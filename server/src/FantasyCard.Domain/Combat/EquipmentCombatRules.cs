using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Combat;

public sealed record CombatEquipmentItem(
    Guid ItemId,
    string Slot,
    string Quality,
    int Level,
    CardElement Element,
    string? EffectAffix,
    string? SecondaryTrait,
    string? UniqueAffix = null,
    CardElement? UniqueElement = null);

public sealed record ElementalEquipmentModifiers(
    double FireDamageBonus = 0,
    double WoodDamageBonus = 0,
    double EarthDamageBonus = 0,
    double MetalDamageBonus = 0,
    double WaterDamageBonus = 0,
    double FireResistance = 0,
    double WoodResistance = 0,
    double EarthResistance = 0,
    double MetalResistance = 0,
    double WaterResistance = 0)
{
    public double DamageBonus(CardElement element) => element switch
    {
        CardElement.Fire => FireDamageBonus,
        CardElement.Wood => WoodDamageBonus,
        CardElement.Earth => EarthDamageBonus,
        CardElement.Metal => MetalDamageBonus,
        CardElement.Water => WaterDamageBonus,
        _ => 0
    };

    public double Resistance(CardElement element) => element switch
    {
        CardElement.Fire => FireResistance,
        CardElement.Wood => WoodResistance,
        CardElement.Earth => EarthResistance,
        CardElement.Metal => MetalResistance,
        CardElement.Water => WaterResistance,
        _ => 0
    };
}

public sealed record CombatEquipmentProfile(
    ElementalEquipmentModifiers Elements,
    double PiercingBonus = 0,
    double BulwarkDamageReduction = 0,
    double BulwarkShieldBonus = 0,
    double VitalityHealBonus = 0,
    double VitalityOvercapBonus = 0,
    double DrawIntervalModifier = 0,
    double ForcedEscapeBonus = 0,
    bool HasRapidDraw = false)
{
    public static CombatEquipmentProfile Empty { get; } = new(new ElementalEquipmentModifiers());

    public double DamageBonus(CardElement element) => Elements.DamageBonus(element);
    public double Resistance(CardElement element) => Elements.Resistance(element);
}

