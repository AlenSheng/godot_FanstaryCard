using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class OutboundSizeBoundaryTests(ITestOutputHelper output)
{
    [Fact]
    public async Task Exactly_16KiB_sends_but_one_byte_more_closes_before_socket_write()
    {
        var length = RealtimeConnection.MaximumOutboundBytes - 200;
        ServerEvent Message(int n) => new("error.command_rejected", "size", new CommandRejectedEventPayload("BOUNDARY", new string('x', n)), "size-event", 1, DateTimeOffset.UnixEpoch);
        while (RealtimeProtobufCodec.EncodeServer(Message(length)).Length < RealtimeConnection.MaximumOutboundBytes) length++;
        var exact = Message(length);
        var over = Message(length + 1);
        Assert.Equal(RealtimeConnection.MaximumOutboundBytes, RealtimeProtobufCodec.EncodeServer(exact).Length);
        Assert.Equal(RealtimeConnection.MaximumOutboundBytes + 1, RealtimeProtobufCodec.EncodeServer(over).Length);
        using var socket = new RecordingSocket();
        await using var connection = new RealtimeConnection(socket);
        await connection.SendAsync(exact, TestContext.Current.CancellationToken);
        Assert.Equal(1, socket.Writes);
        await Assert.ThrowsAsync<WebSocketException>(() => connection.SendAsync(over, TestContext.Current.CancellationToken));
        Assert.Equal(1, socket.Writes);
        Assert.Equal(WebSocketCloseStatus.MessageTooBig, socket.CloseStatus);
        output.WriteLine($"PR13_OUTBOUND exact={RealtimeConnection.MaximumOutboundBytes} over={RealtimeConnection.MaximumOutboundBytes+1} writes={socket.Writes}");
    }

    private sealed class RecordingSocket : WebSocket
    {
        private WebSocketState _state = WebSocketState.Open;
        private WebSocketCloseStatus? _close;
        public int Writes { get; private set; }
        public override WebSocketCloseStatus? CloseStatus => _close;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() => _state = WebSocketState.Closed;
        public override Task CloseAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) => CloseOutputAsync(status,description,ct);
        public override Task CloseOutputAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) { _close=status;_state=WebSocketState.CloseSent;return Task.CompletedTask; }
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct) => throw new NotSupportedException();
        public override Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool end, CancellationToken ct) { Writes++;return Task.CompletedTask; }
    }
}
