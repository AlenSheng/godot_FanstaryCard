using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Configuration;

/// <summary>Frozen selection weights; this policy never changes combat attributes.</summary>
public sealed record SeasonLootPreferenceConfig(string DefaultElement, int PreferredWeight, int OtherWeight)
{
    public const int Basis = 10000;
    public static IReadOnlyList<string> Elements { get; } = Array.AsReadOnly(new[] { "Wood", "Fire", "Earth", "Metal", "Water" });

    public void Validate()
    {
        if (!Elements.Contains(DefaultElement, StringComparer.Ordinal) || PreferredWeight != 4000 || OtherWeight != 1500)
            throw new InvalidDataException("Season loot preference requires a valid theme default and 40/15/15/15/15 weights.");
    }

    public string Resolve(string? element)
    {
        var value = element ?? DefaultElement;
        if (!Elements.Contains(value, StringComparer.Ordinal))
            throw new DomainValidationException("Loot preference must be one of the five equipment elements.");
        return value;
    }

    public string Roll(string preference, int roll)
    {
        _ = Resolve(preference);
        ArgumentOutOfRangeException.ThrowIfNegative(roll);
        ArgumentOutOfRangeException.ThrowIfGreaterThanOrEqual(roll, Basis);
        foreach (var element in Elements)
        {
            var weight = element == preference ? PreferredWeight : OtherWeight;
            if (roll < weight) return element;
            roll -= weight;
        }
        throw new InvalidDataException("Season loot preference weights do not cover the probability domain.");
    }
}
