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
        var duel = BuildDuel(snapshot, player, state.CombatInfo);
        var allowedActions = BuildAllowedActions(snapshot, player, state.Map, relics, extractionRemaining, springRemaining, now);
        var mapPlayerCount = snapshot.Players.Count(value => value.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted));

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
                relics.Select(pile => pile.PileId).ToArray(),
                allowedActions.Contains("relic.take")
                    ? relics.Select(pile => new RoomRelicPilePayload(
                        pile.PileId,
                        pile.VictimName ?? snapshot.Players.FirstOrDefault(value => value.PlayerId.ToString("D") == pile.VictimId)?.DisplayName ?? "旅人",
                        pile.Version, [])).ToArray()
                    : []),
            new RoomPlayerPayload(
                player.PlayerId,
                player.HeroClass.ToString(),
                player.Phase.ToString(),
                ToCombatant(player.Combat),
                player.Combat.Deck.Hand.Select(card => new RoomCardPayload(card.InstanceId, card.CardId, card.Level, card.ElementOverride?.ToString())).ToArray(),
                player.Combat.Deck.Library.Count,
                player.Combat.Deck.Discard.Count,
                player.Combat.Deck.DrawCharge.ToString("R", CultureInfo.InvariantCulture),
                (player.Inventory?.Items ?? []).Select(ToInventoryItem).ToArray(),
                player.Inventory?.Capacity ?? 0,
                player.Inventory?.SafeSlotIndexes ?? Enumerable.Range(
                    (player.Inventory?.Capacity ?? 0) - (player.Inventory?.SafeSlots ?? 0), player.Inventory?.SafeSlots ?? 0).ToArray(),
                (player.WornArmor ?? []).Select(ToInventoryItem).ToArray(),
                player.Combat.WeaponLevel,
                state.CombatInfo is null ? null : ToBattleStatus(state.CombatInfo.Self),
                PositiveMilliseconds(player.Combat.StunRemaining) ?? 0,
                PositiveMilliseconds(player.Combat.DrawBlockRemaining) ?? 0,
                PositiveMilliseconds(player.Combat.DrawSpeedRemaining) ?? 0,
                PositiveMilliseconds(player.Combat.DrawBlockSpeedRemaining) ?? 0,
                Math.Clamp(4 * (1 + (player.Combat.Equipment?.DrawIntervalModifier ?? 0)),
                    player.Combat.Equipment?.HasRapidDraw == true ? 1.5 : 1.8, 6.0)
                    .ToString("R", CultureInfo.InvariantCulture)),
            player.Pve is null ? null : ToPve(player.Pve),
            duel,
            reward,
            extractionRemaining,
            springRemaining,
            allowedActions,
            mapPlayerCount);
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
            RoomPlayerPhase.Pve when player.Pve?.Phase == PveBattlePhase.Active => BuildPveActions(player),
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
        var actions = new List<string> { "battle.abandon" };
        if (player.CurrentDuelId is not { } duelId) return actions;
        var duel = snapshot.Duels.Single(value => value.DuelId == duelId);
        var opponentId = duel.FirstPlayerId == player.PlayerId ? duel.LatePlayerId : duel.FirstPlayerId;
        var opponent = snapshot.Players.Single(value => value.PlayerId == opponentId);
        if (player.DisconnectedRemaining > TimeSpan.Zero || opponent.DisconnectedRemaining > TimeSpan.Zero) return actions;
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

    private static List<string> BuildPveActions(RoomPlayerSnapshot player)
    {
        var actions = new List<string> { "battle.abandon" };
        if (player.Combat.StunRemaining > TimeSpan.Zero) return actions;
        if (player.Pve!.Monsters.Count(monster => monster.Hp > 0) > 1 ||
            player.Pve.Monsters.Any(monster => monster.Hp > 0 && monster.MonsterId != player.Pve.CurrentTargetId))
            actions.Add("battle.select_target");
        actions.Insert(0, "battle.play_cards");
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
        actions.AddRange(["inventory.move", "inventory.equip", "inventory.unequip"]);
        if (relics.Count > 0 && (player.Pve is null || player.Pve.Phase == PveBattlePhase.Cleared))
            actions.AddRange(["relic.read", "relic.take", "relic.replace"]);
        return actions;
    }

    private static RoomDuelPayload? BuildDuel(BattleRoomSnapshot snapshot, RoomPlayerSnapshot player, RoomCombatInfo? info)
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
                : null,
            opponent.HeroClass.ToString(),
            opponent.DisplayName ?? "旅人",
            info?.EscapeProbability?.ToString("R", CultureInfo.InvariantCulture),
            info?.Opponent is { } opponentInfo ? ToBattleStatus(opponentInfo) : null,
            PositiveMilliseconds(opponent.Combat.StunRemaining) ?? 0,
            PositiveMilliseconds(opponent.Combat.DrawBlockRemaining) ?? 0);
    }

    private static RoomBattleStatusPayload ToBattleStatus(CombatantPublicInfo info)
    {
        var passive = info.Passive;
        var equipment = info.Equipment;
        var bonuses = new List<RoomStatPayload>();
        void Add(string key, double value)
        {
            if (value != 0) bonuses.Add(new(key, value.ToString("R", CultureInfo.InvariantCulture)));
        }
        Add("passive_heal", passive.HealBonus); Add("passive_control", passive.ControlBonus);
        Add("passive_shield", passive.ShieldBonus); Add("weapon_bonus", passive.WeaponBonus);
        Add("shield_flat", passive.ShieldFlatBonus);
        Add("piercing", equipment.PiercingBonus); Add("bulwark_reduction", equipment.BulwarkDamageReduction);
        Add("bulwark_shield", equipment.BulwarkShieldBonus); Add("vitality_heal", equipment.VitalityHealBonus);
        Add("vitality_overcap", equipment.VitalityOvercapBonus); Add("draw_interval", equipment.DrawIntervalModifier);
        Add("forced_escape", equipment.ForcedEscapeBonus);
        foreach (var element in Enum.GetValues<CardElement>().Where(value => value != CardElement.None))
        {
            Add("damage_" + element, equipment.DamageBonus(element));
            Add("resistance_" + element, equipment.Resistance(element));
        }
        var sets = info.WornArmor.Where(item => item.Equipment?.EffectAffix is not null)
            .GroupBy(item => item.Equipment!.EffectAffix!, StringComparer.Ordinal)
            .Select(group =>
            {
                var required = group.Any(item => item.Equipment!.Quality is "Orange" or "Red") ? 2 : 3;
                return new RoomSetPayload(group.Key, group.Count(), required, group.Count() >= required);
            }).ToArray();
        return new(passive.Kind, passive.Combo, passive.CoreElement?.ToString(), bonuses, sets,
            info.DrawIntervalSeconds.ToString("R", CultureInfo.InvariantCulture), passive.ChargeLevel);
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

    internal static RoomInventoryItemPayload ToInventoryItem(ExplorationItem item) => new(
        item.ItemId,
        item.Kind.ToString(),
        item.Quantity,
        item.IsSafe,
        ToEquipment(item.Equipment),
        item.SlotIndex);

    internal static RoomEquipmentPayload? ToEquipment(EquipmentRewardData? item) => item is null ? null :
        new(item.Slot, item.Quality, item.Element, item.EffectAffix, item.SecondaryTrait, item.Level, item.IsBound);

    private static RewardChoiceEventPayload ToReward(RewardChoiceSnapshot reward) => new(
        (int)reward.Layer,
        reward.Options.Select(option => new RewardChoiceOptionPayload(
            option.OptionId,
            (RewardChoiceKindDto)option.Kind,
            option.Item?.ItemId,
            option.Item?.Quantity ?? 0,
            option.HealPercent,
            ToEquipment(option.Item?.Equipment))).ToArray(),
        reward.RefreshCount,
        reward.IsBoss);

    private static RoomCombatantPayload ToCombatant(PlayerCombatSnapshot combat) =>
        new(combat.Hp, combat.MaximumHp,
            (int)Math.Floor(combat.MaximumHp * (1 + Math.Min(0.40, combat.Equipment?.VitalityOvercapBonus ?? 0))), combat.Shield);

    private static RoomPositionPayload ToPosition(MapPosition position) =>
        new(position.Row, position.Column);

    private static long? PositiveMilliseconds(TimeSpan? value) =>
        value is { } duration && duration > TimeSpan.Zero
            ? Math.Max(1, (long)Math.Ceiling(duration.TotalMilliseconds))
            : null;
}
