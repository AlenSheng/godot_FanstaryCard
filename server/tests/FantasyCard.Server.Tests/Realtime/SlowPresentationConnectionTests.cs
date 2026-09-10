using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class SlowPresentationConnectionTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task StalledFeedbackSendAbortsOnlyItsConnectionAndReleasesTheCaller(bool replaceWhileSending)
    {
        var playerId = Guid.NewGuid();
        var registry = new ConnectionRegistry();
        var socket = new StalledSocket();
        await using var connection = new RealtimeConnection(socket);
        registry.Register(playerId, connection);
        var pending = registry.SendPresentationAsync(playerId,
            new("pong", "test", new PongEventPayload(DateTimeOffset.UnixEpoch), "event", 1, DateTimeOffset.UnixEpoch));
        await using var replacement = new RealtimeConnection(new StalledSocket());
        if (replaceWhileSending) registry.Register(playerId, replacement);
        Assert.False(await pending.WaitAsync(TimeSpan.FromSeconds(3), TestContext.Current.CancellationToken));
        Assert.Equal(WebSocketState.Aborted, socket.State);
        Assert.Equal(replaceWhileSending, registry.IsConnected(playerId));
        Assert.Equal(WebSocketState.Open, replacement.Socket.State);
    }

    private sealed class StalledSocket : WebSocket
    {
        private WebSocketState _state = WebSocketState.Open;
        public override WebSocketCloseStatus? CloseStatus => null;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() => _state = WebSocketState.Closed;
        public override Task CloseAsync(WebSocketCloseStatus closeStatus, string? statusDescription, CancellationToken cancellationToken) => Task.CompletedTask;
        public override Task CloseOutputAsync(WebSocketCloseStatus closeStatus, string? statusDescription, CancellationToken cancellationToken) => Task.CompletedTask;
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken cancellationToken) => throw new NotSupportedException();
        public override Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType messageType, bool endOfMessage, CancellationToken cancellationToken) =>
            Task.Delay(Timeout.Infinite, cancellationToken);
    }
}
