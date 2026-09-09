using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Rooms;

public sealed partial class RoomRecoveryWorker(
    RoomSnapshotRepository snapshots,
    RoomRegistry registry,
    RoomRecoveryState recoveryState,
    TimeProvider timeProvider,
    ILogger<RoomRecoveryWorker> logger) : IHostedService
{
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        IReadOnlyList<PersistedRoomSnapshot> persisted;
        try
        {
            persisted = await snapshots.GetRunningAsync(cancellationToken);
        }
        catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
        {
            RecoveryFailed(logger, exception);
            recoveryState.FailScan(exception);
            return;
        }

        var failedRoomIds = new List<Guid>();
        foreach (var room in persisted)
        {
            var registered = false;
            try
            {
                if (registry.ContainsRoom(room.Snapshot.RoomId)) continue;
                var actor = registry.Register(
                    BattleRoom.Restore(room.Snapshot, CombatCardCatalog.CreatePrototype(), room.Seed),
                    room.MatchId);
                registered = true;
                var now = timeProvider.GetUtcNow();
                var downtime = now - room.SavedAt;
                if (downtime > TimeSpan.Zero)
                    await actor.ExecuteAsync(new RecoverRoomDowntimeCommand(downtime, now), cancellationToken);
            }
            catch (Exception exception) when (!cancellationToken.IsCancellationRequested)
            {
                if (registered)
                    await registry.RemoveAsync(room.Snapshot.RoomId);
                failedRoomIds.Add(room.Snapshot.RoomId);
                RoomRecoveryFailed(logger, room.Snapshot.RoomId, exception);
            }
        }
        recoveryState.Complete(failedRoomIds);
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    [LoggerMessage(EventId = 4201, Level = LogLevel.Error, Message = "Running room recovery scan failed.")]
    private static partial void RecoveryFailed(ILogger logger, Exception exception);

    [LoggerMessage(EventId = 4202, Level = LogLevel.Error, Message = "Running room {RoomId} could not be restored.")]
    private static partial void RoomRecoveryFailed(ILogger logger, Guid roomId, Exception exception);
}
