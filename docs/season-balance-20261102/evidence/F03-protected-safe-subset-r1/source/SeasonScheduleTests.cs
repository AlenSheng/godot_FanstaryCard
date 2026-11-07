using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Seasons;

public sealed class SeasonScheduleTests
{
    [Fact]
    public void EmptyScheduleRetainsExplicitLegacyMode()
    {
        var result = SeasonSchedule.Resolve([], DateTimeOffset.UtcNow);
        Assert.Equal(SeasonLifecycleStage.Legacy, result.Stage);
        Assert.True(result.LegacyAllowed);
        Assert.Null(result.Current);
    }

    [Fact]
    public void FirstSeasonDoesNotCloseLegacyBeforeItsPublishedStart()
    {
        var first = Define("first", new DateOnly(2026, 11, 2));
        var result = SeasonSchedule.Resolve([first], first.StartsAtUtc.AddTicks(-1));
        Assert.Equal(SeasonLifecycleStage.Upcoming, result.Stage);
        Assert.True(result.LegacyAllowed);
        Assert.Equal(first, result.Next);
    }

    [Fact]
    public void ExactBoundarySwitchesToAdjacentSeasonWithoutLegacyFallback()
    {
        var first = Define("first", new DateOnly(2026, 11, 2));
        var second = Define("second", new DateOnly(2026, 12, 14));
        var result = SeasonSchedule.Resolve([second, first], first.EndsAtUtc);
        Assert.Equal(SeasonLifecycleStage.Active, result.Stage);
        Assert.Equal(second, result.Current);
        Assert.False(result.LegacyAllowed);
        Assert.Null(result.Next);
    }

    [Fact]
    public void InterSeasonGapAndFinalClosureCannotReopenOldEconomy()
    {
        var first = Define("first", new DateOnly(2026, 11, 2));
        var second = Define("second", new DateOnly(2026, 12, 15));
        var gap = SeasonSchedule.Resolve([first, second], first.EndsAtUtc);
        Assert.Equal(SeasonLifecycleStage.Closed, gap.Stage);
        Assert.False(gap.LegacyAllowed);
        Assert.Null(gap.Current);
        Assert.Equal(second, gap.Next);
        var end = SeasonSchedule.Resolve([first, second], second.EndsAtUtc);
        Assert.Equal(SeasonLifecycleStage.Closed, end.Stage);
        Assert.False(end.LegacyAllowed);
        Assert.Null(end.Next);
    }

    [Fact]
    public void OverlappingInMemoryConfigurationIsRejectedAsWellAsDatabasePublication()
    {
        Assert.Throws<DomainValidationException>(() => SeasonSchedule.Resolve(
            [Define("first", new DateOnly(2026, 11, 2)), Define("second", new DateOnly(2026, 11, 3))], DateTimeOffset.UtcNow));
    }

    private static SeasonDefinition Define(string id, DateOnly start) =>
        SeasonDefinition.FromCalendarDays(id, start, "config-1", "stats-1");
}
