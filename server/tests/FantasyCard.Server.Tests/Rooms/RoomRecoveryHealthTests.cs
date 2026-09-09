using FantasyCard.Server.Rooms;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomRecoveryHealthTests
{
    [Fact]
    public async Task Recovery_is_unhealthy_until_scan_completes()
    {
        var state = new RoomRecoveryState();
        var result = await new RoomRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Unhealthy, result.Status);
    }

    [Fact]
    public async Task Completed_scan_without_failures_is_healthy()
    {
        var state = new RoomRecoveryState();
        state.Complete([]);

        var result = await new RoomRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task Failed_rooms_keep_readiness_unhealthy()
    {
        var roomId = Guid.NewGuid();
        var state = new RoomRecoveryState();
        state.Complete([roomId, roomId]);

        var result = await new RoomRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Equal([roomId], state.Capture().FailedRoomIds);
    }

    [Fact]
    public async Task Scan_failure_keeps_readiness_unhealthy_without_exposing_message()
    {
        var state = new RoomRecoveryState();
        state.FailScan(new InvalidOperationException("database-password"));

        var result = await new RoomRecoveryHealthCheck(state)
            .CheckHealthAsync(new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Equal("InvalidOperationException", result.Data["scanFailure"]);
        Assert.DoesNotContain("database-password", result.Description);
    }
}
