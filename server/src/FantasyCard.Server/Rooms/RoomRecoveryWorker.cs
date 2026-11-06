using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Rooms;

public sealed partial class RoomRecoveryWorker(
    RoomSnapshotRepository snapshots,
    RoomRegistry registry,
    RoomRecoveryState recoveryState,
    TimeProvider timeProvider,
    ILogger<RoomRecoveryWorker> logger,
    PublishedConfigCatalogs? configurations = null) : IHostedService
{
    private readonly PublishedConfigCatalogs _configurations = configurations ?? new(GameConfigCatalog.Current);
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
                if (registry.ContainsRoom(room.RoomId)) continue;
                var snapshot = room.Snapshot ?? throw new InvalidOperationException(room.ReadError ?? "The room checkpoint is invalid.");
                RoomSnapshotRepository.RequireMatchContext(snapshot, room.RoomId, room.MatchConfigVersion!, room.MatchSeason);
                // A stale checkpoint cannot resurrect a player whose durable
                // settlement released their assets and next-match permission.
                // Quarantine this room rather than reconstructing lost combat
                // or relic state from an incomplete settlement receipt.
                foreach (var (playerId, result) in room.SettledPlayers)
                {
                    var player = snapshot.Players.SingleOrDefault(value => value.PlayerId == playerId);
                    if (player is null || player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted) ||
                        ((result is "Dead" or "Extracted") && result != player.Phase.ToString()))
                        throw new InvalidOperationException($"Room '{room.RoomId}' checkpoint disagrees with durable settlement for player '{playerId}'.");
                }
                var actor = registry.Register(
                    BattleRoom.Restore(snapshot, CombatCardCatalog.Create(_configurations.Resolve(snapshot.ConfigVersion)), room.Seed),
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
                    await registry.RemoveAsync(room.RoomId);
                failedRoomIds.Add(room.RoomId);
                RoomRecoveryFailed(logger, room.RoomId, exception);
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
