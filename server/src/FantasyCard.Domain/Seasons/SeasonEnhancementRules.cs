using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Seasons;

/// <summary>Season armor prices use their original published stats and per-step calendar scaling.</summary>
public static class SeasonEnhancementRules
{
    public static int ArmorCost(GameConfigCatalog configuration, SeasonDefinition season, string quality, int targetLevel)
    {
        if (configuration.Version != season.ConfigVersion)
            throw new DomainValidationException("Armor enhancement configuration differs from its original season.");
        var policy = configuration.ResolveSeasonEquipment(season.StatsVersion);
        var cost = configuration.EquipmentQuality(quality, season.StatsVersion).EnhancementCost(targetLevel);
        // Archives predating the season-equipment policy retain their original prices.
        return policy is null ? cost : ScaleArmorStep(cost, season.DurationDays);
    }

    public static int ScaleArmorStep(int baseCost, int durationDays)
    {
        if (baseCost <= 0 || durationDays is < SeasonDefinition.MinimumDurationDays or > SeasonDefinition.MaximumDurationDays)
            throw new DomainValidationException("Armor enhancement price or season duration is invalid.");
        var numerator = Math.Min(durationDays, SeasonDefinition.DefaultDurationDays);
        return checked((int)(((long)baseCost * numerator + SeasonDefinition.DefaultDurationDays - 1) /
            SeasonDefinition.DefaultDurationDays));
    }
}
