using System.Globalization;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Realtime;

internal static class RoomSnapshotProjection
{
    public static RoomSnapshotEventPayload Build(RoomClientState state, Guid playerId, Guid? matchId, DateTimeOffset now)
    {
        var snapshot = state.Snapshot;
        var player = snapshot.Players.Single(value => value.PlayerId == playerId);
        var position = player.Position ?? throw new InvalidOperationException("A room player snapshot has no map position.");
        var relics = (snapshot.RelicPiles ?? [])
            .Where(pile => pile.Position == position)
            .OrderBy(pile => pile.PileId)
            .ToArray();
        var extractionRemaining = PositiveMilliseconds(player.ExtractionRemaining);
        var springRemaining = PositiveMilliseconds(player.SpringDrink?.Remaining);
        var reward = player.RewardChoice is null ? null : ToReward(player.RewardChoice);
        var duel = BuildDuel(snapshot, player);
        var allowedActions = BuildAllowedActions(snapshot, player, state.Map, relics, extractionRemaining, springRemaining, now);

        return new RoomSnapshotEventPayload(
            snapshot.RoomId,
            matchId,
            snapshot.Revision,
            snapshot.ConfigVersion,
            ToPosition(position),
            state.Map.Cells
                .OrderBy(cell => cell.Position.Row)
                .ThenBy(cell => cell.Position.Column)
                .Select(cell => new RoomMapCellPayload(
                    cell.Position.Row, cell.Position.Column, cell.IsBoss, cell.HasSpring))
                .ToArray(),
            extractionRemaining is null && springRemaining is null
                ? state.Map.LegalMoves.Select(ToPosition).ToArray()
                : [],
            new RoomCurrentCellPayload(
                state.Map.CurrentCell.HasEvacuation,
                state.Map.CurrentCell.MonsterGroupId,
                state.Map.CurrentCell.SpringConsumed,
                relics.Select(pile => pile.PileId).ToArray()),
            new RoomPlayerPayload(
                player.PlayerId,
                player.HeroClass.ToString(),
                player.Phase.ToString(),
                ToCombatant(player.Combat),
                player.Combat.Deck.Hand.Select(card => new RoomCardPayload(card.InstanceId, card.CardId)).ToArray(),
                player.Combat.Deck.Library.Count,
                player.Combat.Deck.Discard.Count,
                player.Combat.Deck.DrawCharge.ToString("R", CultureInfo.InvariantCulture),
                (player.Inventory?.Items ?? []).Select(ToInventoryItem).ToArray()),
            player.Pve is null ? null : ToPve(player.Pve),
            duel,
            reward,
            extractionRemaining,
            springRemaining,
            allowedActions);
    }

    private static List<string> BuildAllowedActions(
        BattleRoomSnapshot snapshot,
        RoomPlayerSnapshot player,
        ChaosMapProjection map,
        IReadOnlyList<RelicPileSnapshot> relics,
        long? extractionRemaining,
        long? springRemaining,
        DateTimeOffset now)
    {
        if (extractionRemaining is not null || springRemaining is not null) return [];
        return player.Phase switch
        {
            RoomPlayerPhase.Pve when player.Pve?.Phase == PveBattlePhase.Active && player.Combat.StunRemaining <= TimeSpan.Zero =>
                player.Pve.Monsters.Count(monster => monster.Hp > 0) > 1 ||
                player.Pve.Monsters.Any(monster => monster.Hp > 0 && monster.MonsterId != player.Pve.CurrentTargetId)
                    ? ["battle.play_cards", "battle.select_target"]
                    : ["battle.play_cards"],
            RoomPlayerPhase.Choice => ["choice.read", "choice.refresh", "choice.pick"],
            RoomPlayerPhase.Pvp => BuildDuelActions(snapshot, player, now),
            RoomPlayerPhase.ActionBar => BuildActionBarActions(player, map, relics),
            _ => []
        };
    }

    private static List<string> BuildDuelActions(
        BattleRoomSnapshot snapshot,
        RoomPlayerSnapshot player,
        DateTimeOffset now)
    {
        if (player.CurrentDuelId is not { } duelId) return [];
        var duel = snapshot.Duels.Single(value => value.DuelId == duelId);
        var opponentId = duel.FirstPlayerId == player.PlayerId ? duel.LatePlayerId : duel.FirstPlayerId;
        var opponent = snapshot.Players.Single(value => value.PlayerId == opponentId);
        if (player.DisconnectedRemaining > TimeSpan.Zero || opponent.DisconnectedRemaining > TimeSpan.Zero) return [];
        var actions = new List<string>();
        if (player.Combat.StunRemaining <= TimeSpan.Zero &&
            (duel.LatePlayerId != player.PlayerId || now >= duel.LatePlayerUnlockAt))
            actions.Add("battle.play_cards");
        if (now <= duel.LeaveWindowEndsAt && !(duel.LeaveRequests ?? []).Contains(player.PlayerId))
            actions.Add("duel.leave");
        if (duel.EscapeAttempt is null &&
            !(duel.EscapeCooldowns ?? []).Any(value => value.PlayerId == player.PlayerId && value.Remaining > TimeSpan.Zero))
            actions.Add("duel.escape");
        return actions;
    }

