using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using Google.Protobuf;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class TerminalCommandContextTests
{
    [Fact]
    public async Task Scoped_late_mutation_is_cancelled_without_applying_or_acknowledging()
    {
        var player = PlayerProfile.Create(Guid.NewGuid(), "Terminal", DateTimeOffset.UtcNow);
        var room = CreateRoom(player.UserId);
        var matchId = Guid.NewGuid();
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, matchId, startTicker: false);
        room.AbandonBattle(player.UserId);
        var before = room.Capture();
        var router = new RealtimeCommandRouter(new RealtimeEventStore(TimeProvider.System), TimeProvider.System, registry);
        var command = new ClientCommand("battle.play_cards", "late-card", room.Revision,
            new BattlePlayCardsCommandPayload(Guid.NewGuid(), "invalid-target", [Guid.NewGuid()]), room.RoomId, matchId);

        var response = await router.RouteAsync(player, command, "trace", TestContext.Current.CancellationToken);
        var replay = await router.RouteAsync(player, command, "trace", TestContext.Current.CancellationToken);

        Assert.Collection(response,
            cancelled =>
            {
                Assert.Equal("room.command_cancelled", cancelled.Type);
                var payload = Assert.IsType<RoomCommandCancelledEventPayload>(cancelled.Payload);
                Assert.Equal((room.RoomId, matchId, command.Type, "RoomEndedBeforeApply"),
                    (payload.RoomId, payload.MatchId, payload.CommandType, payload.Reason));
            },
            snapshot => Assert.Equal("room.snapshot", snapshot.Type));
        Assert.All(response, message => Assert.Equal(command.RequestId, message.RequestId));
        Assert.Equivalent(response, replay, strict: true);
        var changedScope = await router.RouteAsync(player, command with { MatchId = Guid.NewGuid() },
            "trace", TestContext.Current.CancellationToken);
        Assert.Equal("REQUEST_ID_REUSED", Assert.IsType<CommandRejectedEventPayload>(Assert.Single(changedScope).Payload).Code);
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.DoesNotContain(response, message => message.Type == "battle.combo_resolved");
    }

    [Theory]
    [InlineData(RoomPlayerPhase.Dead)]
    [InlineData(RoomPlayerPhase.Extracted)]
    public void Terminal_phase_fences_mutation_before_any_side_effect(RoomPlayerPhase phase)
    {
        var playerId = Guid.NewGuid();
        var active = CreateRoom(playerId);
        var snapshot = active.Capture();
        var room = BattleRoom.Restore(snapshot with
        {
            Players = snapshot.Players.Select(value => value with { Phase = phase, Pve = null }).ToArray()
        }, CombatCardCatalog.CreatePrototype(), 17);
        var before = room.Capture();
        var exception = Assert.Throws<RoomAlreadyEndedException>(() =>
            new ExecuteWithClientStateCommand<BattleRoomSnapshot>(new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(5)), playerId).Execute(room));
        Assert.Equal(phase, Assert.Single(exception.State.Snapshot.Players).Phase);
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Fact]
    public async Task Old_match_scope_cannot_execute_against_the_new_active_room()
    {
        var player = PlayerProfile.Create(Guid.NewGuid(), "Scope", DateTimeOffset.UtcNow);
        var room = CreateRoom(player.UserId);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, Guid.NewGuid(), startTicker: false);
        var before = room.Capture();
        var router = new RealtimeCommandRouter(new RealtimeEventStore(TimeProvider.System), TimeProvider.System, registry);
        var response = await router.RouteAsync(player,
            new ClientCommand("battle.abandon", "old-abandon", room.Revision, new BattleAbandonCommandPayload(), Guid.NewGuid(), Guid.NewGuid()),
            "trace", TestContext.Current.CancellationToken);
        Assert.Equal("NOT_IN_ROOM", Assert.IsType<CommandRejectedEventPayload>(Assert.Single(response).Payload).Code);
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Partial_or_empty_scope_is_rejected(bool empty)
    {
        var player = PlayerProfile.Create(Guid.NewGuid(), "Scope", DateTimeOffset.UtcNow);
        var router = new RealtimeCommandRouter(new RealtimeEventStore(TimeProvider.System), TimeProvider.System);
        var response = await router.RouteAsync(player,
            new ClientCommand("room.snapshot.read", "invalid-scope", null, new RoomSnapshotCommandPayload(), empty ? Guid.Empty : Guid.NewGuid(), empty ? Guid.Empty : null),
            "trace", TestContext.Current.CancellationToken);
        Assert.Equal("INVALID_ROOM_CONTEXT", Assert.IsType<CommandRejectedEventPayload>(Assert.Single(response).Payload).Code);
    }

    [Fact]
    public async Task Closed_actor_has_distinct_failure_and_never_runs_the_command()
    {
        var room = CreateRoom(Guid.NewGuid());
        var actor = new RoomActor(room, TimeProvider.System, startTicker: false);
        await actor.DisposeAsync();
        var exception = await Assert.ThrowsAsync<RoomActorClosedException>(async () =>
            await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(1)), TestContext.Current.CancellationToken));
        Assert.Equal(room.RoomId, exception.RoomId);
        Assert.Equal(TimeSpan.Zero, room.Elapsed);
    }

    [Fact]
    public void Scope_and_terminal_events_preserve_protobuf_round_trips_and_legacy_defaults()
    {
        var roomId = Guid.NewGuid();
        var matchId = Guid.NewGuid();
        var command = new ClientCommand("room.snapshot.read", "read", null, new RoomSnapshotCommandPayload(), roomId, matchId);
        Assert.Equivalent(command, RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(command)), strict: true);
        var official = FantasyCard.Contracts.Wire.Realtime.V1.ClientEnvelope.Parser.ParseFrom(RealtimeProtobufCodec.EncodeClient(command));
        Assert.Equal(roomId.ToString("D"), official.RoomId);
        Assert.Equal(matchId.ToString("D"), official.MatchId);
        Assert.Equivalent(command, RealtimeProtobufCodec.DecodeClient(official.ToByteArray()), strict: true);
        var legacy = command with { RoomId = null, MatchId = null };
        Assert.Equivalent(legacy, RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(legacy)), strict: true);
        (string Type, object Payload)[] payloads =
        [
            ("player.died", new PlayerDiedEventPayload(Guid.NewGuid(), "PveDeath", null, roomId, matchId)),
            ("action.extract_completed", new ActionExtractEventPayload("Completed", TimeSpan.Zero, roomId, matchId)),
            ("room.command_cancelled", new RoomCommandCancelledEventPayload(roomId, matchId, "battle.play_cards", "RoomEndedBeforeApply"))
        ];
        foreach (var (type, payload) in payloads)
        {
            var original = new ServerEvent(type, "trace", payload, "event", 1, DateTimeOffset.UnixEpoch, "read", 10);
            Assert.Equivalent(original, RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(original)), strict: true);
            var envelope = FantasyCard.Contracts.Wire.Realtime.V1.ServerEnvelope.Parser.ParseFrom(RealtimeProtobufCodec.EncodeServer(original));
            if (type == "room.command_cancelled")
            {
                var cancellation = FantasyCard.Contracts.Wire.Realtime.V1.RoomCommandCancelledEvent.Parser.ParseFrom(envelope.Payload);
                Assert.Equal(roomId.ToString("D"), cancellation.RoomId);
                Assert.Equal(matchId.ToString("D"), cancellation.MatchId);
                Assert.Equal("battle.play_cards", cancellation.CommandType);
            }
        }
    }

    private static BattleRoom CreateRoom(Guid playerId)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 17);
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(17, 1));
        return room;
    }
}
