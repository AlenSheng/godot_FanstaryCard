using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class ConnectionReplacementTests
{
    [Theory]
    [InlineData("disposed")]
    [InlineData("broken")]
    [InlineData("stalled-send")]
    [InlineData("stalled-close")]
    [InlineData("healthy")]
    public async Task OldPeerCannotPreventReplacementFromSendingConnected(string failure)
    {
        var playerId = Guid.NewGuid();
        var registry = new ConnectionRegistry();
        var oldSocket = new TestSocket(failure);
        await using var oldConnection = new RealtimeConnection(oldSocket);
        registry.Register(playerId, oldConnection);
        if (failure == "disposed") await oldConnection.DisposeAsync();

        var newSocket = new TestSocket("healthy");
        await using var newConnection = new RealtimeConnection(newSocket);
        var replaced = registry.Register(playerId, newConnection);
        Assert.NotNull(replaced);
        Assert.Same(oldConnection, replaced);
        await replaced.RetireAsync(Event("session.replaced", new SessionReplacedEventPayload("newer_connection")))
            .WaitAsync(TimeSpan.FromSeconds(3), TestContext.Current.CancellationToken);

        // The old request's finally must not remove its successor.
        Assert.False(registry.Unregister(playerId, oldConnection));
        Assert.True(registry.IsConnected(playerId));
        await newConnection.SendAsync(Event("session.connected", new SessionConnectedEventPayload(playerId)),
            TestContext.Current.CancellationToken);
        Assert.Equal("session.connected", RealtimeProtobufCodec.DecodeServer(Assert.Single(newSocket.Messages)).Type);
        Assert.Equal(WebSocketState.Open, newSocket.State);
        Assert.True(registry.Unregister(playerId, newConnection));
        Assert.False(registry.IsConnected(playerId));
    }

    private static ServerEvent Event(string type, object payload) =>
        new(type, "replacement-test", payload, "event", 1, DateTimeOffset.UnixEpoch);

    private sealed class TestSocket(string failure) : WebSocket
    {
        private WebSocketState _state = WebSocketState.Open;
        public List<byte[]> Messages { get; } = [];
        public override WebSocketCloseStatus? CloseStatus => null;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() => _state = WebSocketState.Closed;
        public override async Task CloseAsync(WebSocketCloseStatus closeStatus, string? statusDescription, CancellationToken cancellationToken)
        {
            if (failure == "stalled-close") await Task.Delay(Timeout.Infinite, cancellationToken);
            _state = WebSocketState.Closed;
        }
        public override Task CloseOutputAsync(WebSocketCloseStatus closeStatus, string? statusDescription, CancellationToken cancellationToken) =>
            CloseAsync(closeStatus, statusDescription, cancellationToken);
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken cancellationToken) => throw new NotSupportedException();
        public override async Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType messageType, bool endOfMessage, CancellationToken cancellationToken)
        {
            if (failure == "broken") throw new WebSocketException(WebSocketError.ConnectionClosedPrematurely);
            if (failure == "stalled-send") await Task.Delay(Timeout.Infinite, cancellationToken);
            Messages.Add(buffer.ToArray());
        }
    }
}
