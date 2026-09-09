using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Settlement;

public sealed class SettlementNotificationBatchProcessorTests
{
    [Fact]
    public async Task Offline_notifications_remain_pending_and_online_success_is_marked()
    {
        var offline = new SettlementNotification(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), "Dead");
        var online = new SettlementNotification(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), "Extracted");
        var published = new List<Guid>();
        var marked = new List<Guid>();

        await SettlementNotificationBatchProcessor.ProcessAsync(
            [offline, online],
            playerId => playerId == online.PlayerId,
            (notification, _) =>
            {
                published.Add(notification.SettlementId);
                return Task.FromResult(true);
            },
            (settlementId, _) =>
            {
                marked.Add(settlementId);
                return Task.CompletedTask;
            },
            TestContext.Current.CancellationToken);

        Assert.Equal([online.SettlementId], published);
        Assert.Equal([online.SettlementId], marked);
    }

    [Fact]
    public async Task Failed_delivery_is_not_marked_published()
    {
        var notification = new SettlementNotification(Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid(), "Dead");
        var marked = false;

        await SettlementNotificationBatchProcessor.ProcessAsync(
            [notification],
            _ => true,
            (_, _) => Task.FromResult(false),
            (_, _) =>
            {
                marked = true;
                return Task.CompletedTask;
            },
            TestContext.Current.CancellationToken);

        Assert.False(marked);
    }
}
