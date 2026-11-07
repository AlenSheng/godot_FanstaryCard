using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonEnhancementTests
{
    [Theory]
    [InlineData("White", 4, 28)]
    [InlineData("Green", 6, 42)]
    [InlineData("Blue", 8, 68)]
    [InlineData("Purple", 10, 130)]
    [InlineData("Orange", 20, 260)]
    [InlineData("Red", 30, 390)]
    public void PublishedSeasonPricesHaveTheProposalTotalsAndDoNotReplacePermanentCosts(string quality, int plusThree, int plusFive)
    {
        var catalog = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("enhancement", new(2026, 11, 1), catalog.Version, "season-equipment-v1");
        var costs = Enumerable.Range(1, 5).Select(level => SeasonEnhancementRules.ArmorCost(catalog, season, quality, level)).ToArray();
        Assert.Equal(plusThree, costs.Take(3).Sum()); Assert.Equal(plusFive, costs.Sum());
        Assert.Equal(248, Enumerable.Range(1, 5).Sum(level => catalog.EquipmentQuality("White").EnhancementCost(level)));
    }

    [Theory]
    [InlineData(30, 52, 573)]
    [InlineData(42, 60, 780)]
    [InlineData(60, 60, 780)]
    public void CalendarScalingRoundsEachArmorStepUpRatherThanScalingTheWholeLoadout(int days, int plusThree, int plusFive)
    {
        var catalog = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("enhancement", new(2026, 11, 1), catalog.Version, "season-equipment-v1", days);
        var costs = Enumerable.Range(1, 5).Select(level => SeasonEnhancementRules.ArmorCost(catalog, season, "Orange", level) +
            4 * SeasonEnhancementRules.ArmorCost(catalog, season, "Purple", level)).ToArray();
        Assert.Equal(plusThree, costs.Take(3).Sum()); Assert.Equal(plusFive, costs.Sum());
        Assert.Equal(plusThree + 6, costs.Take(3).Sum() + 4 * 1 + 2); // C08 owns the actual five-body reforge transaction.
    }

    [Fact]
    public void MissingOrDifferentVersionAndInvalidStepInputsCannotProduceFreeEnhancement()
    {
        var catalog = GameConfigCatalog.Current;
        var unknown = SeasonDefinition.FromCalendarDays("enhancement", new(2026, 11, 1), catalog.Version, "unknown-stats");
        Assert.Throws<DomainValidationException>(() => SeasonEnhancementRules.ArmorCost(catalog, unknown, "White", 1));
        var different = SeasonDefinition.FromCalendarDays("enhancement", new(2026, 11, 1), "another-config", "season-equipment-v1");
        Assert.Throws<DomainValidationException>(() => SeasonEnhancementRules.ArmorCost(catalog, different, "White", 1));
        Assert.Throws<DomainValidationException>(() => SeasonEnhancementRules.ScaleArmorStep(0, 42));
        Assert.Throws<DomainValidationException>(() => SeasonEnhancementRules.ScaleArmorStep(1, 29));
    }
}
