using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class DuelRulesTests
{
    [Theory]
    [InlineData(HeroClass.Priest, 50, 100, 50, 100, 0.14)]
    [InlineData(HeroClass.Mage, 50, 100, 50, 100, 0.11)]
    [InlineData(HeroClass.Guardian, 50, 100, 50, 100, 0.09)]
    [InlineData(HeroClass.Priest, 25, 100, 75, 100, 0.44)]
    public void EscapeProbability_MatchesGddGoldenValues(
        HeroClass heroClass, int ownHp, int ownMax, int opponentHp, int opponentMax, double expected)
    {
        Assert.Equal(expected, DuelRules.EscapeProbability(heroClass, ownHp, ownMax, opponentHp, opponentMax), 6);
    }

    [Fact]
    public void EscapeProbability_IsCappedAtSeventyPercent()
    {
        var probability = DuelRules.EscapeProbability(HeroClass.Priest, 10, 100, 90, 100, 0.15);

        Assert.Equal(0.70, probability, 6);
    }
}
