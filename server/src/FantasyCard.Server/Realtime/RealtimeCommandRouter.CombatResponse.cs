using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;

namespace FantasyCard.Server.Realtime;

public sealed partial class RealtimeCommandRouter
{
    private ServerEvent CombatResponse(Guid playerId, ClientCommand command, string traceId,
        CombatResolution resolution, IReadOnlyList<Guid> ids, bool preview = false) =>
        _eventStore.Create(playerId, preview ? "combat.previewed" : "battle.combo_resolved", traceId,
            new BattleComboResolvedEventPayload(
                    resolution.BattleId,
                    resolution.AttackerId,
                    resolution.TargetId,
                    resolution.Damage,
                    resolution.ShieldDamage,
                    resolution.HpDamage,
                    resolution.Heal,
                    resolution.ShieldGain,
                    resolution.TargetDefeated,
                    resolution.BattleEnded,
                    resolution.DamageSegments?.Select(segment => new CombatDamageSegmentPayload(segment.Kind, segment.Amount)).ToArray(),
                    resolution.CoreElement?.ToString(), resolution.CoreCount,
                    resolution.StunSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.DrawBlockSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.HealthCost, resolution.DrawCharge.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.ImmediateDraw, ids, resolution.AttackerId.ToString("D"),
                    resolution.DrawSpeedSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.DrawSpeedModifier.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.DrawBlockSpeedSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.ResonanceMultiplier.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.ConflictPairCount,
                    resolution.ConflictCancellation.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                    resolution.CombatActionId, resolution.ActionReplayed), command.RequestId, resolution.RoomRevision);
}
