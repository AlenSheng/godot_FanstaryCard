using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace FantasyCard.Server.Rooms;

public sealed class RoomRecoveryState
{
    private readonly object _gate = new();
    private bool _completed;
    private string? _scanFailure;
    private Guid[] _failedRoomIds = [];

    public void Complete(IEnumerable<Guid> failedRoomIds)
    {
        ArgumentNullException.ThrowIfNull(failedRoomIds);
        lock (_gate)
        {
            _completed = true;
            _scanFailure = null;
            _failedRoomIds = failedRoomIds.Distinct().Order().ToArray();
        }
    }

    public void FailScan(Exception exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        lock (_gate)
        {
            _completed = true;
            _scanFailure = exception.GetType().Name;
            _failedRoomIds = [];
        }
    }

    public RoomRecoveryStatus Capture()
    {
        lock (_gate)
            return new RoomRecoveryStatus(_completed, _scanFailure, _failedRoomIds.ToArray());
    }
}

public sealed record RoomRecoveryStatus(
    bool Completed,
    string? ScanFailure,
    IReadOnlyList<Guid> FailedRoomIds)
{
    public bool IsHealthy => Completed && ScanFailure is null && FailedRoomIds.Count == 0;
}

public sealed class RoomRecoveryHealthCheck(RoomRecoveryState state) : IHealthCheck
{
    public Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken cancellationToken = default)
    {
        var status = state.Capture();
        if (status.IsHealthy)
            return Task.FromResult(HealthCheckResult.Healthy("Running room recovery completed."));

        var data = new Dictionary<string, object>
        {
            ["completed"] = status.Completed,
            ["scanFailure"] = status.ScanFailure ?? string.Empty,
            ["failedRoomIds"] = status.FailedRoomIds.Select(id => id.ToString("D")).ToArray()
        };
        return Task.FromResult(HealthCheckResult.Unhealthy(
            status.Completed ? "One or more running rooms were not restored." : "Running room recovery has not completed.",
            data: data));
    }
}
