using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace FantasyCard.Server.Rooms;

public sealed class RoomPersistenceState
{
    private readonly object _gate = new();
    private readonly HashSet<Guid> _failedRooms = [];

    public void RecordSuccess(Guid roomId)
    {
        lock (_gate) _failedRooms.Remove(roomId);
    }

    public void RecordFailure(Guid roomId)
    {
        lock (_gate) _failedRooms.Add(roomId);
    }

    public void Clear(Guid roomId)
    {
        lock (_gate) _failedRooms.Remove(roomId);
    }

    public IReadOnlyList<Guid> CaptureFailures()
    {
        lock (_gate) return _failedRooms.Order().ToArray();
    }
}

public sealed class RoomPersistenceHealthCheck(RoomPersistenceState state) : IHealthCheck
{
    public Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken cancellationToken = default)
    {
        var failedRooms = state.CaptureFailures();
        return Task.FromResult(failedRooms.Count == 0
            ? HealthCheckResult.Healthy("Room snapshots are persisting normally.")
            : HealthCheckResult.Unhealthy(
                "One or more active rooms have an unpersisted snapshot.",
                data: new Dictionary<string, object>
                {
                    ["failedRoomIds"] = failedRooms.Select(id => id.ToString("D")).ToArray()
                }));
    }
}
