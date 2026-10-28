using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Matchmaking;

public sealed class ReadySendIsolationTests
{
    [Fact]
    public async Task One_slow_player_cannot_hold_three_ready_notifications_and_each_player_replay_stays_ordered()
    {
        var registry = new ConnectionRegistry();
        var events = new RealtimeEventStore(TimeProvider.System);
        using var metrics = new ServerMetrics();
        await using var rooms = new RoomRegistry(TimeProvider.System);
        using var coordinator = new RoomReadyCoordinator(null!, rooms, null!, events, registry,
            TimeProvider.System, NullLogger<RoomReadyCoordinator>.Instance, metrics);
        var players = Enumerable.Range(0, 4).Select(_ => Guid.NewGuid()).ToArray();
        var slow = new RecordingSocket(block: true);
        var sockets = new[] { slow, new RecordingSocket(), new RecordingSocket(), new RecordingSocket() };
        var connections = sockets.Select(socket => new RealtimeConnection(socket)).ToArray();
        for (var i = 0; i < players.Length; i++) registry.Register(players[i], connections[i]);
        var pending = new PendingMatch(Guid.NewGuid(), Guid.NewGuid(), DateTimeOffset.UtcNow.AddSeconds(15), players);
        var notifications = coordinator.NotifyRequiredAsync(pending, TestContext.Current.CancellationToken);
        var fastCompletedBeforeSlowRelease = false;
        try
        {
            await slow.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
            try
            {
                await Task.WhenAll(sockets.Skip(1).Select(socket => socket.Required.Task))
                    .WaitAsync(TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken);
                fastCompletedBeforeSlowRelease = true;
            }
            catch (TimeoutException) { }
        }
        finally { slow.Release.TrySetResult(); }
        await notifications.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        // Deliver a second notification pair, exercising the actual per-player
        // event replay journal and binary connection ordering.
        await coordinator.NotifyRequiredAsync(pending, TestContext.Current.CancellationToken);
        foreach (var socket in sockets)
        {
            Assert.Equal(["match.found", "room.ready_required", "match.found", "room.ready_required"], socket.Messages.Select(m => m.Type));
            Assert.Equal([1L, 2L, 3L, 4L], socket.Messages.Select(m => m.Sequence));
        }
        foreach (var player in players)
        {
            var replay = events.ReadAfter(player, 0).Events;
            Assert.Equal(["match.found", "room.ready_required", "match.found", "room.ready_required"], replay.Select(m => m.Type));
            Assert.Equal([1L, 2L, 3L, 4L], replay.Select(m => m.Sequence));
        }
        foreach (var connection in connections) await connection.DisposeAsync();
        Assert.True(fastCompletedBeforeSlowRelease, "Three healthy peers must receive both messages while the first peer's send remains blocked.");
    }

    private sealed class RecordingSocket(bool block = false) : WebSocket
    {
        private WebSocketState _state = WebSocketState.Open;
        public List<ServerEvent> Messages { get; } = [];
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Required { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public override WebSocketCloseStatus? CloseStatus => null;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() => _state = WebSocketState.Closed;
        public override Task CloseAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) => Task.CompletedTask;
        public override Task CloseOutputAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) => Task.CompletedTask;
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct) => throw new NotSupportedException();
        public override async Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool end, CancellationToken ct)
        {
            Entered.TrySetResult();
            if (block) await Release.Task.WaitAsync(ct);
            var message = RealtimeProtobufCodec.DecodeServer(buffer.ToArray());
            Messages.Add(message);
            if (message.Type == "room.ready_required") Required.TrySetResult();
        }
    }
}
