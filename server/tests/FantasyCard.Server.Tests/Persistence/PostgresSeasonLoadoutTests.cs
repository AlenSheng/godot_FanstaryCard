using System.Security.Cryptography;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonLoadoutTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task SaveRejectsLegacyArchivedAndFutureItemsWithoutChangingVersionOrLocations()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var current = Define("current", new DateOnly(2026, 11, 2));
        var prior = Define("prior", new DateOnly(2026, 9, 21));
        var future = Define("future", new DateOnly(2026, 12, 14));
        var clock = new Clock(current.StartsAtUtc);
        var seasons = new SeasonRepository(database.DataSource, clock);
        foreach (var definition in new[] { prior, current, future }) await seasons.PublishAsync(definition, new string('a', 64), Ct);
        var repository = new ProgressionRepository(database.DataSource, clock);
        var bad = new[] { await ItemAsync(database, player, null, null),
            await ItemAsync(database, player, prior.SeasonId, "ArchivedSeason"),
            await ItemAsync(database, player, future.SeasonId, "ActiveSeason") };
        for (var index = 0; index < bad.Length; index++)
        {
            var rejected = await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(bad[index]), "bad-" + index, 1, clock.Now, Ct);
            Assert.Equal(SaveLoadoutStatus.AssetUnavailable, rejected.Status);
            Assert.Equal("Inventory", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", bad[index]));
        }
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT version FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1", player));
        var valid = await ItemAsync(database, player, current.SeasonId, "ActiveSeason");
        var saved = await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(valid), "valid", 1, clock.Now, Ct);
        Assert.Equal(SaveLoadoutStatus.Updated, saved.Status);
        Assert.Equal(current.SeasonId, saved.Loadout!.SeasonId);
        SameResult(saved, await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(valid), "valid", 1, clock.Now, Ct));
        Assert.Equal(current.SeasonId, await database.ScalarAsync<string>("SELECT season_id FROM inventory_movements WHERE player_id=$1", player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task CurrentSaveDoesNotUnequipAnItemFromAnotherDomain()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var definition = Define("current", new DateOnly(2026, 11, 2));
        var clock = new Clock(definition.StartsAtUtc);
        await new SeasonRepository(database.DataSource, clock).PublishAsync(definition, new string('a', 64), Ct);
        var legacy = await ItemAsync(database, player, null, null, "Equipped");
        var current = await ItemAsync(database, player, definition.SeasonId, "ActiveSeason");

        var saved = await new ProgressionRepository(database.DataSource, clock).SaveLoadoutAsync(
            player, HeroClass.Mage, Slots(current), "save-current", 1, clock.Now, Ct);

        Assert.Equal(SaveLoadoutStatus.Updated, saved.Status);
        Assert.Equal("Equipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", legacy));
        Assert.Equal("Equipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", current));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1", player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task LoadoutReadKeepsCurrentPreparationLocksButHidesForeignReferences()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var definition = Define("current", new DateOnly(2026, 11, 2));
        var clock = new Clock(definition.StartsAtUtc);
        await new SeasonRepository(database.DataSource, clock).PublishAsync(definition, new string('a', 64), Ct);
        var current = await ItemAsync(database, player, definition.SeasonId, "ActiveSeason", "PreparationLocked");
        var legacy = await ItemAsync(database, player, null, null, slot: "Chest");
        await using (var seed = database.DataSource.CreateCommand("UPDATE player_loadouts SET head_id=$2,chest_id=$3 WHERE player_id=$1 AND hero_class=2"))
        {
            seed.Parameters.AddWithValue(player);seed.Parameters.AddWithValue(current);seed.Parameters.AddWithValue(legacy);
            await seed.ExecuteNonQueryAsync(Ct);
        }

        var read = await new ProgressionRepository(database.DataSource, clock).GetLoadoutAsync(player, HeroClass.Mage, Ct);

        Assert.Equal(current, read!.EquipmentIds[0]);
        Assert.Null(read.EquipmentIds[1]);
        Assert.Equal(definition.SeasonId, read.SeasonId);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ClosedPeriodRejectsNewWritesWhileCompletedReplayHasNoNewEffects()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var definition = Define("current", new DateOnly(2026, 11, 2));
        var clock = new Clock(definition.StartsAtUtc);
        await new SeasonRepository(database.DataSource, clock).PublishAsync(definition, new string('a', 64), Ct);
        var current = await ItemAsync(database, player, definition.SeasonId, "ActiveSeason");
        var repository = new ProgressionRepository(database.DataSource, clock);
        var saved = await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(current), "saved", 1, clock.Now, Ct);
        clock.Now = definition.EndsAtUtc;

        await Assert.ThrowsAsync<DomainValidationException>(() => repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(null), "closed-new", 2, clock.Now, Ct));
        SameResult(saved, await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(current), "saved", 1, clock.Now, Ct));
        Assert.All((await repository.GetLoadoutAsync(player, HeroClass.Mage, Ct))!.EquipmentIds, Assert.Null);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1", player));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AnnouncedSeasonRetainsLegacyHashAndCannotMoveFutureEquipmentEarly()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var definition = Define("first", new DateOnly(2026, 11, 2));
        var clock = new Clock(definition.StartsAtUtc.AddTicks(-1));
        await new SeasonRepository(database.DataSource, clock).PublishAsync(definition, new string('a', 64), Ct);
        var legacy = await ItemAsync(database, player, null, null);
        var future = await ItemAsync(database, player, definition.SeasonId, "ActiveSeason");
        var repository = new ProgressionRepository(database.DataSource, clock);

        var rejected = await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(future), "future", 1, clock.Now, Ct);
        Assert.Equal(SaveLoadoutStatus.AssetUnavailable, rejected.Status);
        var saved = await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(legacy), "legacy", 1, clock.Now, Ct);
        Assert.Equal(SaveLoadoutStatus.Updated, saved.Status);
        Assert.Null(saved.Loadout!.SeasonId);
        clock.Now = definition.StartsAtUtc;
        SameResult(saved, await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(legacy), "legacy", 1, clock.Now, Ct));
        Assert.Equal(SaveLoadoutStatus.AssetUnavailable, (await repository.SaveLoadoutAsync(player, HeroClass.Mage, Slots(legacy), "new-realm", 2, clock.Now, Ct)).Status);
    }

    private static Guid?[] Slots(Guid? head) => [head, null, null, null, null];
    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task WaitingForPlayerLockCannotUseAnExpiredAdmissionTimestamp()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var definition = Define("current", new DateOnly(2026, 11, 2));
        var clock = new Clock(definition.EndsAtUtc.AddSeconds(-1));
        await new SeasonRepository(database.DataSource, clock).PublishAsync(definition, new string('a', 64), Ct);
        var current = await ItemAsync(database, player, definition.SeasonId, "ActiveSeason");
        await using var blocker = await database.DataSource.OpenConnectionAsync(Ct);
        await using var transaction = await blocker.BeginTransactionAsync(Ct);
        await using (var command = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", blocker, transaction))
        {
            command.Parameters.AddWithValue(player);await command.ExecuteScalarAsync(Ct);
        }
        var saving = new ProgressionRepository(database.DataSource, clock).SaveLoadoutAsync(
            player, HeroClass.Mage, Slots(current), "boundary-wait", 1, clock.Now, Ct);
        await Task.Delay(50, Ct);
        clock.Now = definition.EndsAtUtc;
        await transaction.CommitAsync(Ct);
        await Assert.ThrowsAsync<DomainValidationException>(() => saving);
        Assert.Equal("Inventory", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", current));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT version FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player));
    }

    private static void SameResult(SaveLoadoutResult expected, SaveLoadoutResult actual)
    {
        Assert.Equal(expected.Status, actual.Status);
        Assert.Equal(expected.Loadout!.Version, actual.Loadout!.Version);
        Assert.Equal(expected.Loadout.SeasonId, actual.Loadout.SeasonId);
        Assert.Equal(expected.Loadout.EquipmentIds, actual.Loadout.EquipmentIds);
    }
    private static SeasonDefinition Define(string id, DateOnly start) => SeasonDefinition.FromCalendarDays(id, start, "config-1", "stats-1", highestOpenDifficulty: 5);

    private static async Task<Guid> PlayerAsync(PostgresTestSchema database)
    {
        var now = DateTimeOffset.UtcNow;
        return (await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Loadout owner", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), Ct)).UserId;
    }

    private static async Task<Guid> ItemAsync(PostgresTestSchema database, Guid player, string? season, string? scope, string location = "Inventory", string slot = "Head")
    {
        var id = Guid.NewGuid();
        await using var command = database.DataSource.CreateCommand("""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES ($1,$2,$9,'Purple',0,$3,CURRENT_TIMESTAMP,$4,$4,$5,$6,$7,$8)
            """);
        command.Parameters.AddWithValue(id);command.Parameters.AddWithValue(player);command.Parameters.AddWithValue(location);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, (object?)season ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, (object?)scope ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, season is null ? DBNull.Value : "stats-1");
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, season is null ? DBNull.Value : "MarkCraft");
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Smallint, season is null ? DBNull.Value : (short)2);
        command.Parameters.AddWithValue(slot);
        await command.ExecuteNonQueryAsync(Ct);return id;
    }

    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
