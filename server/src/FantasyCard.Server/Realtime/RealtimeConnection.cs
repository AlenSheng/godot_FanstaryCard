using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Realtime;

public sealed class RealtimeConnection(WebSocket socket) : IAsyncDisposable
{
    private readonly SemaphoreSlim _sendGate = new(1, 1);
    public WebSocket Socket { get; } = socket;

    public async Task SendAsync(ServerEvent message, CancellationToken cancellationToken)
    {
        var bytes = RealtimeProtobufCodec.EncodeServer(message);
        await _sendGate.WaitAsync(cancellationToken);
        try
        {
            if (Socket.State == WebSocketState.Open)
                await Socket.SendAsync(bytes, WebSocketMessageType.Binary, true, cancellationToken);
        }
        finally { _sendGate.Release(); }
    }

    public async Task CloseAsync(WebSocketCloseStatus status, string description, CancellationToken cancellationToken)
    {
        if (Socket.State is WebSocketState.Open or WebSocketState.CloseReceived)
            await Socket.CloseAsync(status, description, cancellationToken);
    }

    public ValueTask DisposeAsync()
    {
        _sendGate.Dispose();
        Socket.Dispose();
        return ValueTask.CompletedTask;
    }
}