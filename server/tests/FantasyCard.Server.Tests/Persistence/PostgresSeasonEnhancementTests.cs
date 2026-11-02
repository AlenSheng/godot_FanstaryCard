using System.Security.Cryptography;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonEnhancementTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public Func<DateTimeOffset>? Read { get; set; }
        public override DateTimeOffset GetUtcNow() => Read?.Invoke() ?? Now;
    }
    private sealed record Setup(Guid Player, SeasonDefinition Season, Clock Clock, ProgressionRepository Repository, SeasonRepository Seasons);

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(30, 52, 573, 281)]
    [InlineData(42, 60, 780, 390)]
    [InlineData(60, 60, 780, 390)]
    [Trait("Category", "PostgresIntegration")]
    public async Task ActualFiveArmorAndRedUpgradesMatchQuoteAndConsumeOnlyTheirSeasonWalletAndRealBodies(
        int days, int expectedThree, int expectedFive, int expectedRed)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db, days);
        long total = 0, firstThree = 0;
        foreach (var (quality, slot) in new[] { ("Orange", "Head"), ("Purple", "Chest"), ("Purple", "Hands"), ("Purple", "Legs"), ("Purple", "Feet"), ("Red", "Head") })
        {
            var id = await ItemAsync(db, setup, quality, 0, slot); long itemTotal = 0;
            for (var level = 0; level < 5; level++)
            {
                var quote = (await setup.Repository.GetEquipmentEnhancementQuoteAsync(setup.Player, id, Ct))!;
                Assert.Equal(setup.Season.SeasonId, quote.FragmentSourceSeasonId); Assert.Equal(level + 1, quote.NextLevel);
                Guid? material = level >= 3 ? await ItemAsync(db, setup, quality, 0, "Chest") : null;
                quote = (await setup.Repository.GetEquipmentEnhancementQuoteAsync(setup.Player, id, Ct))!;
                Assert.True(quote.CanEnhance);
                var result = await setup.Repository.EnhanceEquipmentAsync(setup.Player, id, id.ToString("N") + level,
                    new(quote.ExpectedVersion, material, MaterialExpectedVersion: material is null ? null : 1), Ct);
                Assert.Equal(quote.AvailableFragments - quote.FragmentCost, result.EquipmentFragments);
                Assert.Equal(setup.Season.SeasonId, result.Equipment.SeasonId); Assert.Equal("ActiveSeason", result.Equipment.AssetScope);
                Assert.Equal("season-equipment-v1", result.Equipment.StatsVersion);
                if (quality == "Red") Assert.Equal("Inferno", result.Equipment.UniqueAffix);
                itemTotal += quote.FragmentCost;
                if (quality != "Red" && level < 3) firstThree += quote.FragmentCost;
                if (material is { } consumed)
                    Assert.Equal("EnhanceMaterialConsumed", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", consumed));
            }
            if (quality == "Red") Assert.Equal(expectedRed, itemTotal);
            total += itemTotal;
        }
        Assert.Equal(expectedThree, firstThree); Assert.Equal(expectedFive + expectedRed, total);
        Assert.Equal(50_000L - total, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", setup.Player));
        Assert.Equal(99_999L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", setup.Player));
        Assert.Equal(12L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.enhance' AND season_id=$1 AND difficulty_id='D0' AND stats_version='season-equipment-v1'", setup.Season.SeasonId));
        Assert.Equal(-total, await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM economy_ledger WHERE reason='equipment.enhance' AND season_id=$1", setup.Season.SeasonId));
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("quality")]
    [InlineData("scope")]
    [InlineData("stats")]
    [InlineData("location")]
    [InlineData("owner")]
    [InlineData("version")]
    [InlineData("missing-version")]
    [InlineData("bot")]
    [Trait("Category", "PostgresIntegration")]
    public async Task InvalidOrChangedMaterialCannotConsumeEitherWalletOrAnyItem(string invalid)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db);
        var target = await ItemAsync(db, setup, "Purple", 3); var material = await ItemAsync(db, setup, invalid == "quality" ? "Blue" : "Purple", 0);
        if (invalid is "scope" or "stats" or "location" or "bot")
        {
            var assignment = invalid switch { "scope" => "asset_scope='ArchivedSeason'", "stats" => "stats_version='foreign-stats'",
                "location" => "location='MarketListed'", _ => "source_kind='BotReward'" };
            await ExecuteAsync(db, "UPDATE equipments SET " + assignment + " WHERE instance_id=$1", material);
        }
        if (invalid == "owner")
        {
            var another = await PlayerAsync(db); Assert.NotEqual(setup.Player, another);
            await ExecuteAsync(db, "UPDATE equipments SET owner_id=$2 WHERE instance_id=$1", material, another);
        }
        var quote = (await setup.Repository.GetEquipmentEnhancementQuoteAsync(setup.Player, target, Ct))!;
        Assert.Equal(invalid is "version" or "missing-version" ? 1 : 0, quote.AvailableMaterialCount);
        await Assert.ThrowsAsync<DomainValidationException>(() => setup.Repository.EnhanceEquipmentAsync(setup.Player, target,
            "invalid-material", new(1, material, MaterialExpectedVersion: invalid == "missing-version" ? null : invalid == "version" ? 2 : 1), Ct));
        Assert.Equal(50_000L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", setup.Player));
        Assert.Equal(99_999L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", setup.Player));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1", target));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.enhance'"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ConcurrentReplayRestartAndChangedBodyCannotChargeOrConsumeTwice()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db);
        var target = await ItemAsync(db, setup, "Purple", 3); var material = await ItemAsync(db, setup, "Purple", 0);
        var request = new EnhanceEquipmentRequest(1, material, MaterialExpectedVersion: 1);
        var results = await Task.WhenAll(Enumerable.Range(0, 2).Select(_ => setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "same", request, Ct)));
        Assert.Equal(results[0], results[1]);
        setup.Clock.Now = setup.Season.EndsAtUtc;
        var restarted = new ProgressionRepository(db.DataSource, setup.Clock);
        Assert.Equal(results[0], await restarted.EnhanceEquipmentAsync(setup.Player, target, "same", request, Ct));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => restarted.EnhanceEquipmentAsync(setup.Player, target, "same", request with { MaterialExpectedVersion = 2 }, Ct));
        Assert.Equal(49_960L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", setup.Player));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE reason='equipment.enhance'"));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.enhance'"));
        await Assert.ThrowsAsync<DomainValidationException>(() => restarted.GetEquipmentEnhancementQuoteAsync(setup.Player, target, Ct));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task DatabaseFailureAfterWalletDebitRollsBackEverythingAndTheSameKeyCanRetry()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db);
        var target = await ItemAsync(db, setup, "Purple", 3); var material = await ItemAsync(db, setup, "Purple", 0);
        await ExecuteAsync(db, "CREATE FUNCTION block_enhancement() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated enhancement rollback control'; END $$; CREATE TRIGGER enhancement_control BEFORE UPDATE OF level ON equipments FOR EACH ROW EXECUTE FUNCTION block_enhancement()");
        var request = new EnhanceEquipmentRequest(1, material, MaterialExpectedVersion: 1);
        await Assert.ThrowsAsync<Npgsql.PostgresException>(() => setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "retry", request, Ct));
        Assert.Equal(50_000L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", setup.Player));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", material));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE reason='equipment.enhance'"));
        await ExecuteAsync(db, "DROP TRIGGER enhancement_control ON equipments; DROP FUNCTION block_enhancement()");
        Assert.Equal(4, (await setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "retry", request, Ct)).Equipment.Level);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ClosingBoundaryRejectsNewUpgradeBeforeItConsumesTheSeasonWallet()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db);
        var target = await ItemAsync(db, setup, "Purple", 0); var reads = 0;
        setup.Clock.Read = () => ++reads == 1 ? setup.Season.EndsAtUtc.AddMilliseconds(-1) : setup.Season.EndsAtUtc;
        await Assert.ThrowsAsync<DomainValidationException>(() => setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "boundary", new(1), Ct));
        Assert.Equal(50_000L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", setup.Player));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1", target));
    }

    private static async Task<Setup> CreateAsync(PostgresTestSchema db, int days = 42)
    {
        var catalog = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("enhancement-season", new(2026, 11, 1), catalog.Version, "season-equipment-v1", days);
        var clock = new Clock(season.StartsAtUtc.AddHours(2)); var player = await PlayerAsync(db);
        var seasons = new SeasonRepository(db.DataSource, clock); await seasons.PublishAsync(season, catalog.ContentHash, Ct);
        await seasons.EnsurePlayerAsync(player, season.ContextFor(0), Ct);
        await seasons.ApplyAsync(player, season.ContextFor(0), 0, 50_000, 0, "test.fund", "fund", SeasonWalletPurpose.General, Ct);
        await ExecuteAsync(db, "UPDATE player_materials SET equipment_fragments=99999 WHERE player_id=$1", player);
        return new(player, season, clock, new(db.DataSource, clock), seasons);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task EmptySeasonWalletNeverFallsBackToRichHistoricalFragmentsOrConsumesTheMaterial()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db);
        var target = await ItemAsync(db, setup, "Purple", 3); var material = await ItemAsync(db, setup, "Purple", 0);
        await setup.Seasons.ApplyAsync(setup.Player, setup.Season.ContextFor(0), 0, -50_000, 0, "test.empty", "empty", SeasonWalletPurpose.General, Ct);
        var quote = (await setup.Repository.GetEquipmentEnhancementQuoteAsync(setup.Player, target, Ct))!;
        Assert.Equal(0, quote.AvailableFragments); Assert.False(quote.CanEnhance);
        await Assert.ThrowsAsync<DomainValidationException>(() => setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "poor",
            new(1, material, MaterialExpectedVersion: 1), Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "override",
            new(1, material, "another-wallet", 1), Ct));
        Assert.Equal(99_999L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", setup.Player));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", material));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1", target));
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("archive")]
    [InlineData("stats")]
    [Trait("Category", "PostgresIntegration")]
    public async Task ArchivedOrForeignStatsTargetCannotUseTheCurrentSeasonBalance(string invalid)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true); var setup = await CreateAsync(db);
        var target = await ItemAsync(db, setup, "Purple", 0);
        await ExecuteAsync(db, "UPDATE equipments SET " + (invalid == "archive" ? "asset_scope='ArchivedSeason'" : "stats_version='foreign-stats'") + " WHERE instance_id=$1", target);
        await Assert.ThrowsAsync<DomainValidationException>(() => setup.Repository.GetEquipmentEnhancementQuoteAsync(setup.Player, target, Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => setup.Repository.EnhanceEquipmentAsync(setup.Player, target, "closed", new(1), Ct));
        Assert.Equal(50_000L, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", setup.Player));
    }
    private static async Task<Guid> PlayerAsync(PostgresTestSchema db)
    {
        var now = DateTimeOffset.UtcNow;
        return (await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Enhance-" + Guid.NewGuid().ToString("N")[..10], RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), Ct)).UserId;
    }
    private static async Task<Guid> ItemAsync(PostgresTestSchema db, Setup setup, string quality, int level, string slot = "Chest")
    {
        var id = Guid.NewGuid();
        // Red controls already exist. This test does not mint a red drop or exercise C11 weekly quota.
        await ExecuteAsync(db, """
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty,unique_affix,unique_element)
            VALUES($1,$2,$3,$4,$5,false,'Inventory',1,CURRENT_TIMESTAMP,'Fire',
                CASE WHEN $4 IN ('Purple','Orange','Red') THEN 'Piercing' END,'DrawInterval',
                $6,$6,'ActiveSeason','season-equipment-v1','ExistingControl',5,
                CASE WHEN $4='Red' THEN 'Inferno' END,CASE WHEN $4='Red' THEN 'Fire' END)
            """, id, setup.Player, slot, quality, level, setup.Season.SeasonId);
        return id;
    }
    private static async Task ExecuteAsync(PostgresTestSchema db, string sql, params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
}
