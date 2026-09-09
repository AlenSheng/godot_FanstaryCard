using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace FantasyCard.Server.Settlement;

public sealed class SettlementRecoveryState
{
    private readonly object _gate = new();
    private bool _completed;
    private string? _scanFailure;
    private Guid[] _failedSettlementIds = [];

    public void Complete(IEnumerable<Guid> failedSettlementIds)
    {
        ArgumentNullException.ThrowIfNull(failedSettlementIds);
        lock (_gate)
        {
            _completed = true;
            _scanFailure = null;
            _failedSettlementIds = failedSettlementIds.Distinct().Order().ToArray();
        }
    }

    public void FailScan(Exception exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        lock (_gate)
        {
            _completed = true;
            _scanFailure = exception.GetType().Name;
            _failedSettlementIds = [];
        }
    }

    public SettlementRecoveryStatus Capture()
    {
        lock (_gate)
            return new(_completed, _scanFailure, _failedSettlementIds.ToArray());
    }
}

public sealed record SettlementRecoveryStatus(
    bool Completed,
    string? ScanFailure,
    IReadOnlyList<Guid> FailedSettlementIds)
{
    public bool IsHealthy => Completed && ScanFailure is null && FailedSettlementIds.Count == 0;
}

public sealed class SettlementRecoveryHealthCheck(SettlementRecoveryState state) : IHealthCheck
{
    public Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken cancellationToken = default)
    {
        var status = state.Capture();
        if (status.IsHealthy)
            return Task.FromResult(HealthCheckResult.Healthy("Settlement recovery scan completed."));

        return Task.FromResult(HealthCheckResult.Unhealthy(
            status.Completed
                ? "One or more settlements could not be recovered."
                : "Settlement recovery has not completed.",
            data: new Dictionary<string, object>
            {
                ["completed"] = status.Completed,
                ["scanFailure"] = status.ScanFailure ?? string.Empty,
                ["failedSettlementIds"] = status.FailedSettlementIds.Select(id => id.ToString("D")).ToArray()
            }));
    }
}
