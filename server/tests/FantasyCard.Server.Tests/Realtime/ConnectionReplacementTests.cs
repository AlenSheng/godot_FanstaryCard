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

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Server_close_preserves_receive_until_ack_or_bounded_deadline(bool acknowledge)
    {
        var socket = new HandshakeSocket();
        await using var connection = new RealtimeConnection(socket);
        await connection.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Revoked", TestContext.Current.CancellationToken);
        Assert.Equal(WebSocketState.CloseSent, socket.State);
        Assert.False(connection.CloseDeadline.IsCancellationRequested);
        var handshake = connection.CompleteCloseHandshakeAsync();
        // A deterministic scheduler gate: the receive must remain pending, rather than
        // being cancelled immediately after writing the close frame.
        Assert.False(handshake.IsCompleted);
        await connection.SendAsync(Event("session.connected", new SessionConnectedEventPayload(Guid.NewGuid())),
            TestContext.Current.CancellationToken);
        Assert.Equal(0, socket.SentMessages);
        if (acknowledge) socket.Acknowledge();
        await handshake.WaitAsync(TimeSpan.FromSeconds(5), TestContext.Current.CancellationToken);
        Assert.Equal(acknowledge ? WebSocketState.Closed : WebSocketState.Aborted, socket.State);
    }

    private sealed class HandshakeSocket : WebSocket
    {
        private readonly TaskCompletionSource _ack = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private WebSocketState _state = WebSocketState.Open;
        public int SentMessages { get; private set; }
        public override WebSocketCloseStatus? CloseStatus => WebSocketCloseStatus.PolicyViolation;
        public override string? CloseStatusDescription => "Revoked";
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public void Acknowledge() => _ack.TrySetResult();
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() { }
        public override Task CloseAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) =>
            throw new NotSupportedException("Only the existing receive loop owns the handshake.");
        public override Task CloseOutputAsync(WebSocketCloseStatus status, string? description, CancellationToken ct)
        {
            _state = WebSocketState.CloseSent;
            return Task.CompletedTask;
        }
        public override async Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct)
        {
            await _ack.Task.WaitAsync(ct);
            _state = WebSocketState.Closed;
            return new WebSocketReceiveResult(0, WebSocketMessageType.Close, true);
        }
        public override Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool end, CancellationToken ct)
        {
            SentMessages++;
            return Task.CompletedTask;
        }
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
