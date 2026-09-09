using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Matchmaking;

public interface IRoomReadyService
{
    Task<ReadyLobbyView?> GetAsync(Guid playerId, CancellationToken cancellationToken);
    Task<ReadyLobbyView> ReadyAsync(Guid playerId, CancellationToken cancellationToken);
}

public sealed partial class RoomReadyCoordinator(
    MatchmakingRepository repository,
    RoomRegistry roomRegistry,
    RoomSnapshotRepository snapshots,
    RealtimeEventStore eventStore,
    ConnectionRegistry connections,
    TimeProvider timeProvider,
    ILogger<RoomReadyCoordinator> logger) : BackgroundService, IRoomReadyService
{
    public Task<ReadyLobbyView?> GetAsync(Guid playerId, CancellationToken cancellationToken) =>
        repository.GetReadyLobbyAsync(playerId, cancellationToken);

    public Task<ReadyLobbyView> ReadyAsync(Guid playerId, CancellationToken cancellationToken) =>
        repository.MarkReadyAsync(playerId, timeProvider.GetUtcNow(), cancellationToken);

    public async Task NotifyRequiredAsync(PendingMatch match, CancellationToken cancellationToken)
    {
        foreach (var playerId in match.PlayerIds)
        {
            var found = eventStore.Create(playerId, "match.found", "matchmaker",
                new MatchFoundEventPayload(match.MatchId, match.RoomId, match.ReadyDeadline.ToUnixTimeMilliseconds()));
            await connections.SendIfConnectedAsync(playerId, found, cancellationToken);
            var message = eventStore.Create(playerId, "room.ready_required", "matchmaker",
                new RoomReadyRequiredEventPayload(match.MatchId, match.RoomId,
                    match.ReadyDeadline.ToUnixTimeMilliseconds(), 0, match.PlayerIds.Count));
            await connections.SendIfConnectedAsync(playerId, message, cancellationToken);
        }
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (!await ProcessNextAsync(timeProvider.GetUtcNow(), stoppingToken))
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(100), stoppingToken);
                    continue;
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                LaunchFailed(logger, exception);
                await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken);
            }
        }
    }

    internal async Task<bool> ProcessNextAsync(DateTimeOffset now, CancellationToken cancellationToken)
    {
        var launch = await repository.ClaimReadyMatchAsync(now, cancellationToken);
        if (launch is null) return false;
        await LaunchAsync(launch, cancellationToken);
        return true;
    }

    private async Task LaunchAsync(ReadyMatchLaunch launch, CancellationToken cancellationToken)
    {
        var assignment = launch.Assignment;
        var room = CreateRoom(assignment);
        await snapshots.SaveIfDueAsync(room.Capture(), cancellationToken);
        RoomActor actor;
        var registered = false;
        try
        {
            actor = roomRegistry.Register(room, assignment.MatchId);
            registered = true;
            await repository.MarkRunningAsync(assignment.MatchId, cancellationToken);
        }
        catch
        {
            if (registered) await roomRegistry.RemoveAsync(assignment.RoomId);
            throw;
        }

        foreach (var playerId in launch.HumanPlayerIds)
        {
            var state = await actor.ExecuteAsync(new GetRoomClientStateCommand(playerId), cancellationToken);
            var snapshot = RoomSnapshotProjection.Build(state, playerId, assignment.MatchId, timeProvider.GetUtcNow());
            var started = eventStore.Create(playerId, "room.started", "ready-complete",
                new RoomStartedEventPayload(assignment.MatchId, assignment.RoomId, assignment.Players.Count, snapshot),
                roomRevision: state.Snapshot.Revision);
            await connections.SendIfConnectedAsync(playerId, started, cancellationToken);
        }

        foreach (var playerId in launch.RemovedPlayerIds)
        {
            var removed = eventStore.Create(playerId, "room.ready_removed", "ready-timeout",
                new RoomReadyRemovedEventPayload(assignment.MatchId, "ready_timeout"));
            await connections.SendIfConnectedAsync(playerId, removed, cancellationToken);
        }
    }

    private static BattleRoom CreateRoom(MatchAssignment assignment)
    {
        var room = new BattleRoom(assignment.RoomId, BootstrapRepository.CurrentConfigVersion,
            CombatCardCatalog.CreatePrototype(), assignment.Seed);
        foreach (var player in assignment.Players)
        {
            var wornArmor = (player.EquipmentIds ?? []).Select(id =>
                new ExplorationItem(id.ToString("D"), ExplorationItemKind.Equipment)).ToArray();
            var equipment = EquipmentCombatRules.Calculate(player.Equipment);
            var state = room.AddPlayer(new BattleRoomPlayerSetup(player.PlayerId, player.HeroClass,
                player.CardIds, null, WeaponLevel: player.WeaponLevel,
                InventoryCapacity: player.InventoryCapacity, SafeSlots: player.SafeSlots,
                WornArmor: wornArmor, IsBot: player.IsBot, Equipment: equipment));
            for (var potion = 0; potion < player.PotionCount; potion++)
                if (!state.Inventory.TryAdd(new ExplorationItem($"health_potion:{potion + 1}", ExplorationItemKind.HealthPotion)))
                    throw new InvalidOperationException("Preparation potion count exceeds the exploration inventory capacity.");
        }
        room.InitializeMap(ChaosMapGenerator.Generate(assignment.Seed, assignment.Players.Count));
        return room;
    }

    [LoggerMessage(EventId = 3011, Level = LogLevel.Error, Message = "Ready-match launch iteration failed.")]
    private static partial void LaunchFailed(ILogger logger, Exception exception);
}
