using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace FantasyCard.Server.Tests.Settlement;

public sealed class SettlementRecoveryHealthTests
{
    [Fact]
    public async Task Recovery_is_unhealthy_until_first_scan_completes()
    {
        var state = new SettlementRecoveryState();

        var result = await new SettlementRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Unhealthy, result.Status);
    }

    [Fact]
    public async Task Successful_scan_restores_readiness()
    {
        var state = new SettlementRecoveryState();
        state.FailScan(new InvalidOperationException("secret"));
        state.Complete([]);

        var result = await new SettlementRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task Failed_settlements_are_deduplicated_without_exposing_exception_messages()
    {
        var settlementId = Guid.NewGuid();
        var state = new SettlementRecoveryState();
        state.Complete([settlementId, settlementId]);

        var failed = await new SettlementRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);
        var failedStatus = state.Capture();
        state.FailScan(new InvalidOperationException("database-password"));
        var scanFailed = await new SettlementRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Unhealthy, failed.Status);
        Assert.Equal([settlementId], failedStatus.FailedSettlementIds);
        Assert.Equal(HealthStatus.Unhealthy, scanFailed.Status);
        Assert.Equal("InvalidOperationException", scanFailed.Data["scanFailure"]);
        Assert.DoesNotContain("database-password", scanFailed.Description);
    }
}
