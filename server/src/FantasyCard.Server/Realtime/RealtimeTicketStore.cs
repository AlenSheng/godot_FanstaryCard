using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Realtime;

// Stores only hashes. One live ticket per player and a global cap bound memory.
public sealed class RealtimeTicketStore(TimeProvider timeProvider)
{
    public static readonly TimeSpan Lifetime = TimeSpan.FromSeconds(30);
    private const int Capacity = 4096;
    private readonly object _gate = new();
    private readonly Dictionary<string, TicketSession> _tickets = new(StringComparer.Ordinal);

    public IssuedRealtimeTicket? Issue(Guid playerId, byte[] sessionHash)
    {
        lock (_gate)
        {
            var now = timeProvider.GetUtcNow();
            foreach (var key in _tickets.Where(pair => pair.Value.ExpiresAt <= now || pair.Value.PlayerId == playerId)
                         .Select(pair => pair.Key).ToArray())
                _tickets.Remove(key);
            if (_tickets.Count >= Capacity) return null;
            var token = SessionToken.Create();
            var expires = now.Add(Lifetime);
            _tickets.Add(Convert.ToHexString(SessionToken.Hash(token)), new(playerId, sessionHash.ToArray(), expires));
            return new(token, expires);
        }
    }

    public TicketSession? Consume(string? ticket)
    {
        if (string.IsNullOrEmpty(ticket) || ticket.Length > 256) return null;
        lock (_gate)
        {
            return _tickets.Remove(Convert.ToHexString(SessionToken.Hash(ticket)), out var session)
                   && session.ExpiresAt > timeProvider.GetUtcNow() ? session : null;
        }
    }
}

public sealed record IssuedRealtimeTicket(string Ticket, DateTimeOffset ExpiresAt);
public sealed record TicketSession(Guid PlayerId, byte[] SessionHash, DateTimeOffset ExpiresAt);