    private static List<string> BuildActionBarActions(
        RoomPlayerSnapshot player,
        ChaosMapProjection map,
        IReadOnlyList<RelicPileSnapshot> relics)
    {
        var actions = new List<string>();
        if (map.LegalMoves.Count > 0) actions.Add("room.move");
        if (map.Cells.Single(cell => cell.Position == map.Self).HasSpring && !map.CurrentCell.SpringConsumed)
            actions.Add("action.spring");
        if ((player.Inventory?.Items ?? []).Any(item => item.Kind == ExplorationItemKind.HealthPotion))
            actions.Add("action.potion");
        if (map.CurrentCell.HasEvacuation && (player.Pve is null || player.Pve.Phase == PveBattlePhase.Cleared))
            actions.Add("action.extract");
        if (relics.Count > 0) actions.Add("relic.take");
        return actions;
    }

    private static RoomDuelPayload? BuildDuel(BattleRoomSnapshot snapshot, RoomPlayerSnapshot player)
    {
        if (player.CurrentDuelId is not { } duelId) return null;
        var duel = snapshot.Duels.Single(value => value.DuelId == duelId);
        var opponentId = duel.FirstPlayerId == player.PlayerId ? duel.LatePlayerId : duel.FirstPlayerId;
        var opponent = snapshot.Players.Single(value => value.PlayerId == opponentId);
        return new RoomDuelPayload(
            duel.DuelId,
            opponentId,
            ToCombatant(opponent.Combat),
            duel.LatePlayerUnlockAt.ToUnixTimeMilliseconds(),
            duel.LeaveWindowEndsAt.ToUnixTimeMilliseconds(),
            (duel.LeaveRequests ?? []).Contains(player.PlayerId),
            duel.EscapeAttempt?.PlayerId == player.PlayerId
                ? PositiveMilliseconds(duel.EscapeAttempt.Remaining)
                : null);
    }

    private static RoomPvePayload ToPve(PveBattleSnapshot pve) => new(
        pve.BattleId,
        pve.Phase.ToString(),
        pve.CurrentTargetId,
        pve.Monsters.Select(monster =>
        {
            var intent = monster.Intents[monster.IntentIndex % monster.Intents.Count];
            return new RoomMonsterPayload(
                monster.MonsterId,
                monster.MaximumHp,
                monster.Hp,
                monster.Shield,
                intent.Kind.ToString(),
                intent.Value,
                intent.Element.ToString(),
                (long)monster.IntervalProgress.TotalMilliseconds,
                (long)monster.WindupRemaining.TotalMilliseconds,
                (long)monster.StunRemaining.TotalMilliseconds,
                monster.BossPhase);
        }).ToArray());

    private static RoomInventoryItemPayload ToInventoryItem(ExplorationItem item) => new(
        item.ItemId,
        item.Kind.ToString(),
        item.Quantity,
        item.IsSafe,
        item.Equipment is null
            ? null
            : new RoomEquipmentPayload(
                item.Equipment.Slot,
                item.Equipment.Quality,
                item.Equipment.Element,
                item.Equipment.EffectAffix,
                item.Equipment.SecondaryTrait));

    private static RewardChoiceEventPayload ToReward(RewardChoiceSnapshot reward) => new(
        (int)reward.Layer,
        reward.Options.Select(option => new RewardChoiceOptionPayload(
            option.OptionId,
            (RewardChoiceKindDto)option.Kind,
            option.Item?.ItemId,
            option.Item?.Quantity ?? 0,
            option.HealPercent)).ToArray(),
        reward.RefreshCount,
        reward.IsBoss);

    private static RoomCombatantPayload ToCombatant(PlayerCombatSnapshot combat) =>
        new(combat.Hp, combat.MaximumHp, combat.MaximumHp, combat.Shield);

    private static RoomPositionPayload ToPosition(MapPosition position) =>
        new(position.Row, position.Column);

    private static long? PositiveMilliseconds(TimeSpan? value) =>
        value is { } duration && duration > TimeSpan.Zero
            ? Math.Max(1, (long)Math.Ceiling(duration.TotalMilliseconds))
            : null;
}
