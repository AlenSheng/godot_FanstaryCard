using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Settlement;

public sealed class SettlementBatchProcessorTests
{
    [Fact]
    public async Task Failed_settlement_does_not_starve_later_settlements()
    {
        var first = Guid.NewGuid();
        var broken = Guid.NewGuid();
        var last = Guid.NewGuid();
        var committed = new List<Guid>();
        var failed = new List<Guid>();

        await SettlementBatchProcessor.ProcessAsync(
            [first, broken, broken, last],
            (settlementId, _) => settlementId == broken
                ? Task.FromException<int>(new InvalidOperationException("broken"))
                : Task.FromResult(1),
            (settlementId, _) => committed.Add(settlementId),
            (settlementId, _) => failed.Add(settlementId),
            TestContext.Current.CancellationToken);

        Assert.Equal([first, last], committed);
        Assert.Equal([broken], failed);
    }

    [Fact]
    public async Task Cancellation_stops_the_batch_instead_of_being_reported_as_failure()
    {
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var failures = 0;

        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            SettlementBatchProcessor.ProcessAsync(
                [Guid.NewGuid()],
                (_, _) => Task.FromResult(1),
                (_, _) => { },
                (_, _) => failures++,
                cancellation.Token));

        Assert.Equal(0, failures);
    }
}
