using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Progression;

public sealed partial class RewardRefreshRecoveryWorker(
    EconomyRepository economy,
    RoomRegistry rooms,
    RoomSnapshotRepository snapshots,
    TimeProvider timeProvider,
    ILogger<RewardRefreshRecoveryWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5), timeProvider);
        do
        {
            try
            {
                foreach (var operation in await economy.GetRecoverableRewardRefreshesAsync(stoppingToken))
                {
                    try
                    {
                        await RecoverAsync(operation, stoppingToken);
                    }
                    catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                    {
                        return;
                    }
                    catch (Exception exception)
                    {
                        RecoveryFailed(logger, operation.PlayerId, operation.RequestId, exception);
                    }
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                RecoveryScanFailed(logger, exception);
            }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }

    private async Task RecoverAsync(PendingRewardRefresh operation, CancellationToken cancellationToken)
    {
        BattleRoomSnapshot? snapshot;
        if (rooms.TryGetRoom(operation.RoomId, out var actor) && actor is not null)
        {
            snapshot = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
            await snapshots.SaveIfDueAsync(snapshot, cancellationToken);
        }
        else
        {
            snapshot = await snapshots.GetAsync(operation.RoomId, cancellationToken);
        }

        var receipt = FindReceipt(snapshot, operation.PlayerId, operation.RequestId);
        if (receipt is not null)
        {
            await economy.MarkRewardRefreshAppliedAsync(
                operation.PlayerId, operation.RequestId, receipt, cancellationToken);
            return;
        }
        await economy.RefundReservedRewardRefreshAsync(
            operation.PlayerId, operation.RequestId, cancellationToken);
    }

    internal static RewardRefreshReceiptSnapshot? FindReceipt(
        BattleRoomSnapshot? snapshot,
        Guid playerId,
        string requestId) =>
        snapshot?.Players.SingleOrDefault(player => player.PlayerId == playerId)
            ?.RewardRefreshReceipts?.SingleOrDefault(receipt => receipt.RequestId == requestId);

    [LoggerMessage(EventId = 4211, Level = LogLevel.Error, Message = "Reward refresh recovery scan failed.")]
    private static partial void RecoveryScanFailed(ILogger logger, Exception exception);

    [LoggerMessage(EventId = 4212, Level = LogLevel.Error,
        Message = "Reward refresh recovery failed for player {PlayerId}, request {RequestId}.")]
    private static partial void RecoveryFailed(
        ILogger logger, Guid playerId, string requestId, Exception exception);
}
