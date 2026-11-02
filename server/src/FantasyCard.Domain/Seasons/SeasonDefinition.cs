using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Seasons;

/// <summary>A published season has explicit UTC boundaries and immutable rule identities.</summary>
public sealed record SeasonDefinition
{
    public const string SupportedRulesetId = "season-v1";
    public const string LegacyArchiveId = "legacy-gdd-0.70";
    public const string TimeZoneId = "Asia/Shanghai";
    public const int DefaultDurationDays = 42;
    public const int MinimumDurationDays = 30;
    public const int MaximumDurationDays = 60;
    public const int MaximumDifficulty = 5;

    private static readonly TimeZoneInfo SeasonTimeZone = TimeZoneInfo.FindSystemTimeZoneById(TimeZoneId);

    public SeasonDefinition(
        string seasonId,
        string rulesetId,
        string configVersion,
        string statsVersion,
        DateTimeOffset startsAtUtc,
        DateTimeOffset endsAtUtc,
        int highestOpenDifficulty)
    {
        RequireIdentifier(seasonId, nameof(seasonId));
        if (seasonId == LegacyArchiveId)
            throw new DomainValidationException("The historical archive cannot be used as a playable season.");
        RequireIdentifier(configVersion, nameof(configVersion));
        RequireIdentifier(statsVersion, nameof(statsVersion));
        if (rulesetId != SupportedRulesetId)
            throw new DomainValidationException("The season ruleset is not supported.");
        if (highestOpenDifficulty is < 0 or > MaximumDifficulty)
            throw new DomainValidationException("Season difficulty must be between D0 and D5.");

        var localStart = TimeZoneInfo.ConvertTime(startsAtUtc, SeasonTimeZone);
        var localEnd = TimeZoneInfo.ConvertTime(endsAtUtc, SeasonTimeZone);
        var durationDays = (localEnd.Date - localStart.Date).Days;
        if (endsAtUtc <= startsAtUtc ||
            durationDays is < MinimumDurationDays or > MaximumDurationDays ||
            localStart.TimeOfDay != TimeSpan.Zero || localEnd.TimeOfDay != TimeSpan.Zero)
            throw new DomainValidationException("A season must span 30 to 60 whole Shanghai calendar days.");

        SeasonId = seasonId;
        RulesetId = rulesetId;
        ConfigVersion = configVersion;
        StatsVersion = statsVersion;
        StartsAtUtc = startsAtUtc.ToUniversalTime();
        EndsAtUtc = endsAtUtc.ToUniversalTime();
        DurationDays = durationDays;
        HighestOpenDifficulty = highestOpenDifficulty;
    }

    public string SeasonId { get; }
    public string RulesetId { get; }
    public string ConfigVersion { get; }
    public string StatsVersion { get; }
    public DateTimeOffset StartsAtUtc { get; }
    public DateTimeOffset EndsAtUtc { get; }
    public int DurationDays { get; }
    public int HighestOpenDifficulty { get; }

    public bool Contains(DateTimeOffset timestamp) => timestamp >= StartsAtUtc && timestamp < EndsAtUtc;

    /// <summary>Natural-day progression is independent of the shop's 04:00 reset.</summary>
    public int NaturalDayAt(DateTimeOffset timestamp)
    {
        if (!Contains(timestamp))
            throw new DomainValidationException("The timestamp is outside the season.");
        var startDate = TimeZoneInfo.ConvertTime(StartsAtUtc, SeasonTimeZone).Date;
        var currentDate = TimeZoneInfo.ConvertTime(timestamp, SeasonTimeZone).Date;
        return (currentDate - startDate).Days + 1;
    }

    public SeasonContext ContextFor(int difficulty)
    {
        if (difficulty < 0 || difficulty > HighestOpenDifficulty)
            throw new DomainValidationException("The selected season difficulty is not open.");
        return new SeasonContext(SeasonId, difficulty, RulesetId, ConfigVersion, StatsVersion);
    }

    public static SeasonDefinition FromCalendarDays(
        string seasonId,
        DateOnly startsOn,
        string configVersion,
        string statsVersion,
        int durationDays = DefaultDurationDays,
        int highestOpenDifficulty = 0)
    {
        if (durationDays is < MinimumDurationDays or > MaximumDurationDays)
            throw new DomainValidationException("A season must span 30 to 60 whole Shanghai calendar days.");
        var start = TimeZoneInfo.ConvertTimeToUtc(startsOn.ToDateTime(TimeOnly.MinValue), SeasonTimeZone);
        var end = TimeZoneInfo.ConvertTimeToUtc(startsOn.AddDays(durationDays).ToDateTime(TimeOnly.MinValue), SeasonTimeZone);
        return new SeasonDefinition(seasonId, SupportedRulesetId, configVersion, statsVersion,
            new DateTimeOffset(start), new DateTimeOffset(end), highestOpenDifficulty);
    }

    internal static void RequireIdentifier(string value, string field)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 80 ||
            value.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not '-' and not '_' and not '.'))
            throw new DomainValidationException($"Invalid season identifier: {field}.");
    }
}
