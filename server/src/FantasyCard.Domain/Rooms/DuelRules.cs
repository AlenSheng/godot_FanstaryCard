using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public static class DuelRules
{
    public static double EscapeProbability(
        HeroClass heroClass,
        int ownHp,
        int ownMaximumHp,
        int opponentHp,
        int opponentMaximumHp,
        double shoeBonus = 0,
        double goldenCicadaBonus = 0)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(ownMaximumHp, 0);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(opponentMaximumHp, 0);
        ArgumentOutOfRangeException.ThrowIfNegative(ownHp);
        ArgumentOutOfRangeException.ThrowIfNegative(opponentHp);
        ArgumentOutOfRangeException.ThrowIfNegative(shoeBonus);
        ArgumentOutOfRangeException.ThrowIfNegative(goldenCicadaBonus);

        var ownPercent = 100d * Math.Clamp(ownHp, 0, ownMaximumHp) / ownMaximumHp;
        var opponentPercent = 100d * Math.Clamp(opponentHp, 0, opponentMaximumHp) / opponentMaximumHp;
        var gap = Math.Max(0, opponentPercent - ownPercent);
        var classBonus = heroClass switch
        {
            HeroClass.Priest => 0.08,
            HeroClass.Mage => 0.05,
            HeroClass.Guardian => 0.03,
            _ => throw new DomainValidationException("Unknown hero class.")
        };
        return Math.Clamp(0.06 + 0.006 * gap + classBonus + shoeBonus + goldenCicadaBonus, 0.06, 0.70);
    }
}
