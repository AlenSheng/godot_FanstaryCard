using System.Security.Cryptography;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonPreparationTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task SnapshotPinsContextAndProjectsLevelsWithoutChangingPermanentProgression()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(db);
        var definition = Define();var clock = new Clock(definition.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(definition, GameConfigCatalog.Current.ContentHash, Ct);
        await using (var seed = db.DataSource.CreateCommand("WITH c AS (UPDATE player_cards SET level=5 WHERE player_id=$1 AND unlocked RETURNING player_id) UPDATE class_weapons SET level=5 WHERE player_id=$1"))
        {
            seed.Parameters.AddWithValue(player);await seed.ExecuteNonQueryAsync(Ct);
        }
        var request = await RequestAsync(db, player, "D0");
        var repository = new PreparationRepository(db.DataSource, clock);
        var result = await repository.CreateAsync(player, "prepare", request, Ct);
        Assert.Equal(CreatePreparationStatus.Created, result.Status);
        var snapshot = result.Preparation!.Snapshot;
        Assert.Equal(70, snapshot.MaximumHp);
        Assert.Equal(GameConfigCatalog.Current.SeasonLootPreference!.DefaultElement,snapshot.LootPreferenceElement);
        Assert.Equal(0, snapshot.ClassWeaponLevel);
        Assert.Equal(5, snapshot.ActualClassWeaponLevel);
        Assert.All(snapshot.CardLevels!, value => Assert.Equal(0, value));
        Assert.All(snapshot.ActualCardLevels!, value => Assert.Equal(5, value));
        Assert.Equal("current", snapshot.Season!.SeasonId);
        Assert.Equal("season-v1", snapshot.Season.RulesetId);
        Assert.Equal("D0", snapshot.Season.DifficultyId);
        Assert.Equal(GameConfigCatalog.Current.Version, snapshot.ConfigVersion);
        Assert.Equal(5, await db.ScalarAsync<int>("SELECT min(level) FROM player_cards WHERE player_id=$1 AND unlocked", player));
        Assert.Equal(5, await db.ScalarAsync<int>("SELECT level FROM class_weapons WHERE player_id=$1 AND hero_class=2", player));
        Assert.Equal("current", await db.ScalarAsync<string>("SELECT season_id FROM preparations WHERE preparation_id=$1", result.Preparation.PreparationId));
        var replay = await repository.CreateAsync(player, "prepare", request, Ct);
        Assert.Equal(CreatePreparationStatus.Replayed, replay.Status);
        Assert.Equal(result.Preparation.PreparationId, replay.Preparation!.PreparationId);
        Assert.Equal(snapshot.Season, replay.Preparation.Snapshot.Season);
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(0, "Purple", false)]
    [InlineData(1, "Orange", false)]
    [InlineData(2, "Orange", true)]
    [Trait("Category", "PostgresIntegration")]
    public async Task EntryCapsAndSeasonStatsAreCheckedBeforeLockingAssets(int difficulty, string quality, bool accepted)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(db);var definition = Define();var clock = new Clock(definition.StartsAtUtc);
        var seasons = new SeasonRepository(db.DataSource, clock);
        await seasons.PublishAsync(definition, GameConfigCatalog.Current.ContentHash, Ct);
        await seasons.EnsurePlayerAsync(player, definition.ContextFor(0), Ct);
        await using (var unlock = db.DataSource.CreateCommand("UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1"))
        {
            unlock.Parameters.AddWithValue(player);await unlock.ExecuteNonQueryAsync(Ct);
        }
        var item = await ItemAsync(db, player, "current", "season-equipment-v1", quality);
        var request = await RequestAsync(db, player, "D" + difficulty, item);
        var result = await new PreparationRepository(db.DataSource, clock).CreateAsync(player, "entry", request, Ct);
        Assert.Equal(accepted ? CreatePreparationStatus.Created : CreatePreparationStatus.AssetUnavailable, result.Status);
        Assert.Equal(accepted ? "PreparationLocked" : "Equipped", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", item));
        Assert.Equal(accepted ? 1L : 0L, await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1", player));
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(null, null)]
    [InlineData("current", "wrong-stats")]
    [Trait("Category", "PostgresIntegration")]
    public async Task LegacyOrMismatchedStatsEquipmentCannotEnterSeasonPreparation(string? season, string? stats)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(db);var definition = Define();var clock = new Clock(definition.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(definition, GameConfigCatalog.Current.ContentHash, Ct);
        var item = await ItemAsync(db, player, season, stats, "Blue");
        var result = await new PreparationRepository(db.DataSource, clock).CreateAsync(player, "bad-item", await RequestAsync(db, player, "D0", item), Ct);
        Assert.Equal(CreatePreparationStatus.AssetUnavailable, result.Status);
        Assert.Equal("Equipped", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", item));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM player_season_state WHERE player_id=$1", player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task LockedDifficultyAndWrongConfigurationCannotCreateMembershipOrPreparation()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(db);var definition = Define();var clock = new Clock(definition.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(definition, GameConfigCatalog.Current.ContentHash, Ct);
        var repository = new PreparationRepository(db.DataSource, clock);
        var lockedRequest = await RequestAsync(db, player, "D2");
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.CreateAsync(player, "locked", lockedRequest, Ct));
        var wrongSeason = (await RequestAsync(db, player, "D0")) with { SeasonId = "another" };
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.CreateAsync(player, "wrong-season", wrongSeason, Ct));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM player_season_state WHERE player_id=$1", player));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1", player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task PreparationExpiresAtSeasonEndAndDoesNotFallBackToLegacyAfterClosure()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(db);var definition = Define();var clock = new Clock(definition.EndsAtUtc.AddSeconds(-10));
        await new SeasonRepository(db.DataSource, clock).PublishAsync(definition, GameConfigCatalog.Current.ContentHash, Ct);
        var repository = new PreparationRepository(db.DataSource, clock);
        var request = await RequestAsync(db, player, "D0");
        var created = await repository.CreateAsync(player, "before-end", request, Ct);
        Assert.Equal(definition.EndsAtUtc, created.Preparation!.ExpiresAt);
        clock.Now = definition.EndsAtUtc;
        var legacy = request with { SeasonId = null, Difficulty = "Standard" };
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.CreateAsync(player, "after-end", legacy, Ct));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1", player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task UnloadedSeasonConfigurationCannotCreateAFalseCurrentSnapshot()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(db);var normal = Define();var clock = new Clock(normal.StartsAtUtc);
        var wrong = new SeasonDefinition(normal.SeasonId, normal.RulesetId, "unloaded-config", normal.StatsVersion,
            normal.StartsAtUtc, normal.EndsAtUtc, normal.HighestOpenDifficulty);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(wrong, new string('a', 64), Ct);
        var request = await RequestAsync(db, player, "D0");
        await Assert.ThrowsAsync<DomainValidationException>(() => new PreparationRepository(db.DataSource, clock).CreateAsync(player, "unloaded", request, Ct));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1", player));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM player_season_wallets WHERE player_id=$1", player));
    }

    private static SeasonDefinition Define() => SeasonDefinition.FromCalendarDays("current", new DateOnly(2026, 11, 2), GameConfigCatalog.Current.Version, "season-equipment-v1", highestOpenDifficulty: 5);
    private static async Task<Guid> PlayerAsync(PostgresTestSchema db)
    {
        var now=DateTimeOffset.UtcNow;
        return (await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"),"Prepared owner",RandomNumberGenerator.GetBytes(32),now,now.AddHours(1),Ct)).UserId;
    }
    private static async Task<CreatePreparationRequest> RequestAsync(PostgresTestSchema db,Guid player,string difficulty,Guid? item=null) =>
        new(HeroClassDto.Mage,await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",player),
            [item,null,null,null,null],BackpackTierDto.Free,[],0,difficulty,"current");
    private static async Task<Guid> ItemAsync(PostgresTestSchema db,Guid player,string? season,string? stats,string quality)
    {
        var id=Guid.NewGuid();await using var command=db.DataSource.CreateCommand("""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES ($1,$2,'Head',$3,0,'Equipped',CURRENT_TIMESTAMP,'Fire',$4,$4,$5,$6,$7,$8)
            """);
        command.Parameters.AddWithValue(id);command.Parameters.AddWithValue(player);command.Parameters.AddWithValue(quality);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar,(object?)season??DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar,season is null?DBNull.Value:"ActiveSeason");
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar,(object?)stats??DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar,season is null?DBNull.Value:"NaturalDrop");
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Smallint,season is null?DBNull.Value:(short)2);
        await command.ExecuteNonQueryAsync(Ct);return id;
    }
    private sealed class Clock(DateTimeOffset now):TimeProvider
    {
        public DateTimeOffset Now{get;set;}=now;
        public override DateTimeOffset GetUtcNow()=>Now;
    }
}
