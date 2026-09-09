using System.Collections.Concurrent;
using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Realtime;

public sealed class RealtimeEventStore(TimeProvider timeProvider)
{
    private const int MaximumBufferedEvents = 256;
    private const int MaximumRememberedRequests = 256;
    private readonly ConcurrentDictionary<Guid, PlayerStream> _streams = new();

    public ServerEvent Create(
        Guid playerId,
        string type,
        string traceId,
        object? payload,
        string? requestId = null,
        long? roomRevision = null)
    {
        while (true)
        {
            var stream = _streams.GetOrAdd(
                playerId, _ => new PlayerStream(timeProvider.GetUtcNow()));
            lock (stream.Gate)
            {
                if (!_streams.TryGetValue(playerId, out var current) ||
                    !ReferenceEquals(current, stream))
                    continue;
                var now = timeProvider.GetUtcNow();
                stream.LastAccessAt = now;
                var message = new ServerEvent(
                    type,
                    traceId,
                    payload,
                    Guid.CreateVersion7().ToString("N"),
                    ++stream.LastSequence,
                    now,
                    requestId,
                    roomRevision);
                stream.Events.Enqueue(message);
                while (stream.Events.Count > MaximumBufferedEvents)
                {
                    stream.Events.Dequeue();
                }

                if (requestId is not null)
                {
                    stream.Responses[requestId] = message;
                    stream.RequestOrder.Enqueue(requestId);
                    while (stream.RequestOrder.Count > MaximumRememberedRequests)
                    {
                        var expiredRequest = stream.RequestOrder.Dequeue();
                        stream.Responses.Remove(expiredRequest);
                    }
                }

                return message;
            }
        }
    }

    public bool TryGetResponse(Guid playerId, string requestId, out ServerEvent? response)
    {
        response = null;
        if (!_streams.TryGetValue(playerId, out var stream))
        {
            return false;
        }

        lock (stream.Gate)
        {
            if (!_streams.TryGetValue(playerId, out var current) ||
                !ReferenceEquals(current, stream))
                return false;
            stream.LastAccessAt = timeProvider.GetUtcNow();
            return stream.Responses.TryGetValue(requestId, out response);
        }
    }

    public ReplayResult ReadAfter(Guid playerId, long lastSequence)
    {
        if (!_streams.TryGetValue(playerId, out var stream))
        {
            return new ReplayResult(false, 0, []);
        }

        lock (stream.Gate)
        {
            if (!_streams.TryGetValue(playerId, out var current) ||
                !ReferenceEquals(current, stream))
                return new ReplayResult(false, 0, []);
            stream.LastAccessAt = timeProvider.GetUtcNow();
            var firstBufferedSequence = stream.Events.Count == 0
                ? stream.LastSequence + 1
                : stream.Events.Peek().Sequence;
            var hasGap = lastSequence < firstBufferedSequence - 1;
            var events = hasGap
                ? []
                : stream.Events.Where(message => message.Sequence > lastSequence).ToArray();
            return new ReplayResult(hasGap, stream.LastSequence, events);
        }
    }

    public sealed record ReplayResult(
        bool HasGap,
        long LastSequence,
        IReadOnlyList<ServerEvent> Events);

    public int RemoveInactive(DateTimeOffset cutoff)
    {
        var removed = 0;
        foreach (var pair in _streams)
        {
            lock (pair.Value.Gate)
            {
                if (pair.Value.LastAccessAt >= cutoff) continue;
                if (_streams.TryRemove(
                    new KeyValuePair<Guid, PlayerStream>(pair.Key, pair.Value)))
                    removed++;
            }
        }
        return removed;
    }

    private sealed class PlayerStream(DateTimeOffset lastAccessAt)
    {
        public object Gate { get; } = new();
        public long LastSequence { get; set; }
        public Queue<ServerEvent> Events { get; } = new();
        public Dictionary<string, ServerEvent> Responses { get; } = new(StringComparer.Ordinal);
        public Queue<string> RequestOrder { get; } = new();
        public DateTimeOffset LastAccessAt { get; set; } = lastAccessAt;
    }
}
