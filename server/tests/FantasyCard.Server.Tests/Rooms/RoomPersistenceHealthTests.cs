using FantasyCard.Server.Rooms;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomPersistenceHealthTests
{
    [Fact]
    public async Task Failed_snapshot_is_unhealthy_until_a_later_success()
    {
        var roomId = Guid.NewGuid();
        var state = new RoomPersistenceState();
        var check = new RoomPersistenceHealthCheck(state);

        state.RecordFailure(roomId);
        var failed = await check.CheckHealthAsync(
            new HealthCheckContext(), TestContext.Current.CancellationToken);
        state.RecordSuccess(roomId);
        var recovered = await check.CheckHealthAsync(
            new HealthCheckContext(), TestContext.Current.CancellationToken);

        Assert.Equal(HealthStatus.Unhealthy, failed.Status);
        Assert.Equal(HealthStatus.Healthy, recovered.Status);
    }

    [Fact]
    public void Failure_snapshot_is_sorted_and_deduplicated()
    {
        var first = Guid.Parse("00000000-0000-0000-0000-000000000001");
        var second = Guid.Parse("00000000-0000-0000-0000-000000000002");
        var state = new RoomPersistenceState();

        state.RecordFailure(second);
        state.RecordFailure(first);
        state.RecordFailure(second);

        Assert.Equal([first, second], state.CaptureFailures());
    }
}
