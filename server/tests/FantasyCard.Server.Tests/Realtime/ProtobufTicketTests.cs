using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class ProtobufTicketTests(ITestOutputHelper output)
{
    [Fact]
    public async Task TicketConsumptionIsAtomicAndBoundToSession()
    {
        var store = new RealtimeTicketStore(TimeProvider.System);
        var player = Guid.NewGuid();
        var hash = new byte[] { 1, 2, 3 };
        var ticket = Assert.IsType<IssuedRealtimeTicket>(store.Issue(player, hash));
        hash[0] = 9;
        var results = await Task.WhenAll(Enumerable.Range(0, 32).Select(_ => Task.Run(() => store.Consume(ticket.Ticket), TestContext.Current.CancellationToken)));
        var consumed = Assert.Single(results, result => result is not null)!;
        Assert.Equal(player, consumed.PlayerId);
        Assert.Equal(new byte[] { 1, 2, 3 }, consumed.SessionHash);
    }

    [Fact]
    public void ExpiredReissuedAndMalformedTicketsAreRejected()
    {
        var clock = new TicketClock();
        var store = new RealtimeTicketStore(clock);
        var player = Guid.NewGuid();
        var first = store.Issue(player, [1])!;
        var next = store.Issue(player, [2])!;
        Assert.Null(store.Consume(first.Ticket));
        clock.Now += RealtimeTicketStore.Lifetime;
        Assert.Null(store.Consume(next.Ticket));
        Assert.Null(store.Consume(null));
        Assert.Null(store.Consume(new string('x', 257)));
        Assert.False(new RealtimeOptions().AllowLegacyAccessTokenQuery);
    }

    [Fact]
    public async Task FragmentedReceiveKeepsTheCumulativeLimit()
    {
        using var socket = new BudgetSocket();
        socket.Fragments.Enqueue((new byte[8192], false));
        socket.Fragments.Enqueue((new byte[8192], false));
        var result = await RealtimeEndpoints.ReceiveAsync(socket, TestContext.Current.CancellationToken);
        Assert.Equal(RealtimeEndpoints.ReceiveStatus.TooLarge, result.Status);
        socket.Fragments.Enqueue((new byte[8192], false));
        socket.Fragments.Enqueue((new byte[8192], true));
        result = await RealtimeEndpoints.ReceiveAsync(socket, TestContext.Current.CancellationToken);
        Assert.Equal(RealtimeEndpoints.ReceiveStatus.Complete, result.Status);
        Assert.Equal(16384, result.Payload!.Length);
    }

    [Fact]
    public async Task PendingSendLimitAbortsSlowPeer()
    {
        using var socket = new BudgetSocket();
        await using var connection = new RealtimeConnection(socket);
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        var pending = Enumerable.Range(0, RealtimeConnection.MaximumPendingSends)
            .Select(_ => connection.SendAsync(Event("pong", new PongEventPayload(DateTimeOffset.UnixEpoch)), cancellation.Token)).ToArray();
        await Assert.ThrowsAsync<WebSocketException>(() => connection.SendAsync(Event("pong", new PongEventPayload(DateTimeOffset.UnixEpoch)), cancellation.Token));
        Assert.Equal(WebSocketState.Aborted, socket.State);
        await cancellation.CancelAsync();
        try { await Task.WhenAll(pending); }
        catch (OperationCanceledException) { }
        Assert.All(pending, task => Assert.True(task.IsCompleted));
    }

    private sealed class BudgetSocket : WebSocket
    {
        private WebSocketState _state = WebSocketState.Open;
        public Queue<(byte[] Bytes, bool End)> Fragments { get; } = new();
        public override WebSocketCloseStatus? CloseStatus => null;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() => _state = WebSocketState.Closed;
        public override Task CloseAsync(WebSocketCloseStatus closeStatus, string? statusDescription, CancellationToken cancellationToken) => Task.CompletedTask;
        public override Task CloseOutputAsync(WebSocketCloseStatus closeStatus, string? statusDescription, CancellationToken cancellationToken) => Task.CompletedTask;
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken cancellationToken)
        {
            var (bytes, end) = Fragments.Dequeue();
            bytes.AsSpan().CopyTo(buffer.AsSpan());
            return Task.FromResult(new WebSocketReceiveResult(bytes.Length, WebSocketMessageType.Binary, end));
        }
        public override Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType messageType, bool endOfMessage, CancellationToken cancellationToken) =>
            Task.Delay(Timeout.Infinite, cancellationToken);
    }

    [Fact]
    public void MalformedFrameFloodConsumesBudgetAndBoundsErrorResponses()
    {
        var reader = new RealtimeFrameReader(3);
        var now = DateTimeOffset.UnixEpoch;
        // An unfinished varint is invalid regardless of the payload message type.
        var frames = Enumerable.Range(0, 100).Select(_ => reader.Read([0x80], now)).ToArray();
        Assert.Equal(3, frames.Count(frame => frame.ErrorType == "error.invalid_message"));
        Assert.Equal(1, frames.Count(frame => frame.ErrorType == "error.rate_limited"));
        Assert.Equal(97, frames.Count(frame => frame.RateLimited));
        Assert.All(frames, frame => Assert.Null(frame.Command));
        var ping = RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", "budget", null, null));
        Assert.True(reader.Read(ping, now).RateLimited);
        Assert.NotNull(reader.Read(ping, now.AddSeconds(1)).Command);
        Assert.Equal("error.invalid_message", reader.Read([0x80], now.AddSeconds(1)).ErrorType);
    }

    [Fact]
    public void Owned_test_frame_bypass_keeps_protobuf_validation()
    {
        var reader = new RealtimeFrameReader(1, ownedTestBypass: true);
        var now = DateTimeOffset.UnixEpoch;
        foreach (var _ in Enumerable.Range(0, 100))
        {
            var invalid = reader.Read([0x80], now);
            Assert.False(invalid.RateLimited);
            Assert.Null(invalid.Command);
            Assert.Equal("error.invalid_message", invalid.ErrorType);
        }
        var ping = RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", "owned-test", null, null));
        foreach (var _ in Enumerable.Range(0, 100)) Assert.NotNull(reader.Read(ping, now).Command);
    }

    private sealed class TicketClock : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = DateTimeOffset.UnixEpoch;
        public override DateTimeOffset GetUtcNow() => Now;
    }

    [Fact]
    public void AuthoritativeSnapshotAndRelicBudgetMeasured()
    {
        var room = CreateRoom(out var playerId);
        var snapshot = room.Capture();
        var player = snapshot.Players.Single();
        var armor = Enumerable.Range(0, 36).Select(index => new ExplorationItem(
            Guid.NewGuid().ToString("D"), ExplorationItemKind.Equipment, 1, index >= 33,
            new("Head", "Purple", "Metal", "Piercing", "DrawInterval", 5, true), index)).ToArray();
        var piles = Enumerable.Range(0, 4).Select(index => new RelicPileSnapshot(Guid.NewGuid(), Guid.NewGuid().ToString("D"),
            player.Position!.Value, 2, Enumerable.Range(0, 41).Select(item => armor[item % armor.Length] with
            { ItemId = Guid.NewGuid().ToString("D"), SlotIndex = -1, IsSafe = false }).ToArray(), new string('旅', 20))).ToArray();
        snapshot = snapshot with
        {
            Players = [player with { Phase = RoomPlayerPhase.ActionBar, Pve = null,
                Inventory = new(36, 3, armor, SafeSlotIndexes: [33, 34, 35]) }],
            RelicPiles = piles
        };
        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 37);
        var projection = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(playerId).Execute(restored), playerId, null, DateTimeOffset.UnixEpoch);
        projection = projection with { Player = projection.Player with
        { Hand = [new(Guid.NewGuid(), "M-BOXSPIRIT", ElementOverride: "None"), new(Guid.NewGuid(), "M-BOXSPIRIT", ElementOverride: "Metal")] } };
        Assert.Equal(36, projection.Player.InventoryCapacity);
        Assert.Equal([33, 34, 35], projection.Player.SafeSlotIndexes);
        Assert.All(projection.CurrentCell.RelicPiles!, pile => Assert.Empty(pile.Items));
        Assert.Equal(4, projection.CurrentCell.RelicPiles!.Count);
        var snapshotBytes = RealtimeProtobufCodec.EncodeServer(Event("room.snapshot", projection));
        output.WriteLine($"Snapshot bytes: {snapshotBytes.Length}");
        Assert.True(snapshotBytes.Length <= RealtimeConnection.MaximumOutboundBytes);
        var roundTrip = Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(snapshotBytes).Payload);
        Assert.Equal("None", roundTrip.Player.Hand[0].ElementOverride);
        Assert.Equal("Metal", roundTrip.Player.Hand[1].ElementOverride);
        var pile = piles[0];
        var detail = new RoomRelicPilePayload(pile.PileId, pile.VictimName!, pile.Version, pile.Items.Select(RoomSnapshotProjection.ToInventoryItem).ToArray());
        var bytes = RealtimeProtobufCodec.EncodeServer(Event("relic.contents", detail));
        output.WriteLine($"Relic bytes: {bytes.Length}");
        Assert.True(bytes.Length <= RealtimeConnection.MaximumOutboundBytes);
        Assert.Equivalent(detail, RealtimeProtobufCodec.DecodeServer(bytes).Payload, strict: true);
    }

    private static BattleRoom CreateRoom(out Guid playerId)
    {
        playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 37);
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Range(1, 20).Select(index => $"C{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 1));
        return room;
    }

    private static ServerEvent Event(string type, object payload) => new(type, "test", payload, "event", 1, DateTimeOffset.UnixEpoch, "request", 16);
}
