using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Configuration;

/// <summary>Copied into each room snapshot. Published defaults never enable experiments.</summary>
public sealed record NumericalRules(
    bool CardsSpentDraw = false,
    bool FractionalGuardian = false,
    bool OptionalMonsterPool = false,
    int MonsterCapacity = 5,
    bool BudgetedBotLoot = false,
    int BotLootCount = 2,
    bool MortalBotPve = false)
{
    public static NumericalRules Legacy { get; } = new();
    public FenxianImmediateDrawPolicy FenxianPolicy => CardsSpentDraw
        ? FenxianImmediateDrawPolicy.CoreCardsSpent : FenxianImmediateDrawPolicy.CurrentRhythm;
    public GuardianShieldBonusPolicy GuardianPolicy => FractionalGuardian
        ? GuardianShieldBonusPolicy.FractionalRemainder : GuardianShieldBonusPolicy.CurrentSteps;

    public void Validate()
    {
        if (MonsterCapacity is < 1 or > 8 || BotLootCount is < 0 or > 3)
            throw new DomainValidationException("Numerical candidate limits are outside the supported range.");
    }
}
