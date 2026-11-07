using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed partial class BattleRoom
{
    private bool _combatPreview;
    public CombatActionStatus GetCombatActionStatus(Guid playerId) => GetPlayer(playerId).CombatActions.Status(Elapsed);
    public string NewCombatActionId(Guid playerId) => GetPlayer(playerId).CombatActions.NewId();
    public bool IsHistoricalCombatAction(Guid playerId, string? actionId) =>
        Season is not null && GetPlayer(playerId).CombatActions.IsHistorical(actionId);

    public CombatResolution ReplayCombatAction(Guid playerId, string? actionId, Guid battleId, string targetId, IReadOnlyList<Guid> ids)
    {
        if (Season is null) throw new DomainValidationException("The room has no seasonal action ledger.");
        return GetPlayer(playerId).CombatActions.Replay(actionId, CombatActionLedger.Hash(battleId, targetId, ids))
            ?? throw new DomainValidationException("The combat action has not been applied.");
    }
}
