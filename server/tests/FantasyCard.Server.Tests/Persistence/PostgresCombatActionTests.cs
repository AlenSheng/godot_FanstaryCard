using System.Security.Cryptography;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresCombatActionTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AckPersistsActionAndRouterAndRoomRecreationCannotRepeatItOrResetCooldown()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var fixture = await Setup(db);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource, fixture.Clock, metrics);
        ClientCommand command;
        await using (var rooms = new RoomRegistry(fixture.Clock))
        {
            rooms.Register(fixture.Room, fixture.Match, startTicker: false);
            command = Command(fixture, "first");
            var router = Router(fixture, rooms, snapshots);
            var response = await router.RouteAsync(fixture.Player, RoundTrip(command), "trace", Ct);
            var result = Assert.IsType<BattleComboResolvedEventPayload>(response.Single(e => e.Type == "battle.combo_resolved").Payload);
            Assert.False(result.ActionReplayed);
            Assert.Equal(((BattlePlayCardsCommandPayload)command.Payload!).CombatActionId, result.CombatActionId);
            var saved = await snapshots.GetAsync(fixture.Room.RoomId, Ct);
            Assert.Equal(1, saved!.Players.Single(p => p.PlayerId == fixture.Player.UserId).LastCombatActionSequence);
            var raw = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", fixture.Room.RoomId);
            var replay = await Router(fixture, rooms, snapshots).RouteAsync(fixture.Player,
                command with { RequestId = "router-recreated", ExpectedRevision = long.MaxValue }, "trace", Ct);
            Assert.True(Assert.IsType<BattleComboResolvedEventPayload>(replay.Single(e => e.Type == "battle.combo_resolved").Payload).ActionReplayed);
            Assert.Equal(raw, await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", fixture.Room.RoomId));
        }
        await using var restoredRooms = new RoomRegistry(fixture.Clock);
        var recovery = new RoomRecoveryState();
        await new RoomRecoveryWorker(snapshots, restoredRooms, recovery, fixture.Clock, NullLogger<RoomRecoveryWorker>.Instance).StartAsync(Ct);
        Assert.True(recovery.Capture().IsHealthy);
        var afterRestart = await Router(fixture, restoredRooms, snapshots).RouteAsync(fixture.Player,
            command with { RequestId = "after-cold-recovery" }, "trace", Ct);
        Assert.True(Assert.IsType<BattleComboResolvedEventPayload>(afterRestart.Single(e => e.Type == "battle.combo_resolved").Payload).ActionReplayed);
        var projected = Assert.IsType<RoomSnapshotEventPayload>(afterRestart[^1].Payload);
        Assert.Equal(2, projected.Player.CombatAction!.NextSequence);
        Assert.Equal(500, projected.Player.CombatAction.RemainingMs);
        Assert.Equal(fixture.Room.Capture().Players.Single(p => p.PlayerId == fixture.Player.UserId).Combat.Deck.Discard.Count, projected.Player.DiscardCount);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task OwnedTerminalFallbackReplaysThePersistedActionWithoutRegisteringOrMutatingARoom()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var fixture = await Setup(db);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource, fixture.Clock, metrics);
        var command = Command(fixture, "first");
        await using (var rooms = new RoomRegistry(fixture.Clock))
        {
            var actor = rooms.Register(fixture.Room, fixture.Match, startTicker: false);
            await Router(fixture, rooms, snapshots).RouteAsync(fixture.Player, command, "trace", Ct);
            var terminal = await actor.ExecuteAsync(new AbandonBattleCommand(fixture.Player.UserId), Ct);
            await snapshots.SaveIfDueAsync(terminal, Ct);
            await new SettlementCoordinator(new SettlementRepository(db.DataSource, fixture.Clock, metrics), fixture.Clock).ObserveAsync(fixture.Match, terminal);
        }
        var before = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", fixture.Room.RoomId);
        await using var absent = new RoomRegistry(fixture.Clock);
        var response = await Router(fixture, absent, snapshots).RouteAsync(fixture.Player,
            command with { RequestId = "terminal-retry" }, "trace", Ct);
        var result = Assert.IsType<BattleComboResolvedEventPayload>(response.Single(e => e.Type == "battle.combo_resolved").Payload);
        Assert.True(result.ActionReplayed);
        Assert.Empty(absent.GetRoomIds());
        Assert.Equal(before, await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", fixture.Room.RoomId));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", fixture.Match));
    }

    private static RealtimeCommandRouter Router(Fixture f, RoomRegistry rooms, RoomSnapshotRepository snapshots) =>
        new(new RealtimeEventStore(f.Clock), f.Clock, rooms, roomSnapshotRepository: snapshots);
    private static ClientCommand RoundTrip(ClientCommand command) => RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(command));
    private static ClientCommand Command(Fixture fixture, string request)
    {
        var player = fixture.Room.GetPlayer(fixture.Player.UserId);
        var snapshot = player.Combat.Deck.Capture();
        var all = snapshot.Hand.Concat(snapshot.Library).Concat(snapshot.Discard).ToArray();
        var chosen = all.Single(c => c.CardId == "C01");
        player.Combat.Deck.Restore(new([chosen], all.Where(c => c.InstanceId != chosen.InstanceId).ToArray(), [], 0));
        return new("battle.play_cards", request, fixture.Room.Revision,
            new BattlePlayCardsCommandPayload(player.Pve!.BattleId, player.Pve.CurrentTargetId!, [chosen.InstanceId], fixture.Room.NewCombatActionId(player.PlayerId)),
            fixture.Room.RoomId, fixture.Match);
    }
    private static async Task<Fixture> Setup(PostgresTestSchema db)
    {
        var season = SeasonDefinition.FromCalendarDays("actions", new DateOnly(2026, 11, 2), GameConfigCatalog.Current.Version, "season-equipment-v1");
        var clock = new Clock(season.StartsAtUtc);
        var seasons = new SeasonRepository(db.DataSource, clock); await seasons.PublishAsync(season, new string('a', 64), Ct);
        var key = Guid.NewGuid().ToString("N");
        var player = await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(key,
            "Action " + key[..10], RandomNumberGenerator.GetBytes(32), clock.GetUtcNow(), clock.GetUtcNow().AddHours(1), Ct);
        await seasons.EnsurePlayerAsync(player.UserId, season.ContextFor(0), Ct);
        var room = new BattleRoom(Guid.NewGuid(), season.ConfigVersion, CombatCardCatalog.Create(GameConfigCatalog.Current), 73, season: season.ContextFor(0));
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"MAG-{i:D2}")).ToArray();
        room.AddPlayer(new(player.UserId, HeroClass.Mage, cards, null)); room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        var match = Guid.NewGuid();
        await using (var command = db.DataSource.CreateCommand("""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,'actions','season-v1','season-equipment-v1')
            """))
        {
            command.Parameters.AddWithValue(match); command.Parameters.AddWithValue(room.RoomId);
            command.Parameters.AddWithValue(season.ConfigVersion); command.Parameters.AddWithValue(clock.GetUtcNow()); await command.ExecuteNonQueryAsync(Ct);
        }
        await using (var command = db.DataSource.CreateCommand("INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            command.Parameters.AddWithValue(match); command.Parameters.AddWithValue(player.UserId); await command.ExecuteNonQueryAsync(Ct);
        }
        return new(room, match, player, clock);
    }
    private sealed record Fixture(BattleRoom Room, Guid Match, PlayerProfile Player, Clock Clock);
    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period) => new InertTimer();
    }
    private sealed class InertTimer : ITimer
    {
        public bool Change(TimeSpan dueTime, TimeSpan period) => true;
        public void Dispose() { }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
