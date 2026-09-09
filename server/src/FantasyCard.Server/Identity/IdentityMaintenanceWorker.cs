using FantasyCard.Server.Common;

namespace FantasyCard.Server.Identity;

public sealed partial class IdentityMaintenanceWorker(
    IdentityRepository repository,
    TimeProvider timeProvider,
    ServerMetrics metrics,
    ILogger<IdentityMaintenanceWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromHours(1), timeProvider);
        do
        {
            try
            {
                var deleted = await repository.CleanupExpiredDataAsync(
                    timeProvider.GetUtcNow(), stoppingToken);
                metrics.ExpiredDataDeleted(
                    deleted.Sessions,
                    deleted.IdempotencyRecords,
                    deleted.RoomEvents,
                    deleted.Preparations,
                    deleted.MatchTickets);
                if (deleted is not { Sessions: 0, IdempotencyRecords: 0, RoomEvents: 0, Preparations: 0, MatchTickets: 0 })
                {
                    ExpiredDataDeleted(
                        logger,
                        deleted.Sessions,
                        deleted.IdempotencyRecords,
                        deleted.RoomEvents,
                        deleted.Preparations,
                        deleted.MatchTickets);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                CleanupFailed(logger, exception);
            }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }

    [LoggerMessage(EventId = 4001, Level = LogLevel.Information, Message = "Expired data cleanup completed: {Sessions} session(s), {IdempotencyRecords} idempotency record(s), {RoomEvents} room event(s), {Preparations} preparation(s), {MatchTickets} match ticket(s).")]
    private static partial void ExpiredDataDeleted(ILogger logger, int sessions, int idempotencyRecords, int roomEvents, int preparations, int matchTickets);

    [LoggerMessage(EventId = 4002, Level = LogLevel.Error, Message = "Expired transient data cleanup failed.")]
    private static partial void CleanupFailed(ILogger logger, Exception exception);
}
