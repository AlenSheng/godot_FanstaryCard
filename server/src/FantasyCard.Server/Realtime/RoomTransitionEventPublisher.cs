using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;

namespace FantasyCard.Server.Realtime;

internal sealed class RoomTransitionEventPublisher(
    BattleRoomSnapshot initial,
    RealtimeEventStore eventStore,
    ConnectionRegistry? connections = null)
{
    private BattleRoomSnapshot _previous = initial;

    public async Task ObserveCombatAsync(BattleRoomSnapshot current, IReadOnlyList<CombatFeedbackResolution> feedback)
    {
        foreach (var entry in feedback)
        {
            var result = entry.Resolution;
            if (!Guid.TryParse(result.TargetId, out var targetId)) continue;
            var target = current.Players.SingleOrDefault(player => player.PlayerId == targetId);
            if (target is null || target.IsBot || targetId == result.AttackerId) continue;
            var payload = new BattleComboResolvedEventPayload(result.BattleId, result.AttackerId, result.TargetId,
                result.Damage, result.ShieldDamage, result.HpDamage, result.Heal, result.ShieldGain,
                result.TargetDefeated, result.BattleEnded,
                result.DamageSegments?.Select(segment => new CombatDamageSegmentPayload(segment.Kind, segment.Amount)).ToArray(),
                SourceId: entry.SourceId,
                ResonanceMultiplier: result.ResonanceMultiplier.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                ConflictPairCount: result.ConflictPairCount,
                ConflictCancellation: result.ConflictCancellation.ToString("R", System.Globalization.CultureInfo.InvariantCulture));
            var message = eventStore.Create(targetId, "combat.hit", "room-combat", payload, roomRevision: result.RoomRevision);
            if (connections is not null)
                await connections.SendPresentationAsync(targetId, message);
        }
    }

    public async Task ObserveAsync(BattleRoomSnapshot current)
    {
        var previous = _previous;
        _previous = current;
        var deliveries = new List<(Guid PlayerId, ServerEvent Event)>();

        foreach (var duel in previous.Duels.Where(old => current.Duels.All(value => value.DuelId != old.DuelId)))
        {
            var first = current.Players.Single(player => player.PlayerId == duel.FirstPlayerId);
            var late = current.Players.Single(player => player.PlayerId == duel.LatePlayerId);
            var dead = first.Phase == RoomPlayerPhase.Dead ? first : late.Phase == RoomPlayerPhase.Dead ? late : null;
            var reason = dead is not null
                ? "death"
                : duel.EscapeAttempt is not null ? "escaped" : "mutual_leave";
            Guid? winnerId = dead is null
                ? null
                : dead.PlayerId == first.PlayerId ? late.PlayerId : first.PlayerId;
            var payload = new DuelEndedEventPayload(duel.DuelId, reason, winnerId);
            AddIfHuman(first, "duel.ended", payload);
            AddIfHuman(late, "duel.ended", payload);
        }

        foreach (var before in previous.Duels.Where(old => old.EscapeAttempt is not null))
        {
            var after = current.Duels.SingleOrDefault(value => value.DuelId == before.DuelId);
            if (after is null || after.EscapeAttempt is not null) continue;
            var attempt = before.EscapeAttempt!;
            var failed = (after.EscapeCooldowns ?? []).Any(value =>
                value.PlayerId == attempt.PlayerId && value.Remaining > TimeSpan.Zero);
            var type = failed ? "duel.escape_failed" : "duel.escape_interrupted";
            var status = failed ? "Failed" : "Interrupted";
            var payload = new DuelEscapeEventPayload(before.DuelId, attempt.Probability, status);
            AddIfHuman(current.Players.Single(player => player.PlayerId == before.FirstPlayerId), type, payload);
            AddIfHuman(current.Players.Single(player => player.PlayerId == before.LatePlayerId), type, payload);
        }

        foreach (var player in current.Players.Where(player => player.Phase == RoomPlayerPhase.Dead))
        {
            var before = previous.Players.SingleOrDefault(value => value.PlayerId == player.PlayerId);
            if (before is null || before.Phase == RoomPlayerPhase.Dead || player.IsBot) continue;
            var cause = before.Phase == RoomPlayerPhase.Pvp ? "PvpDeath" : "PveDeath";
            Add(player.PlayerId, "player.died", new PlayerDiedEventPayload(player.PlayerId, cause, before.CurrentDuelId));
        }

        foreach (var player in current.Players)
        {
            var before = previous.Players.SingleOrDefault(value => value.PlayerId == player.PlayerId);
            if (before is null || player.IsBot) continue;
            if (before.ExtractionRemaining is { } extraction && extraction > TimeSpan.Zero &&
                player.ExtractionRemaining is null)
            {
                var completed = player.Phase == RoomPlayerPhase.Extracted;
                Add(player.PlayerId, completed ? "action.extract_completed" : "action.extract_cancelled",
                    new ActionExtractEventPayload(completed ? "Completed" : "Cancelled", TimeSpan.Zero));
            }
            if (before.SpringDrink is { } spring && spring.Remaining > TimeSpan.Zero && player.SpringDrink is null)
            {
                var cancelled = player.Phase == RoomPlayerPhase.Pvp;
                Add(player.PlayerId, cancelled ? "action.spring_cancelled" : "action.spring_completed",
                    new ActionSpringEventPayload(cancelled ? "Cancelled" : "Completed", TimeSpan.Zero));
            }
        }

        if (connections is null) return;
        foreach (var delivery in deliveries)
            await connections.SendPresentationAsync(delivery.PlayerId, delivery.Event);

        var mapPlayerCount = ActiveMapPlayerCount(current);
        if (mapPlayerCount == ActiveMapPlayerCount(previous)) return;
        foreach (var player in current.Players.Where(value => !value.IsBot && IsOnMap(value)))
        {
            var update = eventStore.Create(
                player.PlayerId,
                "map.player_count",
                "room-population",
                new MapPlayerCountEventPayload(mapPlayerCount),
                roomRevision: current.Revision);
            await connections.SendPresentationAsync(player.PlayerId, update);
        }

        void AddIfHuman(RoomPlayerSnapshot player, string type, object payload)
        {
            if (!player.IsBot) Add(player.PlayerId, type, payload);
        }

        void Add(Guid playerId, string type, object payload)
        {
            deliveries.Add((playerId, eventStore.Create(
                playerId,
                type,
                "room-transition",
                payload,
                roomRevision: current.Revision)));
        }
    }

    private static int ActiveMapPlayerCount(BattleRoomSnapshot snapshot) =>
        snapshot.Players.Count(IsOnMap);

    private static bool IsOnMap(RoomPlayerSnapshot player) =>
        player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted);
}
