using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Combat;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Common;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Rooms;

public sealed partial class RoomRegistry(
    TimeProvider timeProvider,
    SettlementCoordinator? settlementCoordinator = null,
    RoomSnapshotRepository? snapshotRepository = null,
    RoomPersistenceState? persistenceState = null,
    ServerMetrics? metrics = null,
    ILogger<RoomRegistry>? logger = null,
    RealtimeEventStore? eventStore = null,
    ConnectionRegistry? connections = null) : IAsyncDisposable
{
    private readonly object _gate = new();
    private readonly Dictionary<Guid, RoomActor> _rooms = [];
    private readonly Dictionary<Guid, Guid> _playerRooms = [];
    private readonly Dictionary<Guid, Guid?> _roomMatches = [];
    private readonly Dictionary<Guid, RoomLifecycleMetricsTracker> _lifecycleTrackers = [];

    public RoomActor Register(BattleRoom room, Guid? matchId = null, bool startTicker = true)
    {
        ArgumentNullException.ThrowIfNull(room);
        var initialSnapshot = room.Capture();
        var players = initialSnapshot.Players;
        lock (_gate)
        {
            if (_rooms.ContainsKey(room.RoomId))
            {
                throw new InvalidOperationException($"Room '{room.RoomId}' is already registered.");
            }
            // A settled player may start another match while their former room
            // remains alive for teammates. Only active players own the route.
            var activePlayers = players.Where(player => !IsTerminal(player.Phase)).ToArray();
            var conflictingPlayer = activePlayers.FirstOrDefault(player => _playerRooms.ContainsKey(player.PlayerId));
            if (conflictingPlayer is not null)
            {
                throw new InvalidOperationException($"Player '{conflictingPlayer.PlayerId}' is already assigned to a room.");
            }

            DateTimeOffset? lastSnapshotFailureLog = null;
            DateTimeOffset? lastSettlementFailureLog = null;
            var lifecycleTracker = metrics is null
                ? null
                : new RoomLifecycleMetricsTracker(initialSnapshot, metrics, timeProvider);
            var transitionPublisher = eventStore is null
                ? null
                : new RoomTransitionEventPublisher(initialSnapshot, eventStore, connections);
            var observer = snapshotRepository is null &&
                (settlementCoordinator is null || matchId is not { }) &&
                lifecycleTracker is null && transitionPublisher is null
                ? null
                : new Func<BattleRoomSnapshot, Task>(async snapshot =>
                {
                    lifecycleTracker?.Observe(snapshot);
                    if (transitionPublisher is not null)
                        await transitionPublisher.ObserveAsync(snapshot);
                    if (snapshotRepository is not null)
                    {
                        try
                        {
                            await snapshotRepository.SaveIfDueAsync(snapshot);
                            persistenceState?.RecordSuccess(snapshot.RoomId);
                        }
                        catch (Exception exception)
                        {
                            persistenceState?.RecordFailure(snapshot.RoomId);
                            metrics?.RoomSnapshotFailed();
                            var now = timeProvider.GetUtcNow();
                            if (lastSnapshotFailureLog is null || now - lastSnapshotFailureLog >= TimeSpan.FromSeconds(10))
                            {
                                lastSnapshotFailureLog = now;
                                if (logger is not null)
                                    SnapshotPersistenceFailed(logger, snapshot.RoomId, snapshot.Revision, exception);
                            }
                        }
                    }
                    if (settlementCoordinator is not null && matchId is { } id)
                    {
                        try
                        {
                            await settlementCoordinator.ObserveAsync(id, snapshot);
                            ReleaseTerminalPlayers(snapshot);
                        }
                        catch (Exception exception)
                        {
                            metrics?.SettlementFailed();
                            var now = timeProvider.GetUtcNow();
                            if (lastSettlementFailureLog is null || now - lastSettlementFailureLog >= TimeSpan.FromSeconds(10))
                            {
                                lastSettlementFailureLog = now;
                                if (logger is not null)
                                    SettlementObservationFailed(logger, snapshot.RoomId, snapshot.Revision, exception);
                            }
                        }
                    }
                });
            var actor = new RoomActor(room, timeProvider, startTicker, observer, metrics,
                transitionPublisher is null ? null : transitionPublisher.ObserveCombatAsync);
            _rooms.Add(room.RoomId, actor);
            _roomMatches.Add(room.RoomId, matchId);
            if (lifecycleTracker is not null)
                _lifecycleTrackers.Add(room.RoomId, lifecycleTracker);
            foreach (var player in activePlayers)
            {
                _playerRooms.Add(player.PlayerId, room.RoomId);
            }
            metrics?.RoomOpened(players.Count);
            return actor;
        }
    }

    internal void ReleaseTerminalPlayers(BattleRoomSnapshot snapshot)
    {
        lock (_gate)
        {
            foreach (var player in snapshot.Players.Where(player => IsTerminal(player.Phase)))
            {
                if (_playerRooms.TryGetValue(player.PlayerId, out var roomId) && roomId == snapshot.RoomId)
                    _playerRooms.Remove(player.PlayerId);
            }
        }
    }

    private static bool IsTerminal(RoomPlayerPhase phase) =>
        phase is RoomPlayerPhase.Extracted or RoomPlayerPhase.Dead;

    public bool TryGetForPlayer(Guid playerId, out RoomActor? actor)
    {
        lock (_gate)
        {
            actor = null;
            return _playerRooms.TryGetValue(playerId, out var roomId) &&
                _rooms.TryGetValue(roomId, out actor);
        }
    }

    public bool ContainsRoom(Guid roomId)
    {
        lock (_gate) return _rooms.ContainsKey(roomId);
    }

    public IReadOnlyList<Guid> GetRoomIds()
    {
        lock (_gate) return _rooms.Keys.ToArray();
    }

    public bool TryGetRoom(Guid roomId, out RoomActor? actor)
    {
        lock (_gate) return _rooms.TryGetValue(roomId, out actor);
    }

    public bool TryGetForPlayer(Guid playerId, out RoomActor? actor, out Guid? matchId)
    {
        lock (_gate)
        {
            actor = null;
            matchId = null;
            if (!_playerRooms.TryGetValue(playerId, out var roomId) ||
                !_rooms.TryGetValue(roomId, out actor))
                return false;
            _roomMatches.TryGetValue(roomId, out matchId);
            return true;
        }
    }

    public async ValueTask MarkPlayerDisconnectedAsync(Guid playerId)
    {
        if (TryGetForPlayer(playerId, out var actor) && actor is not null)
            await actor.ExecuteAsync(new SetPlayerConnectionCommand(playerId, Connected: false));
    }

    public async ValueTask MarkPlayerConnectedAsync(Guid playerId)
    {
        if (TryGetForPlayer(playerId, out var actor) && actor is not null)
            await actor.ExecuteAsync(new SetPlayerConnectionCommand(playerId, Connected: true));
    }

    public async ValueTask<bool> RemoveAsync(Guid roomId)
    {
        RoomActor? actor;
        RoomLifecycleMetricsTracker? lifecycleTracker;
        lock (_gate)
        {
            if (!_rooms.Remove(roomId, out actor))
            {
                return false;
            }
            _roomMatches.Remove(roomId);
            _lifecycleTrackers.Remove(roomId, out lifecycleTracker);
            persistenceState?.Clear(roomId);
            foreach (var playerId in _playerRooms
                .Where(pair => pair.Value == roomId)
                .Select(pair => pair.Key)
                .ToArray())
            {
                _playerRooms.Remove(playerId);
            }
        }

        await actor.DisposeAsync();
        lifecycleTracker?.EndRemaining();
        metrics?.RoomClosed();
        return true;
    }

    public async ValueTask DisposeAsync()
    {
        Guid[] roomIds;
        lock (_gate)
        {
            roomIds = _rooms.Keys.ToArray();
        }
        foreach (var roomId in roomIds)
        {
            await RemoveAsync(roomId);
        }
    }

    [LoggerMessage(EventId = 4301, Level = LogLevel.Error, Message = "Room {RoomId} snapshot persistence failed at revision {RoomRevision}.")]
    private static partial void SnapshotPersistenceFailed(ILogger logger, Guid roomId, long roomRevision, Exception exception);

    [LoggerMessage(EventId = 4302, Level = LogLevel.Error, Message = "Room {RoomId} settlement observation failed at revision {RoomRevision}.")]
    private static partial void SettlementObservationFailed(ILogger logger, Guid roomId, long roomRevision, Exception exception);
}
