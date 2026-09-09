namespace FantasyCard.Server.Settlement;

public static class SettlementNotificationBatchProcessor
{
    public static async Task ProcessAsync(
        IEnumerable<SettlementNotification> notifications,
        Func<Guid, bool> isConnected,
        Func<SettlementNotification, CancellationToken, Task<bool>> publish,
        Func<Guid, CancellationToken, Task> markPublished,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(notifications);
        ArgumentNullException.ThrowIfNull(isConnected);
        ArgumentNullException.ThrowIfNull(publish);
        ArgumentNullException.ThrowIfNull(markPublished);
        foreach (var notification in notifications)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!isConnected(notification.PlayerId)) continue;
            if (!await publish(notification, cancellationToken)) continue;
            await markPublished(notification.SettlementId, cancellationToken);
        }
    }
}
