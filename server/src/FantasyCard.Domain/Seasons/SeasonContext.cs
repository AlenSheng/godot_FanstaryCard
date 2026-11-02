using System.Globalization;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Seasons;

/// <summary>The same context must follow preparation, room recovery, loot and settlement.</summary>
public sealed record SeasonContext
{
    public SeasonContext(string seasonId, int difficulty, string rulesetId, string configVersion, string statsVersion)
    {
        SeasonDefinition.RequireIdentifier(seasonId, nameof(seasonId));
        SeasonDefinition.RequireIdentifier(configVersion, nameof(configVersion));
        SeasonDefinition.RequireIdentifier(statsVersion, nameof(statsVersion));
        if (rulesetId != SeasonDefinition.SupportedRulesetId)
            throw new DomainValidationException("The season ruleset is not supported.");
        if (difficulty is < 0 or > SeasonDefinition.MaximumDifficulty)
            throw new DomainValidationException("Season difficulty must be between D0 and D5.");
        SeasonId = seasonId;
        Difficulty = difficulty;
        RulesetId = rulesetId;
        ConfigVersion = configVersion;
        StatsVersion = statsVersion;
    }

    public string SeasonId { get; }
    public int Difficulty { get; }
    public string DifficultyId => "D" + Difficulty.ToString(CultureInfo.InvariantCulture);
    public string RulesetId { get; }
    public string ConfigVersion { get; }
    public string StatsVersion { get; }

    /// <summary>Projection never changes the permanent card or signature-weapon level.</summary>
    public int ProjectPermanentLevel(int actualLevel)
    {
        if (actualLevel is < 0 or > 5)
            throw new DomainValidationException("Permanent card and weapon levels must be between zero and five.");
        return Math.Min(actualLevel, Difficulty);
    }

    public void RequireSameDomain(SeasonContext other)
    {
        ArgumentNullException.ThrowIfNull(other);
        if (this != other)
            throw new DomainValidationException("Season, difficulty or rule versions do not match.");
    }
}
