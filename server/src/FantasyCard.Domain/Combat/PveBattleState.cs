namespace FantasyCard.Domain.Combat;

public sealed class PveBattleState
{
    private List<MonsterCombatState> _monsters;

    public PveBattleState(
        Guid battleId,
        string? currentTargetId,
        IReadOnlyList<MonsterCombatState> monsters)
    {
        if (battleId == Guid.Empty)
        {
            throw new ArgumentException("PVE battle id cannot be empty.", nameof(battleId));
        }
        if (monsters.Count == 0)
        {
            throw new ArgumentException("A PVE battle requires at least one monster.", nameof(monsters));
        }

        BattleId = battleId;
        CurrentTargetId = currentTargetId;
        _monsters = monsters.ToList();
    }

    public Guid BattleId { get; }
    public PveBattlePhase Phase { get; private set; } = PveBattlePhase.Active;
    public string? CurrentTargetId { get; private set; }
    public IReadOnlyList<MonsterCombatState> Monsters => _monsters;
    public bool IsCleared => _monsters.All(monster => monster.IsDead);

    public MonsterCombatState GetTarget(string targetId) =>
        _monsters.SingleOrDefault(monster => string.Equals(monster.MonsterId, targetId, StringComparison.Ordinal))
        ?? throw new Players.DomainValidationException($"Monster target '{targetId}' is not in this PVE battle.");

    public bool SelectTarget(string targetId)
    {
        if (Phase != PveBattlePhase.Active)
            throw new Players.DomainValidationException("Targets can only be selected during an active PVE battle.");
        var target = GetTarget(targetId);
        if (target.IsDead)
            throw new Players.DomainValidationException("A defeated monster cannot be selected.");
        if (string.Equals(CurrentTargetId, targetId, StringComparison.Ordinal)) return false;
        CurrentTargetId = targetId;
        return true;
    }

    public void Freeze() => Phase = PveBattlePhase.Frozen;

    public void Activate() => Phase = IsCleared ? PveBattlePhase.Cleared : PveBattlePhase.Active;

    public void MarkDead() => Phase = PveBattlePhase.Dead;

    public void RefreshPhase()
    {
        if (IsCleared)
        {
            Phase = PveBattlePhase.Cleared;
        }
    }

    public PveBattleSnapshot Capture() =>
        new(
            BattleId,
            Phase,
            CurrentTargetId,
            _monsters.Select(monster => monster.Capture()).ToArray());

    public void Restore(PveBattleSnapshot snapshot)
    {
        if (snapshot.BattleId != BattleId)
        {
            throw new Players.DomainValidationException("PVE snapshot belongs to another battle.");
        }
        Phase = snapshot.Phase;
        CurrentTargetId = snapshot.CurrentTargetId;
        _monsters = snapshot.Monsters.Select(MonsterCombatState.Restore).ToList();
    }

    public static PveBattleState Rehydrate(PveBattleSnapshot snapshot)
    {
        var state = new PveBattleState(
            snapshot.BattleId,
            snapshot.CurrentTargetId,
            snapshot.Monsters.Select(MonsterCombatState.Restore).ToArray());
        state.Phase = snapshot.Phase;
        return state;
    }
}
