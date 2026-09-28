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
    private readonly CancellationTokenSource _closeDeadline = new();
    internal CancellationToken CloseDeadline => _closeDeadline.Token;

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
                {
                    await Socket.CloseOutputAsync(status, description, timeout.Token);
                    // Keep the sole receive loop alive to consume the peer acknowledgement.
                    // Cancelling it immediately aborts ManagedWebSocket and can reset TCP
                    // before the peer observes the close frame (especially on Linux).
                    _closeDeadline.CancelAfter(TimeSpan.FromSeconds(2));
                }
            }
            finally { _sendGate.Release(); }
        }
        catch (OperationCanceledException) { Socket.Abort(); }
    }

    internal async Task CompleteCloseHandshakeAsync()
    {
        // Called only after the application's receive loop has stopped.
        var buffer = new byte[MaximumOutboundBytes];
        try
        {
            while (Socket.State == WebSocketState.CloseSent)
                await Socket.ReceiveAsync(buffer.AsMemory(), CloseDeadline);
        }
        catch (OperationCanceledException) { Socket.Abort(); }
        catch (WebSocketException) { Socket.Abort(); }
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
        _closeDeadline.Dispose();
        return ValueTask.CompletedTask;
    }
}
