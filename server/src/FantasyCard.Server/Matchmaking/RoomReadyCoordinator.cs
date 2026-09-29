using System.Diagnostics;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Common;
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
    ILogger<RoomReadyCoordinator> logger,
    ServerMetrics? metrics = null) : BackgroundService, IRoomReadyService
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
            var startedAt = Stopwatch.GetTimestamp();
            await connections.SendIfConnectedAsync(playerId, found, cancellationToken);
            metrics?.ObserveMatchLaunchPhase("found_send", Stopwatch.GetElapsedTime(startedAt));
            var message = eventStore.Create(playerId, "room.ready_required", "matchmaker",
                new RoomReadyRequiredEventPayload(match.MatchId, match.RoomId,
                    match.ReadyDeadline.ToUnixTimeMilliseconds(), 0, match.PlayerIds.Count));
            startedAt = Stopwatch.GetTimestamp();
            await connections.SendIfConnectedAsync(playerId, message, cancellationToken);
            metrics?.ObserveMatchLaunchPhase("required_send", Stopwatch.GetElapsedTime(startedAt));
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
        var startedAt = Stopwatch.GetTimestamp();
        var launch = await repository.ClaimReadyMatchAsync(now, cancellationToken);
        metrics?.ObserveMatchLaunchPhase("claim", Stopwatch.GetElapsedTime(startedAt));
        if (launch is null) return false;
        await LaunchAsync(launch, cancellationToken);
        return true;
    }

    private async Task LaunchAsync(ReadyMatchLaunch launch, CancellationToken cancellationToken)
    {
        var assignment = launch.Assignment;
        var startedAt = Stopwatch.GetTimestamp();
        var room = CreateRoom(assignment);
        metrics?.ObserveMatchLaunchPhase("build", Stopwatch.GetElapsedTime(startedAt));
        startedAt = Stopwatch.GetTimestamp();
        await snapshots.SaveIfDueAsync(room.Capture(), cancellationToken);
        metrics?.ObserveMatchLaunchPhase("snapshot", Stopwatch.GetElapsedTime(startedAt));
        RoomActor actor;
        var registered = false;
        try
        {
            startedAt = Stopwatch.GetTimestamp();
            actor = roomRegistry.Register(room, assignment.MatchId);
            metrics?.ObserveMatchLaunchPhase("register", Stopwatch.GetElapsedTime(startedAt));
            registered = true;
            startedAt = Stopwatch.GetTimestamp();
            await repository.MarkRunningAsync(assignment.MatchId, cancellationToken);
            metrics?.ObserveMatchLaunchPhase("mark_running", Stopwatch.GetElapsedTime(startedAt));
        }
        catch
        {
            metrics?.MatchLaunchFailed(registered ? "mark_running" : "register");
            if (registered) await roomRegistry.RemoveAsync(assignment.RoomId);
            throw;
        }

        foreach (var playerId in launch.HumanPlayerIds)
        {
            startedAt = Stopwatch.GetTimestamp();
            var state = await actor.ExecuteAsync(new GetRoomClientStateCommand(playerId), cancellationToken);
            var snapshot = RoomSnapshotProjection.Build(state, playerId, assignment.MatchId, timeProvider.GetUtcNow());
            var started = eventStore.Create(playerId, "room.started", "ready-complete",
                new RoomStartedEventPayload(assignment.MatchId, assignment.RoomId, assignment.Players.Count, snapshot),
                roomRevision: state.Snapshot.Revision);
            await connections.SendIfConnectedAsync(playerId, started, cancellationToken);
            metrics?.ObserveMatchLaunchPhase("started_send", Stopwatch.GetElapsedTime(startedAt));
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
            CombatCardCatalog.CreatePrototype(), assignment.Seed, FantasyCard.Domain.Configuration.GameConfigCatalog.Current.Numerics);
        foreach (var player in assignment.Players)
        {
            var wornArmor = (player.EquipmentIds ?? []).Select(id =>
            {
                var item = player.Equipment?.SingleOrDefault(value => value.ItemId == id);
                var details = item is null ? null : new EquipmentRewardData(
                    item.Slot, item.Quality, item.Element.ToString(), item.EffectAffix,
                    item.SecondaryTrait ?? "DrawInterval", item.Level);
                return new ExplorationItem(id.ToString("D"), ExplorationItemKind.Equipment,
                    Equipment: details, IsGenerated: false);
            }).ToArray();
            var equipment = EquipmentCombatRules.Calculate(player.Equipment);
            var state = room.AddPlayer(new BattleRoomPlayerSetup(player.PlayerId, player.HeroClass,
                player.CardIds, null, WeaponLevel: player.WeaponLevel,
                InventoryCapacity: player.InventoryCapacity, SafeSlots: player.SafeSlots,
                WornArmor: wornArmor, IsBot: player.IsBot, Equipment: equipment,
                SafeSlotIndexes: player.SafeSlotIndexes, DisplayName: player.DisplayName, CardLevels: player.CardLevels));
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
