using FantasyCard.Domain.Combat;

namespace FantasyCard.Domain.Rooms;

public sealed partial class BattleRoom
{
    public CombatResolution PreviewCards(Guid playerId, Guid battleId, string targetId,
        IReadOnlyList<Guid> cardInstanceIds, long expectedRevision, DateTimeOffset now)
    {
        var previewRoom = Restore(Capture(), _catalog, 0);
        return previewRoom.PlayCards(playerId, battleId, targetId, cardInstanceIds, expectedRevision, now)
            with { RoomRevision = Revision };
    }

    public RoomCombatInfo GetCombatInfo(Guid playerId)
    {
        var player = GetPlayer(playerId);
        var opponent = player.CurrentDuelId is { } duelId
            ? GetPlayer(GetDuel(duelId).OpponentOf(playerId))
            : null;
        double? escapeProbability = opponent is null ? null : DuelRules.EscapeProbability(
            player.HeroClass, player.Combat.Hp, player.Combat.MaximumHp,
            opponent.Combat.Hp, opponent.Combat.MaximumHp, player.Combat.Equipment.ForcedEscapeBonus);
        return new(ToPublicCombatant(player), opponent is null ? null : ToPublicCombatant(opponent), escapeProbability, Revision);
    }

    private static CombatantPublicInfo ToPublicCombatant(RoomPlayerState player) => new(
        player.PlayerId, player.DisplayName, player.HeroClass, player.Combat.Hp, player.Combat.MaximumHp,
        player.Combat.EffectiveMaximumHp, player.Combat.Shield, player.Combat.WeaponLevel,
        player.WornArmor.ToArray(), player.Combat.Equipment, player.Combat.GetPassiveInfo(), player.Combat.DrawIntervalSeconds);
}
