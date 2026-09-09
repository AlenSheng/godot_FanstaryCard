using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Settlement;

public sealed class SettlementEventPublisher(
    SettlementRepository repository,
    RealtimeEventStore eventStore,
    ConnectionRegistry connections)
{
    public async Task PublishReadyAsync(Guid? playerId, CancellationToken cancellationToken)
    {
        var notifications = await repository.GetReadyNotificationsAsync(playerId, cancellationToken);
        await SettlementNotificationBatchProcessor.ProcessAsync(
            notifications,
            connections.IsConnected,
            PublishAsync,
            repository.MarkNotificationPublishedAsync,
            cancellationToken);
    }

    private async Task<bool> PublishAsync(
        SettlementNotification notification,
        CancellationToken cancellationToken)
    {
        var payload = new SettlementReadyEventPayload(
            notification.SettlementId,
            notification.MatchId,
            notification.Result);
        var ready = eventStore.Create(
            notification.PlayerId,
            "settlement.ready",
            "settlement-outbox",
            payload);
        if (!await connections.SendIfConnectedAsync(notification.PlayerId, ready, cancellationToken)) return false;
        var settled = eventStore.Create(
            notification.PlayerId,
            "match.settled",
            "settlement-outbox",
            payload);
        return await connections.SendIfConnectedAsync(notification.PlayerId, settled, cancellationToken);
    }
}
