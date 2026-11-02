using System.Security.Cryptography;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonReadModelTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task CurrentInventoryExcludesLegacyArchivedAndFutureEquipment()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var current = Define("current", new DateOnly(2026, 11, 2));
        var future = Define("future", new DateOnly(2026, 12, 14));
        var prior = Define("prior", new DateOnly(2026, 9, 21));
        var clock = new Clock(current.StartsAtUtc.AddDays(1));
        var seasons = new SeasonRepository(database.DataSource, clock);
        foreach (var definition in new[] { prior, current, future }) await seasons.PublishAsync(definition, new string('a', 64), Ct);
        await EquipmentAsync(database, player.UserId, null, null);
        var currentId = await EquipmentAsync(database, player.UserId, current.SeasonId, "ActiveSeason");
        await EquipmentAsync(database, player.UserId, future.SeasonId, "ActiveSeason");
        await EquipmentAsync(database, player.UserId, prior.SeasonId, "ArchivedSeason");

        var response = await new ProgressionRepository(database.DataSource, clock).GetInventoryAsync(player.UserId, Ct);

        var item = Assert.Single(response.Equipments);
        Assert.Equal(currentId, item.InstanceId);
        Assert.Equal(current.SeasonId, item.OriginSeasonId);
        Assert.Equal(current.SeasonId, item.SeasonId);
        Assert.Equal("ActiveSeason", item.AssetScope);
        Assert.Equal("season-equipment-v1", item.StatsVersion);
        Assert.Equal(1, response.Summary.EquipmentCount);
        Assert.Equal(49, response.Summary.FreeSlots);
        Assert.Equal("ActiveSeason", response.Scope!.State);
        Assert.False(response.Scope.ReadOnly);
        Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND slot='Head'", player.UserId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task BootstrapSeparatesSeasonBalancesWithoutResettingPermanentDataOrReopeningClosedEconomy()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var current = Define("current", new DateOnly(2026, 11, 2));
        var clock = new Clock(current.StartsAtUtc.AddDays(1));
        var seasons = new SeasonRepository(database.DataSource, clock);
        await seasons.PublishAsync(current, new string('a', 64), Ct);
        await SeedPermanentAsync(database, player.UserId);
        await seasons.EnsurePlayerAsync(player.UserId, current.ContextFor(0), Ct);
        await seasons.ApplyAsync(player.UserId, current.ContextFor(0), 30, 20, 3, "test.reward", "fund", SeasonWalletPurpose.General, Ct);
        using var economy = new EconomyRepository(database.DataSource, clock);
        var bootstrap = Bootstrap(database, clock, economy);

        var active = await bootstrap.GetAsync(player, Ct);

        Assert.Equal(30, active.Wallet.Gold);
        Assert.Equal(80, active.Wallet.Diamond);
        Assert.Equal(20, active.Materials.EquipmentFragments);
        Assert.Equal(77, active.Materials.WarriorSoul);
        Assert.Equal("Active", active.Season!.State);
        Assert.Equal("D0", active.Season.DifficultyId);
        Assert.Equal(0, active.Season.EffectiveLevelCap);
        Assert.True(active.Season.HasJoined);
        Assert.Equal(1000, active.Season.HistoricalEquipmentFragments);
        Assert.Equal(current.SeasonId, Assert.Single(active.Season.FragmentWallets).SeasonId);
        Assert.Contains(active.Cards, card => card.Level == 3);
        Assert.All(active.ClassWeapons, weapon => Assert.Equal(4, weapon.Level));
        Assert.Equal(450L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(1000L, await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId));

        clock.Now = current.EndsAtUtc;
        var closed = await bootstrap.GetAsync(player, Ct);
        Assert.Equal("Closed", closed.Season!.State);
        Assert.Equal(0, closed.Wallet.Gold);
        Assert.Equal(0, closed.Materials.EquipmentFragments);
        Assert.Equal(80, closed.Wallet.Diamond);
        Assert.Equal(77, closed.Materials.WarriorSoul);
        Assert.Equal("Closed", closed.Inventory!.Scope!.State);
        Assert.True(closed.Inventory.Scope.ReadOnly);
        Assert.Contains(closed.Cards, card => card.Level == 3);
        Assert.Equal(450L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AnnouncedFirstSeasonRetainsLegacyUntilItsExactStart()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var player = await PlayerAsync(database);
        var current = Define("first", new DateOnly(2026, 11, 2));
        var clock = new Clock(current.StartsAtUtc.AddTicks(-1));
        var seasons = new SeasonRepository(database.DataSource, clock);
        await seasons.PublishAsync(current, new string('a', 64), Ct);
        await SeedPermanentAsync(database, player.UserId);
        await EquipmentAsync(database, player.UserId, null, null);
        using var economy = new EconomyRepository(database.DataSource, clock);

        var response = await Bootstrap(database, clock, economy).GetAsync(player, Ct);

        Assert.Equal("Upcoming", response.Season!.State);
        Assert.Equal(current.SeasonId, response.Season.NextSeasonId);
        Assert.Equal(current.StartsAtUtc, response.Season.NextStartsAt);
        Assert.Equal(5, response.Season.EffectiveLevelCap);
        Assert.Equal(450, response.Wallet.Gold);
        Assert.Equal(1000, response.Materials.EquipmentFragments);
        Assert.Null(response.Inventory!.Scope);
        Assert.Contains(response.Inventory.Equipments, equipment => equipment.Slot == "Head");
    }

    private static BootstrapRepository Bootstrap(PostgresTestSchema database, Clock clock, EconomyRepository economy) => new(
        database.DataSource, new ProgressionRepository(database.DataSource, clock), economy,
        new MailRepository(database.DataSource, clock), new PreparationRepository(database.DataSource, clock), clock);

    private static SeasonDefinition Define(string id, DateOnly start) => SeasonDefinition.FromCalendarDays(
        id, start, GameConfigCatalog.Current.Version, "season-equipment-v1", highestOpenDifficulty: 5);

    private static async Task<PlayerProfile> PlayerAsync(PostgresTestSchema database)
    {
        var now = DateTimeOffset.UtcNow;
        return await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Season reader", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), Ct);
    }

    private static async Task SeedPermanentAsync(PostgresTestSchema database, Guid playerId)
    {
        await using var command = database.DataSource.CreateCommand("""
            WITH wallet AS (UPDATE player_wallets SET gold=450,diamond=80 WHERE player_id=$1 RETURNING player_id),
            materials AS (UPDATE player_materials SET equipment_fragments=1000,warrior_soul=77 WHERE player_id=$1 RETURNING player_id),
            cards AS (UPDATE player_cards SET level=3 WHERE player_id=$1 AND unlocked RETURNING player_id)
            UPDATE class_weapons SET level=4 WHERE player_id=$1
            """);
        command.Parameters.AddWithValue(playerId); await command.ExecuteNonQueryAsync(Ct);
    }

    private static async Task<Guid> EquipmentAsync(PostgresTestSchema database, Guid playerId, string? seasonId, string? scope)
    {
        var id = Guid.NewGuid();
        await using var command = database.DataSource.CreateCommand("""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES ($1,$2,'Head','Purple',0,'Inventory',CURRENT_TIMESTAMP,$3,$3,$4,$5,$6,$7)
            """);
        command.Parameters.AddWithValue(id); command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, (object?)seasonId ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, (object?)scope ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, seasonId is null ? DBNull.Value : "season-equipment-v1");
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, seasonId is null ? DBNull.Value : "MarkCraft");
        command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Smallint, seasonId is null ? DBNull.Value : (short)2);
        await command.ExecuteNonQueryAsync(Ct);
        return id;
    }

    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
