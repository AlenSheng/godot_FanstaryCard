using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Common;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonAssetDomainTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static readonly string ConfigHash = new('a', 64);

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task UpgradeFromLegacyPreservesPermanentAssetsAndMarksOnlyUnknownHistoricalMetadata()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        await ApplyPreSeasonBaselineAsync(database);
        var playerId = await CreatePlayerAsync(database);
        await using (var seed = database.DataSource.CreateCommand("""
            WITH wallet AS (UPDATE player_wallets SET gold=450,diamond=80 WHERE player_id=$1 RETURNING player_id),
            materials AS (UPDATE player_materials SET warrior_soul=21,priest_soul=22,mage_soul=23,guardian_soul=24,equipment_fragments=1000 WHERE player_id=$1 RETURNING player_id),
            cards AS (UPDATE player_cards SET level=3 WHERE player_id=$1 AND unlocked RETURNING player_id)
            UPDATE class_weapons SET level=4 WHERE player_id=$1
            """))
        {
            seed.Parameters.AddWithValue(playerId);
            await seed.ExecuteNonQueryAsync(Ct);
        }
        var before = await PermanentAggregateAsync(database, playerId);

        await database.MigrateAsync();
        await database.MigrateAsync();
        var definition = Define("season-a");
        var repository = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        Assert.Null(await repository.GetActiveAsync(Ct));
        Assert.True(await repository.PublishAsync(definition, ConfigHash, Ct));
        await repository.EnsurePlayerAsync(playerId, definition.ContextFor(0), Ct);
        await repository.EnsurePlayerAsync(playerId, definition.ContextFor(0), Ct);

        Assert.Equal(before, await PermanentAggregateAsync(database, playerId));
        var wallet = Assert.IsType<SeasonWalletSnapshot>(await repository.GetWalletAsync(playerId, definition.ContextFor(0), Ct));
        Assert.Equal(0, wallet.Gold);
        Assert.Equal(0, wallet.EquipmentFragments);
        Assert.Equal(0, wallet.ChallengeMarks);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM player_season_state WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM season_definitions WHERE season_id='legacy-gdd-0.70' AND starts_at IS NULL AND config_version IS NULL"));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND asset_scope IS NOT NULL", playerId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task PublicationIsImmutableAndConcurrentRetriesKeepOneSnapshot()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var definition = Define("season-a");
        var repository = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        var attempts = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => repository.PublishAsync(definition, ConfigHash, Ct)));

        Assert.Single(attempts, created => created);
        Assert.Equal(definition, await repository.GetActiveAsync(Ct));
        Assert.Throws<DomainValidationException>(() => new SeasonContext(SeasonDefinition.LegacyArchiveId, 0, "season-v1", "config-1", "stats-1"));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.PublishAsync(definition, new string('b', 64), Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.PublishAsync(Define("season-a", duration: 30), ConfigHash, Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.PublishAsync(Define("overlap", new DateOnly(2026, 11, 3)), ConfigHash, Ct));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM season_definitions WHERE ruleset_id='season-v1'"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AdjacentPeriodsAreHalfOpenAndWalletsRemainIndependent()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var first = Define("season-a");
        var next = Define("season-b", new DateOnly(2026, 12, 14));
        var clock = new ManualClock(first.StartsAtUtc);
        var repository = new SeasonRepository(database.DataSource, clock);
        await repository.PublishAsync(first, ConfigHash, Ct);
        await repository.PublishAsync(next, ConfigHash, Ct);
        await repository.EnsurePlayerAsync(playerId, first.ContextFor(0), Ct);
        await repository.ApplyAsync(playerId, first.ContextFor(0), 100, 20, 3, "test.reward", "reward-old", SeasonWalletPurpose.General, Ct);

        clock.Now = first.EndsAtUtc.AddTicks(-1);
        Assert.Equal(first, await repository.GetActiveAsync(Ct));
        clock.Now = first.EndsAtUtc;
        Assert.Equal(next, await repository.GetActiveAsync(Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.EnsurePlayerAsync(playerId, first.ContextFor(0), Ct));
        await repository.EnsurePlayerAsync(playerId, next.ContextFor(0), Ct);
        Assert.Equal(0, (await repository.GetWalletAsync(playerId, next.ContextFor(0), Ct))!.Gold);
        Assert.Equal(100, (await repository.GetWalletAsync(playerId, first.ContextFor(0), Ct))!.Gold);
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT count(*) FROM player_season_wallets WHERE player_id=$1", playerId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ConcurrentWalletReplayWritesOneOperationAndOneEntryPerResource()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var repository = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await repository.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await repository.EnsurePlayerAsync(playerId, context, Ct);

        var results = await Task.WhenAll(Enumerable.Range(0, 12).Select(_ => repository.ApplyAsync(
            playerId, context, 100, 20, 3, "test.reward", "same-request", SeasonWalletPurpose.General, Ct)));

        Assert.All(results, wallet => Assert.Equal(results[0], wallet));
        Assert.Equal(100, results[0].Gold);
        Assert.Equal(2, results[0].Version);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", playerId));
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND season_id='season-a'", playerId));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.ApplyAsync(
            playerId, context, 101, 20, 3, "test.reward", "same-request", SeasonWalletPurpose.General, Ct));
        Assert.Equal(100, (await repository.GetWalletAsync(playerId, context, Ct))!.Gold);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ParallelSpendsCannotOverdrawAndRejectedAmountsLeaveNoJournal()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var repository = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await repository.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await repository.EnsurePlayerAsync(playerId, context, Ct);
        await repository.ApplyAsync(playerId, context, 100, 0, 0, "test.reward", "fund", SeasonWalletPurpose.General, Ct);

        var spends = await Task.WhenAll(Enumerable.Range(0, 2).Select(async index =>
        {
            try { await repository.ApplyAsync(playerId, context, -80, 0, 0, "test.purchase", "buy-" + index, SeasonWalletPurpose.General, Ct); return true; }
            catch (DomainValidationException) { return false; }
        }));

        Assert.Single(spends, succeeded => succeeded);
        Assert.Equal(20, (await repository.GetWalletAsync(playerId, context, Ct))!.Gold);
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", playerId));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.ApplyAsync(
            playerId, context, long.MaxValue, 0, 0, "test.reward", "overflow", SeasonWalletPurpose.General, Ct));
        Assert.Equal(20, (await repository.GetWalletAsync(playerId, context, Ct))!.Gold);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task CallerRollbackAlsoRollsBackBalancesOperationsAndLedger()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var repository = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await repository.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await repository.EnsurePlayerAsync(playerId, context, Ct);
        await using (var connection = await database.DataSource.OpenConnectionAsync(Ct))
        await using (var transaction = await connection.BeginTransactionAsync(Ct))
        {
            await SeasonRepository.ApplyWithinTransactionAsync(connection, transaction, playerId, context,
                100, 5, 0, "test.reward", "rollback", SeasonWalletPurpose.General, definition.StartsAtUtc, ConfigHash, Ct);
            await transaction.RollbackAsync(Ct);
        }
        Assert.Equal(0, (await repository.GetWalletAsync(playerId, context, Ct))!.Gold);
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", playerId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND season_id IS NOT NULL", playerId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ArchivedWalletAllowsOnlyExplicitPermanentWeaponSpendAndOldSeasonCredits()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var first = Define("season-a");
        var next = Define("season-b", new DateOnly(2026, 12, 14));
        var clock = new ManualClock(first.StartsAtUtc);
        var repository = new SeasonRepository(database.DataSource, clock);
        await repository.PublishAsync(first, ConfigHash, Ct);
        await repository.PublishAsync(next, ConfigHash, Ct);
        var oldContext = first.ContextFor(0);
        await repository.EnsurePlayerAsync(playerId, oldContext, Ct);
        await repository.ApplyAsync(playerId, oldContext, 100, 50, 3, "test.reward", "old", SeasonWalletPurpose.General, Ct);
        await database.ExecuteAsync("UPDATE player_season_wallets SET archived_at=CURRENT_TIMESTAMP WHERE season_id='season-a'; UPDATE player_season_state SET archived_at=CURRENT_TIMESTAMP WHERE season_id='season-a'");
        clock.Now = next.StartsAtUtc;
        await repository.EnsurePlayerAsync(playerId, next.ContextFor(0), Ct);

        await Assert.ThrowsAsync<DomainValidationException>(() => repository.ApplyAsync(
            playerId, oldContext, 0, -10, 0, "test.armor", "old-armor", SeasonWalletPurpose.General, Ct));
        await repository.ApplyAsync(playerId, oldContext, 0, -10, 0, "class_weapon.enhance", "old-weapon", SeasonWalletPurpose.PermanentWeaponEnhancement, Ct);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.ApplyAsync(
            playerId, oldContext, -1, -1, 0, "class_weapon.enhance", "bad-weapon", SeasonWalletPurpose.PermanentWeaponEnhancement, Ct));
        await repository.ApplyAsync(playerId, oldContext, 5, 2, 0, "match.settlement", "late", SeasonWalletPurpose.LateSettlement, Ct);
        Assert.Equal(105, (await repository.GetWalletAsync(playerId, oldContext, Ct))!.Gold);
        Assert.Equal(42, (await repository.GetWalletAsync(playerId, oldContext, Ct))!.EquipmentFragments);
        Assert.Equal(0, (await repository.GetWalletAsync(playerId, next.ContextFor(0), Ct))!.Gold);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task CompletedRequestReplaysAfterPeriodEndButCannotChangeContextOrCreditAgain()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var clock = new ManualClock(definition.StartsAtUtc);
        var repository = new SeasonRepository(database.DataSource, clock);
        await repository.PublishAsync(definition, ConfigHash, Ct);
        await repository.EnsurePlayerAsync(playerId, definition.ContextFor(0), Ct);
        var first = await repository.ApplyAsync(playerId, definition.ContextFor(0), 10, 0, 0, "test.reward", "retry", SeasonWalletPurpose.General, Ct);
        clock.Now = definition.EndsAtUtc;

        Assert.Equal(first, await repository.ApplyAsync(playerId, definition.ContextFor(0), 10, 0, 0, "test.reward", "retry", SeasonWalletPurpose.General, Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.ApplyAsync(
            playerId, definition.ContextFor(1), 10, 0, 0, "test.reward", "retry", SeasonWalletPurpose.General, Ct));
        var invalidContext = new SeasonContext("season-a", 0, "season-v1", "wrong-config", "season-equipment-v1");
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.GetWalletAsync(playerId, invalidContext, Ct));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", playerId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task EquipmentDomainConstraintsRejectCrossSeasonOrPrematureHistoricalReuse()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var repository = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await repository.PublishAsync(definition, ConfigHash, Ct);
        var equipment = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, Ct);
        async Task UpdateAsync(string sql)
        {
            await using var command = database.DataSource.CreateCommand(sql);
            command.Parameters.AddWithValue(equipment);
            await command.ExecuteNonQueryAsync(Ct);
        }
        var invalid = await Assert.ThrowsAsync<PostgresException>(() => UpdateAsync("""
            UPDATE equipments SET origin_season_id='legacy-gdd-0.70',season_id='season-a',asset_scope='ActiveSeason',
                stats_version='season-equipment-v1',source_kind='NaturalDrop',generated_difficulty=0 WHERE instance_id=$1
            """));
        Assert.Equal(PostgresErrorCodes.CheckViolation, invalid.SqlState);
        invalid = await Assert.ThrowsAsync<PostgresException>(() => UpdateAsync("""
            UPDATE equipments SET origin_season_id='legacy-gdd-0.70',season_id='legacy-gdd-0.70',asset_scope='ActiveSeason' WHERE instance_id=$1
            """));
        Assert.Equal(PostgresErrorCodes.CheckViolation, invalid.SqlState);
        await UpdateAsync("UPDATE equipments SET origin_season_id='legacy-gdd-0.70',season_id='legacy-gdd-0.70',asset_scope='ArchivedSeason' WHERE instance_id=$1");
        Assert.Equal("legacy-gdd-0.70", await database.ScalarAsync<string>("SELECT origin_season_id FROM equipments WHERE instance_id=$1", equipment));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task PermanentWeaponUpgradeUsesChosenSeasonWalletInTheSameTransaction()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var seasons = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await seasons.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await seasons.EnsurePlayerAsync(playerId, context, Ct);
        await seasons.ApplyAsync(playerId, context, 0, 100, 0, "test.reward", "fund", SeasonWalletPurpose.General, Ct);
        await using (var seed = database.DataSource.CreateCommand("UPDATE player_materials SET equipment_fragments=1000 WHERE player_id=$1"))
        {
            seed.Parameters.AddWithValue(playerId); await seed.ExecuteNonQueryAsync(Ct);
        }
        var progression = new ProgressionRepository(database.DataSource);
        var enhanced = await progression.EnhanceWeaponAsync(playerId, HeroClass.Mage, "season-upgrade", 1, context, Ct);

        Assert.Equal(1, enhanced.Equipment.Level);
        Assert.Equal(92, enhanced.EquipmentFragments);
        Assert.Equal(enhanced, await progression.EnhanceWeaponAsync(playerId, HeroClass.Mage, "season-upgrade", 1, context, Ct));
        Assert.Equal(1000L, await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id='season-upgrade'", playerId));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => progression.EnhanceWeaponAsync(playerId, HeroClass.Guardian, "season-upgrade", 1, context, Ct));

        var historical = await progression.EnhanceWeaponAsync(playerId, HeroClass.Priest, "historical-upgrade", 1, Ct);
        Assert.Equal(992, historical.EquipmentFragments);
        Assert.Equal(92, (await seasons.GetWalletAsync(playerId, context, Ct))!.EquipmentFragments);
        Assert.Equal(248, GameConfigCatalog.Current.EquipmentQuality("White").EnhanceTotalCost);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task InsufficientSelectedWalletCannotSpendHistoricalFragmentsOrUpgradeWeapon()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var seasons = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await seasons.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await seasons.EnsurePlayerAsync(playerId, context, Ct);
        await using (var seed = database.DataSource.CreateCommand("UPDATE player_materials SET equipment_fragments=1000 WHERE player_id=$1"))
        {
            seed.Parameters.AddWithValue(playerId); await seed.ExecuteNonQueryAsync(Ct);
        }
        var progression = new ProgressionRepository(database.DataSource);
        await Assert.ThrowsAsync<DomainValidationException>(() => progression.EnhanceWeaponAsync(playerId, HeroClass.Mage, "unfunded", 1, context, Ct));

        Assert.Equal(0, await database.ScalarAsync<int>("SELECT level FROM class_weapons WHERE player_id=$1 AND hero_class=2", playerId));
        Assert.Equal(1000L, await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", playerId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1", playerId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM idempotency_records WHERE player_id=$1 AND scope='class_weapon.enhance'", playerId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task WeaponWriteFailureRollsBackItsSeasonDebitAndCanRetryOnce()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var seasons = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await seasons.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await seasons.EnsurePlayerAsync(playerId, context, Ct);
        await seasons.ApplyAsync(playerId, context, 0, 100, 0, "test.reward", "fund", SeasonWalletPurpose.General, Ct);
        await database.ExecuteAsync("""
            CREATE FUNCTION test_reject_weapon() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected weapon write failure'; END $$;
            CREATE TRIGGER reject_weapon_update BEFORE UPDATE ON class_weapons FOR EACH ROW EXECUTE FUNCTION test_reject_weapon()
            """);
        var progression = new ProgressionRepository(database.DataSource);
        await Assert.ThrowsAsync<PostgresException>(() => progression.EnhanceWeaponAsync(playerId, HeroClass.Mage, "rollback-upgrade", 1, context, Ct));

        Assert.Equal(100, (await seasons.GetWalletAsync(playerId, context, Ct))!.EquipmentFragments);
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE player_id=$1 AND reason='class_weapon.enhance'", playerId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id='rollback-upgrade'", playerId));
        await database.ExecuteAsync("DROP TRIGGER reject_weapon_update ON class_weapons; DROP FUNCTION test_reject_weapon()");
        Assert.Equal(1, (await progression.EnhanceWeaponAsync(playerId, HeroClass.Mage, "rollback-upgrade", 1, context, Ct)).Equipment.Level);
        Assert.Equal(92, (await seasons.GetWalletAsync(playerId, context, Ct))!.EquipmentFragments);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task WalletReplayStillRejectsDifferentWeaponAfterOuterIdempotencyRecordExpires()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var playerId = await CreatePlayerAsync(database);
        var definition = Define("season-a");
        var seasons = new SeasonRepository(database.DataSource, new ManualClock(definition.StartsAtUtc));
        await seasons.PublishAsync(definition, ConfigHash, Ct);
        var context = definition.ContextFor(0);
        await seasons.EnsurePlayerAsync(playerId, context, Ct);
        await seasons.ApplyAsync(playerId, context, 0, 100, 0, "test.reward", "fund", SeasonWalletPurpose.General, Ct);
        var progression = new ProgressionRepository(database.DataSource);
        await progression.EnhanceWeaponAsync(playerId, HeroClass.Mage, "reused-upgrade", 1, context, Ct);
        await using (var expire = database.DataSource.CreateCommand("DELETE FROM idempotency_records WHERE player_id=$1 AND scope='class_weapon.enhance' AND request_id='reused-upgrade'"))
        {
            expire.Parameters.AddWithValue(playerId); await expire.ExecuteNonQueryAsync(Ct);
        }

        await Assert.ThrowsAsync<DomainValidationException>(() => progression.EnhanceWeaponAsync(playerId, HeroClass.Guardian, "reused-upgrade", 1, context, Ct));
        Assert.Equal(0, await database.ScalarAsync<int>("SELECT level FROM class_weapons WHERE player_id=$1 AND hero_class=3", playerId));
        Assert.Equal(92, (await seasons.GetWalletAsync(playerId, context, Ct))!.EquipmentFragments);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id='reused-upgrade'", playerId));
    }

    private static SeasonDefinition Define(string id, DateOnly? starts = null, int duration = 42) =>
        SeasonDefinition.FromCalendarDays(id, starts ?? new DateOnly(2026, 11, 2), "season-config-1", "season-equipment-v1", duration, 5);

    private static async Task<Guid> CreatePlayerAsync(PostgresTestSchema database)
    {
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var now = DateTimeOffset.UtcNow;
        var player = await identity.SignInLocalAsync(Guid.NewGuid().ToString("N"), "Season tester",
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), Ct);
        return player.UserId;
    }

    private static Task<string> PermanentAggregateAsync(PostgresTestSchema database, Guid playerId) => database.ScalarAsync<string>("""
        SELECT jsonb_build_object(
            'wallet',(SELECT to_jsonb(w) FROM player_wallets w WHERE player_id=$1),
            'materials',(SELECT to_jsonb(m) FROM player_materials m WHERE player_id=$1),
            'cards',(SELECT jsonb_agg(to_jsonb(c) ORDER BY card_id) FROM player_cards c WHERE player_id=$1),
            'weapons',(SELECT jsonb_agg(to_jsonb(w) ORDER BY hero_class) FROM class_weapons w WHERE player_id=$1),
            'decks',(SELECT count(*) FROM player_decks WHERE player_id=$1),
            'equipment',(SELECT string_agg(instance_id::text||':'||level||':'||location||':'||version,',' ORDER BY instance_id) FROM equipments WHERE owner_id=$1)
        )::text
        """, playerId);

    private static async Task ApplyPreSeasonBaselineAsync(PostgresTestSchema database)
    {
        await database.ExecuteAsync("CREATE TABLE schema_migrations(version integer PRIMARY KEY,name varchar(160) NOT NULL,checksum varchar(64) NOT NULL,applied_at timestamptz NOT NULL)");
        var assembly = typeof(DatabaseMigrator).Assembly;
        foreach (var resource in assembly.GetManifestResourceNames()
                     .Where(name => name.Contains(".Persistence.Migrations.V", StringComparison.Ordinal) && name.EndsWith(".sql", StringComparison.Ordinal))
                     .Order(StringComparer.Ordinal))
        {
            var filename = resource[(resource.LastIndexOf(".V", StringComparison.Ordinal) + 1)..];
            var version = int.Parse(filename.AsSpan(1, 3), CultureInfo.InvariantCulture);
            if (version >= 31) continue;
            using var stream = assembly.GetManifestResourceStream(resource)!;
            using var reader = new StreamReader(stream, Encoding.UTF8);
            var sql = await reader.ReadToEndAsync(Ct);
            await database.ExecuteAsync(sql);
            await using var record = database.DataSource.CreateCommand("INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES ($1,$2,$3,CURRENT_TIMESTAMP)");
            record.Parameters.AddWithValue(version); record.Parameters.AddWithValue(filename[6..^4]);
            record.Parameters.AddWithValue(Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(sql.Replace("\r\n", "\n", StringComparison.Ordinal)))));
            await record.ExecuteNonQueryAsync(Ct);
        }
    }

    private sealed class ManualClock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