public static class EquipmentCombatRules
{
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];

    public static CombatEquipmentProfile Calculate(IReadOnlyList<CombatEquipmentItem>? items)
    {
        if (items is null || items.Count == 0)
        {
            return CombatEquipmentProfile.Empty;
        }
        if (items.Count > 5 || items.Select(item => item.ItemId).Distinct().Count() != items.Count ||
            items.Select(item => item.Slot).Distinct(StringComparer.Ordinal).Count() != items.Count ||
            items.Count(item => item.Quality is "Orange" or "Red") > 1)
        {
            throw new DomainValidationException("Equipped armor must contain unique slots and at most one Orange or Red item.");
        }

        var damage = new Dictionary<CardElement, double>();
        var resistance = new Dictionary<CardElement, double>();
        var drawModifier = 0d;
        var forcedEscape = 0d;
        var hasRapidDraw = false;
        foreach (var item in items)
        {
            Validate(item);
            var quality = Quality(item.Quality);
            Add(damage, item.Element, quality.Damage + item.Level * quality.DamagePerLevel);
            Add(resistance, item.Element, quality.Resistance + item.Level * quality.ResistancePerLevel);
            if (string.Equals(item.SecondaryTrait, "DrawInterval", StringComparison.Ordinal) || item.Quality == "Red")
            {
                drawModifier += quality.DrawInterval + item.Level * quality.DrawIntervalPerLevel;
            }
            if (string.Equals(item.SecondaryTrait, "ForcedEscape", StringComparison.Ordinal))
            {
                forcedEscape += quality.ForcedEscape;
            }
            if (string.Equals(item.UniqueAffix, "RapidDraw", StringComparison.Ordinal))
            {
                drawModifier -= 0.25;
                hasRapidDraw = true;
            }
            if (string.Equals(item.UniqueAffix, "Inferno", StringComparison.Ordinal))
            {
                Add(damage, item.UniqueElement ?? item.Element, 0.35);
            }
        }

        var piercing = Affix(items, "Piercing", value => value.Piercing, value => value.PiercingCap);
        var bulwarkReduction = Affix(items, "Bulwark", value => value.BulwarkReduction, value => value.BulwarkReductionCap);
        var bulwarkShield = Affix(items, "Bulwark", value => value.BulwarkShield, value => value.BulwarkShieldCap);
        var vitalityHeal = Affix(items, "Vitality", value => value.VitalityHeal, _ => 0.50);
        var vitalityOvercap = Affix(items, "Vitality", value => value.VitalityOvercap, _ => 0.40);
        return new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(
                Get(damage, CardElement.Fire), Get(damage, CardElement.Wood), Get(damage, CardElement.Earth),
                Get(damage, CardElement.Metal), Get(damage, CardElement.Water),
                Math.Min(0.60, Get(resistance, CardElement.Fire)), Math.Min(0.60, Get(resistance, CardElement.Wood)),
                Math.Min(0.60, Get(resistance, CardElement.Earth)), Math.Min(0.60, Get(resistance, CardElement.Metal)),
                Math.Min(0.60, Get(resistance, CardElement.Water))),
            piercing,
            bulwarkReduction,
            bulwarkShield,
            vitalityHeal,
            vitalityOvercap,
            drawModifier,
            forcedEscape,
            hasRapidDraw);
    }

    private static double Affix(
        IReadOnlyList<CombatEquipmentItem> items,
        string affix,
        Func<EquipmentQualityConfig, double> contribution,
        Func<EquipmentQualityConfig, double> cap)
    {
        var matching = items.Where(item => string.Equals(item.EffectAffix, affix, StringComparison.Ordinal)).ToArray();
        var hasOrangeOrRed = matching.Any(item => item.Quality is "Orange" or "Red");
        if (matching.Length < (hasOrangeOrRed ? 2 : 3))
        {
            return 0;
        }
        var multiplier = matching.Length switch { 2 or 3 => 1.35, 4 => 1.55, _ => 1.80 };
        var sum = matching.Sum(item =>
        {
            var values = Quality(item.Quality);
            return contribution(values) + item.Level * values.AffixPerLevel;
        });
        var strongest = matching.Select(item => Quality(item.Quality)).OrderByDescending(value => value.Rank).First();
        return Math.Min(cap(strongest), Math.Floor(sum * 100 * multiplier) / 100);
    }

    private static void Validate(CombatEquipmentItem item)
    {
        if (item.ItemId == Guid.Empty || !Slots.Contains(item.Slot, StringComparer.Ordinal) || item.Level is < 0 or > 5 ||
            item.Element == CardElement.None || !Enum.IsDefined(item.Element))
        {
            throw new DomainValidationException("Equipment combat attributes are invalid.");
        }
        _ = Quality(item.Quality);
        if (item.EffectAffix is not (null or "Piercing" or "Bulwark" or "Vitality") ||
            item.SecondaryTrait is not (null or "DrawInterval" or "ForcedEscape") ||
            item.SecondaryTrait == "ForcedEscape" && item.Slot != "Feet" ||
            item.Quality is "White" or "Green" or "Blue" && item.EffectAffix is not null)
        {
            throw new DomainValidationException("Equipment affixes are invalid for its slot or quality.");
        }
    }

    private static EquipmentQualityConfig Quality(string quality) =>
        GameConfigCatalog.Current.EquipmentQuality(quality);

    private static void Add(Dictionary<CardElement, double> values, CardElement element, double value) =>
        values[element] = Get(values, element) + value;

    private static double Get(Dictionary<CardElement, double> values, CardElement element) =>
        values.TryGetValue(element, out var value) ? value : 0;

}
