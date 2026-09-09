using FantasyCard.Domain.Combat;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Rooms;

public sealed class RoomLifecycleMetricsTracker
{
    private readonly ServerMetrics _metrics;
    private readonly TimeProvider _timeProvider;
    private readonly Dictionary<Guid, PveObservation> _pve = [];
    private readonly Dictionary<Guid, DuelObservation> _duels = [];

    public RoomLifecycleMetricsTracker(
        BattleRoomSnapshot initialSnapshot,
        ServerMetrics metrics,
        TimeProvider timeProvider)
    {
        ArgumentNullException.ThrowIfNull(initialSnapshot);
        _metrics = metrics ?? throw new ArgumentNullException(nameof(metrics));
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        Seed(initialSnapshot);
    }

    public void Observe(BattleRoomSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ObservePve(snapshot);
        ObserveDuels(snapshot);
    }

    public void EndRemaining(string reason = "room_closed")
    {
        foreach (var observation in _pve.Values)
        {
            _metrics.ObservePveDuration(observation.ActiveElapsed, reason);
            _metrics.PveEndedAbnormally(reason);
        }
        foreach (var observation in _duels.Values)
        {
            _metrics.ObservePvpDuration(_timeProvider.GetUtcNow() - observation.StartedAt, reason);
            _metrics.PvpEndedAbnormally(reason);
        }
        _pve.Clear();
        _duels.Clear();
    }

    private void Seed(BattleRoomSnapshot snapshot)
    {
        foreach (var player in snapshot.Players)
        {
            if (player.Pve is { Phase: PveBattlePhase.Active or PveBattlePhase.Frozen } battle)
                _pve[battle.BattleId] = new PveObservation(player.PlayerId, snapshot.Elapsed, TimeSpan.Zero, battle.Phase);
        }
        foreach (var duel in snapshot.Duels)
            _duels[duel.DuelId] = new DuelObservation(duel.StartedAt, duel.FirstPlayerId, duel.LatePlayerId);
    }

    private void ObservePve(BattleRoomSnapshot snapshot)
    {
        var currentIds = new HashSet<Guid>();
        foreach (var player in snapshot.Players)
        {
            if (player.Pve is not { } battle) continue;
            currentIds.Add(battle.BattleId);
            if (!_pve.TryGetValue(battle.BattleId, out var observation))
            {
                if (battle.Phase is PveBattlePhase.Active or PveBattlePhase.Frozen)
                    _pve[battle.BattleId] = new PveObservation(player.PlayerId, snapshot.Elapsed, TimeSpan.Zero, battle.Phase);
                continue;
            }

            var elapsed = observation.ActiveElapsed;
            if (observation.Phase == PveBattlePhase.Active && snapshot.Elapsed > observation.LastRoomElapsed)
                elapsed += snapshot.Elapsed - observation.LastRoomElapsed;

            if (battle.Phase is PveBattlePhase.Cleared or PveBattlePhase.Dead)
            {
                var outcome = battle.Phase == PveBattlePhase.Cleared ? "cleared" : "player_dead";
                _metrics.ObservePveDuration(elapsed, outcome);
                if (battle.Phase == PveBattlePhase.Dead)
                    _metrics.PveEndedAbnormally(outcome);
                _pve.Remove(battle.BattleId);
                continue;
            }
            _pve[battle.BattleId] = observation with
            {
                LastRoomElapsed = snapshot.Elapsed,
                ActiveElapsed = elapsed,
                Phase = battle.Phase
            };
        }

        foreach (var battleId in _pve.Keys.Where(id => !currentIds.Contains(id)).ToArray())
        {
            var observation = _pve[battleId];
            var playerDead = snapshot.Players.Any(player =>
                player.PlayerId == observation.PlayerId && player.Phase == RoomPlayerPhase.Dead);
            var reason = playerDead ? "interrupted_by_player_death" : "removed";
            _metrics.ObservePveDuration(observation.ActiveElapsed, reason);
            _metrics.PveEndedAbnormally(reason);
            _pve.Remove(battleId);
        }
    }

    private void ObserveDuels(BattleRoomSnapshot snapshot)
    {
        var now = _timeProvider.GetUtcNow();
        var currentIds = snapshot.Duels.Select(duel => duel.DuelId).ToHashSet();
        foreach (var duel in snapshot.Duels)
        {
            if (!_duels.ContainsKey(duel.DuelId))
                _duels[duel.DuelId] = new DuelObservation(
                    duel.StartedAt, duel.FirstPlayerId, duel.LatePlayerId);
        }

        foreach (var duelId in _duels.Keys.Where(id => !currentIds.Contains(id)).ToArray())
        {
            var observation = _duels[duelId];
            var death = snapshot.Players.Any(player =>
                (player.PlayerId == observation.FirstPlayerId || player.PlayerId == observation.LatePlayerId) &&
                player.Phase == RoomPlayerPhase.Dead);
            _metrics.ObservePvpDuration(now - observation.StartedAt, death ? "victory" : "survived");
            _duels.Remove(duelId);
        }
    }

    private sealed record PveObservation(
        Guid PlayerId,
        TimeSpan LastRoomElapsed,
        TimeSpan ActiveElapsed,
        PveBattlePhase Phase);

    private sealed record DuelObservation(
        DateTimeOffset StartedAt,
        Guid FirstPlayerId,
        Guid LatePlayerId);
}
