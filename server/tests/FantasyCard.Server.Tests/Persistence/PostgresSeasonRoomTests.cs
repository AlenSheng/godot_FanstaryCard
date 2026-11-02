using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonRoomTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task PreparationToRoomAndRestartAfterNextSeasonRetainTheOriginalContextAndProjection()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.EndsAtUtc.AddSeconds(-5));
        var seasons = new SeasonRepository(db.DataSource, clock);
        await seasons.PublishAsync(season, new string('a', 64), Ct);
        var player = await PlayerAsync(db, clock);
        await Sql(db, "WITH cards AS (UPDATE player_cards SET level=5 WHERE player_id=$1 AND unlocked RETURNING player_id) UPDATE class_weapons SET level=5 WHERE player_id=$1", player);
        var version = await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2", player);
        var preparation = await new PreparationRepository(db.DataSource, clock).CreateAsync(player, "prepare",
            new(HeroClassDto.Mage, version, [null, null, null, null, null], FantasyCard.Contracts.Matchmaking.BackpackTierDto.Free, [], 0, "D0", season.SeasonId), Ct);
        Assert.Equal(CreatePreparationStatus.Created, preparation.Status);
        using var metrics = new ServerMetrics();
        var settings = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["Matchmaking:BotFillDelaySeconds"] = "0" }).Build();
        var matchmaking = new MatchmakingRepository(db.DataSource, clock, metrics, settings);
        await matchmaking.EnqueueAsync(player, "queue", new(preparation.Preparation!.PreparationId), Ct);
        var pending = Assert.IsType<PendingMatch>(await matchmaking.TryCreateMatchAsync(Ct));
        await matchmaking.MarkReadyAsync(player, clock.Now, Ct);
        var snapshots = new RoomSnapshotRepository(db.DataSource, clock, metrics);
        await using (var rooms = new RoomRegistry(clock))
        {
            using var coordinator = new RoomReadyCoordinator(matchmaking, rooms, snapshots, new RealtimeEventStore(clock),
                new ConnectionRegistry(), clock, NullLogger<RoomReadyCoordinator>.Instance);
            Assert.True(await coordinator.ProcessNextAsync(clock.Now, Ct));
            var snapshot = await snapshots.GetAsync(pending.RoomId, Ct);
            Assert.Equal(season.ContextFor(0), snapshot!.Season);
            Assert.All(snapshot.Players, value => Assert.Equal(0, value.Combat.WeaponLevel));
            Assert.Equal(70, snapshot.Players.Single(p => p.PlayerId == player).Combat.MaximumHp);
        }
        var next = new SeasonDefinition("next", "season-v1", season.ConfigVersion, "next-stats",
            season.EndsAtUtc, season.EndsAtUtc.AddDays(42), 5);
        await seasons.PublishAsync(next, new string('b', 64), Ct);
        clock.Now = next.StartsAtUtc.AddSeconds(1);
        var recovery = new RoomRecoveryState();
        await using var restarted = new RoomRegistry(clock);
        await new RoomRecoveryWorker(snapshots, restarted, recovery, clock, NullLogger<RoomRecoveryWorker>.Instance).StartAsync(Ct);
        Assert.True(recovery.Capture().IsHealthy);
        Assert.True(restarted.TryGetForPlayer(player, out var actor, out var match));
        Assert.Equal(pending.MatchId, match);
        var restored = await actor!.ExecuteAsync(new GetRoomSnapshotCommand(), Ct);
        Assert.Equal(season.ContextFor(0), restored.Season);
        Assert.Equal(0, restored.Players.Single(p => p.PlayerId == player).Combat.WeaponLevel);
        Assert.Equal(5, await db.ScalarAsync<int>("SELECT level FROM class_weapons WHERE player_id=$1 AND hero_class=2", player));
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("season")]
    [InlineData("difficulty")]
    [InlineData("stats")]
    [InlineData("config")]
    [Trait("Category", "PostgresIntegration")]
    public async Task ChangedContextCannotOverwriteTheOriginalCheckpoint(string dimension)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var fixture = await RoomAsync(db, clock, season.ContextFor(0));
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, clock, metrics);
        var original = fixture.Room.Capture();
        await repository.SaveIfDueAsync(original, Ct);
        var raw = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", fixture.Room.RoomId);
        var context = new SeasonContext(dimension == "season" ? "other" : season.SeasonId,
            dimension == "difficulty" ? 1 : 0, season.RulesetId,
            dimension == "config" ? "other-config" : season.ConfigVersion, dimension == "stats" ? "other-stats" : season.StatsVersion);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.SaveIfDueAsync(original with
            { Revision = original.Revision + 20, Season = context, ConfigVersion = context.ConfigVersion }, Ct));
        Assert.Equal(raw, await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", fixture.Room.RoomId));
        Assert.Equal(original.Season, (await repository.GetAsync(original.RoomId, Ct))!.Season);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task OrphansAreRejectedAndOwnedLegacySnapshotsWithoutSeasonRemainReadable()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var metrics = new ServerMetrics();
        var repository = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        var context = Define().ContextFor(0);
        var seasonal = new BattleRoom(Guid.NewGuid(), context.ConfigVersion, CombatCardCatalog.CreatePrototype(), 73, season: context);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.SaveIfDueAsync(seasonal.Capture(), Ct));
        var legacy = new BattleRoom(Guid.NewGuid(), "legacy", CombatCardCatalog.CreatePrototype(), 73);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.SaveIfDueAsync(legacy.Capture(), Ct));
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,'legacy','Running',now())", Guid.NewGuid(), legacy.RoomId);
        await repository.SaveIfDueAsync(legacy.Capture(), Ct);
        Assert.Null((await repository.GetAsync(legacy.RoomId, Ct))!.Season);
        await Sql(db, "UPDATE room_snapshots SET snapshot_json=snapshot_json-'season' WHERE room_id=$1", legacy.RoomId);
        await repository.SaveIfDueAsync(legacy.Capture() with { Revision = 10 }, Ct);
        Assert.Equal(10, (await repository.GetAsync(legacy.RoomId, Ct))!.Revision);
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("stats")]
    [InlineData("ruleset")]
    [InlineData("missing-season")]
    [InlineData("room")]
    [InlineData("config")]
    [Trait("Category", "PostgresIntegration")]
    public async Task RecoveryQuarantinesOnlyTheCorruptedRoomWithoutRewritingItsEvidence(string corruption)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var bad = await RoomAsync(db, clock, season.ContextFor(0));
        var good = await RoomAsync(db, clock, season.ContextFor(0));
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource, clock, metrics);
        await snapshots.SaveIfDueAsync(bad.Room.Capture(), Ct);
        await snapshots.SaveIfDueAsync(good.Room.Capture(), Ct);
        if (corruption == "missing-season")
            await Sql(db, "UPDATE room_snapshots SET snapshot_json=snapshot_json-'season' WHERE room_id=$1", bad.Room.RoomId);
        else
        {
            var path = corruption switch { "stats" => new[] { "season", "statsVersion" }, "ruleset" => ["season", "rulesetId"], "room" => ["roomId"], _ => new[] { "configVersion" } };
            var value = corruption == "room" ? Guid.NewGuid().ToString("D") : "corrupted";
            await Sql(db, "UPDATE room_snapshots SET snapshot_json=jsonb_set(snapshot_json,$2,$3::jsonb) WHERE room_id=$1", bad.Room.RoomId, path, JsonSerializer.Serialize(value));
        }
        var raw = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", bad.Room.RoomId);
        var state = new RoomRecoveryState();
        await using var rooms = new RoomRegistry(clock);
        await new RoomRecoveryWorker(snapshots, rooms, state, clock, NullLogger<RoomRecoveryWorker>.Instance).StartAsync(Ct);
        Assert.False(state.Capture().IsHealthy);
        Assert.Equal([bad.Room.RoomId], state.Capture().FailedRoomIds);
        Assert.False(rooms.ContainsRoom(bad.Room.RoomId));
        Assert.True(rooms.ContainsRoom(good.Room.RoomId));
        Assert.Equal(raw, await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", bad.Room.RoomId));
        await Assert.ThrowsAnyAsync<Exception>(() => snapshots.GetAsync(bad.Room.RoomId, Ct));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task OwnedTerminalReadRequiresTheOriginalMatchContext()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var fixture = await RoomAsync(db, clock, season.ContextFor(0));
        var snapshot = fixture.Room.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(p => p with { Phase = RoomPlayerPhase.Extracted, Pve = null }).ToArray() };
        await Sql(db, "UPDATE match_players SET state='Settled' WHERE match_id=$1", fixture.Match);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource, clock, metrics);
        await snapshots.SaveIfDueAsync(snapshot, Ct);
        Assert.Equal(season.ContextFor(0), (await snapshots.GetOwnedTerminalAsync(fixture.Player, snapshot.RoomId, fixture.Match, Ct))!.Snapshot.Season);
        Assert.Null(await snapshots.GetOwnedTerminalAsync(Guid.NewGuid(), snapshot.RoomId, fixture.Match, Ct));
        await Sql(db, "UPDATE room_snapshots SET snapshot_json=jsonb_set(snapshot_json,'{season,statsVersion}','\"wrong\"') WHERE room_id=$1", snapshot.RoomId);
        await Assert.ThrowsAsync<InvalidOperationException>(() => snapshots.GetOwnedTerminalAsync(fixture.Player, snapshot.RoomId, fixture.Match, Ct));
    }

    private static SeasonDefinition Define() => SeasonDefinition.FromCalendarDays("original", new DateOnly(2026, 11, 2), GameConfigCatalog.Current.Version, "original-stats", highestOpenDifficulty: 5);
    private static async Task<Guid> PlayerAsync(PostgresTestSchema db, Clock clock)
    {
        var key = Guid.NewGuid().ToString("N");
        return (await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(key,
            "Room " + key[..12], RandomNumberGenerator.GetBytes(32), clock.Now, clock.Now.AddHours(1), Ct)).UserId;
    }
    private static async Task<(BattleRoom Room, Guid Match, Guid Player)> RoomAsync(PostgresTestSchema db, Clock clock, SeasonContext context)
    {
        var player = await PlayerAsync(db, clock);
        var room = new BattleRoom(Guid.NewGuid(), context.ConfigVersion, CombatCardCatalog.CreatePrototype(), 73, season: context);
        room.AddPlayer(new(player, HeroClass.Mage, Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        var match = Guid.NewGuid();
        await Sql(db, """
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm',$3,73,$4,'Running',$5,$6,$7,$8)
            """, match, room.RoomId, context.DifficultyId, context.ConfigVersion, clock.Now, context.SeasonId, context.RulesetId, context.StatsVersion);
        await Sql(db, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", match, player);
        return (room, match, player);
    }
    private static async Task Sql(PostgresTestSchema db, string sql, params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
