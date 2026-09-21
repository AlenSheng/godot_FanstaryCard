using System.Collections.Concurrent;

namespace FantasyCard.Server.Realtime;

public sealed class ConnectionRegistry
{
    private readonly ConcurrentDictionary<Guid, RealtimeConnection> _connections = new();

    public RealtimeConnection? Register(Guid playerId, RealtimeConnection connection)
    {
        RealtimeConnection? replaced = null;
        _connections.AddOrUpdate(
            playerId,
            connection,
            (_, current) =>
            {
                replaced = current;
                return connection;
            });
        return replaced;
    }

    public bool Unregister(Guid playerId, RealtimeConnection connection)
    {
        return _connections.TryRemove(new KeyValuePair<Guid, RealtimeConnection>(playerId, connection));
    }

    public bool IsConnected(Guid playerId) => _connections.ContainsKey(playerId);

    public IReadOnlyList<Guid> ConnectedPlayerIds => _connections.Keys.ToArray();

    public void Disconnect(Guid playerId)
    {
        if (_connections.TryGetValue(playerId, out var connection))
            connection.Socket.Abort();
    }

    public async Task<bool> SendPresentationAsync(Guid playerId, FantasyCard.Contracts.Realtime.ServerEvent message)
    {
        if (!_connections.TryGetValue(playerId, out var connection)) return false;
        using var timeout = new CancellationTokenSource(TimeSpan.FromMilliseconds(250));
        try
        {
            await connection.SendAsync(message, timeout.Token);
            return true;
        }
        catch (OperationCanceledException)
        {
            connection.Socket.Abort();
            Unregister(playerId, connection);
            return false;
        }
        catch (Exception exception) when (exception is System.Net.WebSockets.WebSocketException or ObjectDisposedException)
        {
            Unregister(playerId, connection);
            return false;
        }
    }

    public async Task<bool> SendIfConnectedAsync(
        Guid playerId,
        FantasyCard.Contracts.Realtime.ServerEvent message,
        CancellationToken cancellationToken)
    {
        if (!_connections.TryGetValue(playerId, out var connection)) return false;
        try
        {
            await connection.SendAsync(message, cancellationToken);
            return true;
        }
        catch (Exception exception) when (exception is System.Net.WebSockets.WebSocketException or ObjectDisposedException)
        {
            return false;
        }
    }
}
