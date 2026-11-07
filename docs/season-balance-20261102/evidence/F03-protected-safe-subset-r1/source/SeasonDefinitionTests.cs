using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Seasons;

public sealed class SeasonDefinitionTests
{
    [Fact]
    public void DefaultSeasonUsesFortyTwoShanghaiDaysAndHalfOpenUtcBoundaries()
    {
        var season = SeasonDefinition.FromCalendarDays("season-test", new DateOnly(2026, 11, 2), "config-1", "stats-1");

        Assert.Equal(42, season.DurationDays);
        Assert.Equal(new DateTimeOffset(2026, 11, 1, 16, 0, 0, TimeSpan.Zero), season.StartsAtUtc);
        Assert.Equal(new DateTimeOffset(2026, 12, 13, 16, 0, 0, TimeSpan.Zero), season.EndsAtUtc);
        Assert.False(season.Contains(season.StartsAtUtc.AddTicks(-1)));
        Assert.True(season.Contains(season.StartsAtUtc));
        Assert.True(season.Contains(season.EndsAtUtc.AddTicks(-1)));
        Assert.False(season.Contains(season.EndsAtUtc));
        Assert.Equal(1, season.NaturalDayAt(season.StartsAtUtc));
        Assert.Equal(42, season.NaturalDayAt(season.EndsAtUtc.AddTicks(-1)));
        Assert.Throws<DomainValidationException>(() => season.NaturalDayAt(season.EndsAtUtc));
    }

    [Theory]
    [InlineData(30)]
    [InlineData(42)]
    [InlineData(60)]
    public void CalendarDurationDoesNotTurnIntoShopBusinessDay(int days)
    {
        var season = SeasonDefinition.FromCalendarDays("season-test", new DateOnly(2026, 11, 2), "config-1", "stats-1", days);

        Assert.Equal(days, season.DurationDays);
        Assert.Equal(1, season.NaturalDayAt(season.StartsAtUtc.AddHours(3).AddMinutes(59)));
        Assert.Equal(1, season.NaturalDayAt(season.StartsAtUtc.AddHours(4)));
        Assert.Equal(2, season.NaturalDayAt(season.StartsAtUtc.AddDays(1)));
    }

    [Theory]
    [InlineData(29)]
    [InlineData(61)]
    [InlineData(0)]
    [InlineData(-1)]
    public void DurationOutsidePublishedRangeIsRejected(int days)
    {
        Assert.Throws<DomainValidationException>(() => SeasonDefinition.FromCalendarDays(
            "season-test", new DateOnly(2026, 11, 2), "config-1", "stats-1", days));
    }

    [Fact]
    public void ExplicitOffsetsNormalizeToUtcAndPartialCalendarDaysAreRejected()
    {
        var start = new DateTimeOffset(2026, 11, 2, 0, 0, 0, TimeSpan.FromHours(8));
        var season = new SeasonDefinition("season-test", "season-v1", "config-1", "stats-1", start, start.AddDays(42), 5);

        Assert.Equal(TimeSpan.Zero, season.StartsAtUtc.Offset);
        Assert.Equal(start.ToUniversalTime(), season.StartsAtUtc);
        Assert.Throws<DomainValidationException>(() => new SeasonDefinition(
            "season-test", "season-v1", "config-1", "stats-1", start, start.AddDays(42).AddMinutes(1), 5));
        Assert.Throws<DomainValidationException>(() => new SeasonDefinition(
            "season-test", "season-v1", "config-1", "stats-1", start.AddHours(12), start.AddDays(42).AddHours(12), 5));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public void DifficultyProjectsPermanentLevelsWithoutChangingTheirValue(int difficulty)
    {
        var season = SeasonDefinition.FromCalendarDays("season-test", new DateOnly(2026, 11, 2), "config-1", "stats-1", highestOpenDifficulty: 5);
        var context = season.ContextFor(difficulty);

        Assert.Equal("D" + difficulty, context.DifficultyId);
        for (var actual = 0; actual <= 5; actual++)
            Assert.Equal(Math.Min(actual, difficulty), context.ProjectPermanentLevel(actual));
        Assert.Throws<DomainValidationException>(() => context.ProjectPermanentLevel(-1));
        Assert.Throws<DomainValidationException>(() => context.ProjectPermanentLevel(6));
        Assert.Throws<DomainValidationException>(() => season.ContextFor(6));
    }

    [Fact]
    public void DefaultOpensOnlyD0AndRejectsUnknownRulesOrIdentifiers()
    {
        var season = SeasonDefinition.FromCalendarDays("season-test", new DateOnly(2026, 11, 2), "config-1", "stats-1");

        Assert.Equal(0, season.ContextFor(0).Difficulty);
        Assert.Throws<DomainValidationException>(() => season.ContextFor(1));
        Assert.Throws<DomainValidationException>(() => new SeasonContext("season-test", 0, "unknown", "config-1", "stats-1"));
        Assert.Throws<DomainValidationException>(() => new SeasonContext("other/season", 0, "season-v1", "config-1", "stats-1"));
        Assert.Throws<DomainValidationException>(() => new SeasonContext("season-test", 0, "season-v1", "", "stats-1"));
    }

    [Fact]
    public void HistoricalArchiveCannotBePublishedOrRestoredAsAPlayableSeason()
    {
        Assert.Throws<DomainValidationException>(() => SeasonDefinition.FromCalendarDays(
            SeasonDefinition.LegacyArchiveId, new DateOnly(2026, 11, 2), "config-1", "stats-1"));
        Assert.Throws<DomainValidationException>(() => new SeasonContext(
            SeasonDefinition.LegacyArchiveId, 0, "season-v1", "config-1", "stats-1"));
    }

    [Fact]
    public void ContextSurvivesSerializationAndEveryDomainDimensionIsCompared()
    {
        var context = new SeasonContext("season-test", 2, "season-v1", "config-1", "stats-1");
        var restored = JsonSerializer.Deserialize<SeasonContext>(JsonSerializer.Serialize(context));

        Assert.Equal(context, restored);
        context.RequireSameDomain(Assert.IsType<SeasonContext>(restored));
        Assert.Throws<DomainValidationException>(() => context.RequireSameDomain(new("other-season", 2, "season-v1", "config-1", "stats-1")));
        Assert.Throws<DomainValidationException>(() => context.RequireSameDomain(new("season-test", 3, "season-v1", "config-1", "stats-1")));
        Assert.Throws<DomainValidationException>(() => context.RequireSameDomain(new("season-test", 2, "season-v1", "config-2", "stats-1")));
        Assert.Throws<DomainValidationException>(() => context.RequireSameDomain(new("season-test", 2, "season-v1", "config-1", "stats-2")));
    }
}
