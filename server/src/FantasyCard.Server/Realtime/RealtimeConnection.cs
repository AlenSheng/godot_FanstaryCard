using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Realtime;

public sealed class RealtimeConnection(WebSocket socket) : IAsyncDisposable
{
    private readonly SemaphoreSlim _sendGate = new(1, 1);
    public WebSocket Socket { get; } = socket;

    public const int MaximumOutboundBytes = 16 * 1024;
    public const int MaximumPendingSends = 32;
    private int _pendingSends;

    public async Task SendAsync(ServerEvent message, CancellationToken cancellationToken)
    {
        if (Interlocked.Increment(ref _pendingSends) > MaximumPendingSends)
        {
            Interlocked.Decrement(ref _pendingSends);
            Socket.Abort();
            throw new WebSocketException(WebSocketError.ConnectionClosedPrematurely);
        }
        try
        {
            var bytes = RealtimeProtobufCodec.EncodeServer(message);
            if (bytes.Length > MaximumOutboundBytes)
            {
                await CloseAsync(WebSocketCloseStatus.MessageTooBig, "Realtime response exceeds 16 KiB", cancellationToken);
                throw new WebSocketException(WebSocketError.ConnectionClosedPrematurely);
            }
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            await _sendGate.WaitAsync(timeout.Token);
            try
            {
                if (Socket.State == WebSocketState.Open)
                    await Socket.SendAsync(bytes, WebSocketMessageType.Binary, true, timeout.Token);
            }
            finally { _sendGate.Release(); }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            Socket.Abort();
            throw new WebSocketException(WebSocketError.ConnectionClosedPrematurely);
        }
        catch (OperationCanceledException)
        {
            Socket.Abort();
            throw;
        }
        finally { Interlocked.Decrement(ref _pendingSends); }
    }

    public async Task CloseAsync(WebSocketCloseStatus status, string description, CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMilliseconds(500));
        try
        {
            await _sendGate.WaitAsync(timeout.Token);
            try
            {
                if (Socket.State is WebSocketState.Open or WebSocketState.CloseReceived)
                    await Socket.CloseOutputAsync(status, description, timeout.Token);
            }
            finally { _sendGate.Release(); }
        }
        catch (OperationCanceledException) { Socket.Abort(); }
    }

    public async Task RetireAsync(ServerEvent replacement)
    {
        // A killed process cannot complete a close handshake. An already
        // disposed peer must never prevent its replacement from connecting.
        using var timeout = new CancellationTokenSource(TimeSpan.FromMilliseconds(500));
        try
        {
            await SendAsync(replacement, timeout.Token);
            await CloseAsync(WebSocketCloseStatus.PolicyViolation,
                "Replaced by a newer connection", timeout.Token);
        }
        catch (Exception exception) when (exception is WebSocketException or ObjectDisposedException or OperationCanceledException)
        {
            try { Socket.Abort(); }
            catch (ObjectDisposedException) { }
        }
    }

    public ValueTask DisposeAsync()
    {
        // Pending producers may still release the gate after the socket is closed.
        Socket.Dispose();
        return ValueTask.CompletedTask;
    }
}
