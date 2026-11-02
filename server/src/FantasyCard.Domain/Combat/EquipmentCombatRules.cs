using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using System.Text.Json.Serialization;

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
    bool HasRapidDraw = false,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? StatsVersion = null,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] double? MinimumDrawInterval = null,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] double? MaximumDrawInterval = null,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)] int ChainDrawBasisPoints = 0,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)] int OpeningDrawCount = 0,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)] double GoldenCicadaBonus = 0,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] ElementalEquipmentModifiers? RawElements = null)
{
    public static CombatEquipmentProfile Empty { get; } = new(new ElementalEquipmentModifiers());

    public double DamageBonus(CardElement element) => Elements.DamageBonus(element);
    public double Resistance(CardElement element) => Elements.Resistance(element);
}

public static class EquipmentCombatRules
{
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];

    public static CombatEquipmentProfile Calculate(IReadOnlyList<CombatEquipmentItem>? items, GameConfigCatalog? configuration = null,string? statsVersion = null)
    {
        var catalog = configuration ?? GameConfigCatalog.Current;
        var policy=statsVersion is null ? null : catalog.ResolveSeasonEquipment(statsVersion);
        if (items is null || items.Count == 0)
        {
            return policy is null?CombatEquipmentProfile.Empty:CombatEquipmentProfile.Empty with
                {StatsVersion=policy.StatsVersion,MinimumDrawInterval=policy.DrawFloorSeconds,MaximumDrawInterval=policy.DrawCeilingSeconds,RawElements=new()};
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
        var chainDraw=0;var openingDraw=0;var goldenCicada=0d;
        foreach (var item in items)
        {
            Validate(item, catalog);
            if(policy is not null && item.UniqueAffix is not null && (item.Quality!="Red" ||
                item.UniqueAffix is not ("Inferno" or "RapidDraw" or "ChainDraw" or "Scavenge" or "GoldenCicada") ||
                item.UniqueAffix=="GoldenCicada" && item.Slot!="Feet" ||
                item.UniqueAffix=="Inferno" && item.UniqueElement is { } unique && unique!=item.Element))
                throw new DomainValidationException("The seasonal unique affix is not valid for its item or main element.");
            var quality = catalog.EquipmentQuality(item.Quality,statsVersion);
            Add(damage, item.Element, quality.Damage + item.Level * quality.DamagePerLevel);
            Add(resistance, item.Element, quality.Resistance + item.Level * quality.ResistancePerLevel);
            if (string.Equals(item.SecondaryTrait, "DrawInterval", StringComparison.Ordinal) || policy is null && item.Quality == "Red")
            {
                drawModifier += quality.DrawInterval + item.Level * quality.DrawIntervalPerLevel;
            }
            if (string.Equals(item.SecondaryTrait, "ForcedEscape", StringComparison.Ordinal))
            {
                forcedEscape += quality.ForcedEscape;
            }
            if (string.Equals(item.UniqueAffix, "RapidDraw", StringComparison.Ordinal))
            {
                drawModifier -= policy?.RapidDrawReduction ?? 0.25;
                hasRapidDraw = true;
            }
            if (string.Equals(item.UniqueAffix, "Inferno", StringComparison.Ordinal))
            {
                Add(damage, policy is null?item.UniqueElement??item.Element:item.Element, policy?.InfernoBonus??0.35);
            }
            if(policy is not null && item.UniqueAffix=="ChainDraw")chainDraw=policy.ChainDrawBasisPoints;
            if(policy is not null && item.UniqueAffix=="Scavenge")openingDraw=policy.OpeningDrawCount;
            if(policy is not null && item.UniqueAffix=="GoldenCicada")goldenCicada=policy.GoldenCicadaBonus;
        }

        var piercing = Affix(items, "Piercing", value => value.Piercing, value => value.PiercingCap, catalog,statsVersion);
        var bulwarkReduction = Affix(items, "Bulwark", value => value.BulwarkReduction, value => value.BulwarkReductionCap, catalog,statsVersion);
        var bulwarkShield = Affix(items, "Bulwark", value => value.BulwarkShield, value => value.BulwarkShieldCap, catalog,statsVersion);
        var vitalityHeal = Affix(items, "Vitality", value => value.VitalityHeal, _ => 0.50, catalog,statsVersion);
        var vitalityOvercap = Affix(items, "Vitality", value => value.VitalityOvercap, _ => 0.40, catalog,statsVersion);
        var cap=policy?.ResistanceCap??.6;
        var raw=new ElementalEquipmentModifiers(Get(damage,CardElement.Fire),Get(damage,CardElement.Wood),Get(damage,CardElement.Earth),Get(damage,CardElement.Metal),Get(damage,CardElement.Water),
            Get(resistance,CardElement.Fire),Get(resistance,CardElement.Wood),Get(resistance,CardElement.Earth),Get(resistance,CardElement.Metal),Get(resistance,CardElement.Water));
        return new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(
                Get(damage, CardElement.Fire), Get(damage, CardElement.Wood), Get(damage, CardElement.Earth),
                Get(damage, CardElement.Metal), Get(damage, CardElement.Water),
                Math.Min(cap, Get(resistance, CardElement.Fire)), Math.Min(cap, Get(resistance, CardElement.Wood)),
                Math.Min(cap, Get(resistance, CardElement.Earth)), Math.Min(cap, Get(resistance, CardElement.Metal)),
                Math.Min(cap, Get(resistance, CardElement.Water))),
            piercing,
            bulwarkReduction,
            bulwarkShield,
            vitalityHeal,
            vitalityOvercap,
            drawModifier,
            forcedEscape,
            hasRapidDraw,policy?.StatsVersion,policy is null?null:hasRapidDraw?policy.RapidDrawFloorSeconds:policy.DrawFloorSeconds,
            policy?.DrawCeilingSeconds,chainDraw,openingDraw,goldenCicada,policy is null?null:raw);
    }

    private static double Affix(
        IReadOnlyList<CombatEquipmentItem> items,
        string affix,
        Func<EquipmentQualityConfig, double> contribution,
        Func<EquipmentQualityConfig, double> cap,
        GameConfigCatalog catalog,string? statsVersion)
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
            var values = catalog.EquipmentQuality(item.Quality,statsVersion);
            return contribution(values) + item.Level * values.AffixPerLevel;
        });
        var strongest = matching.Select(item => catalog.EquipmentQuality(item.Quality,statsVersion)).OrderByDescending(value => value.Rank).First();
        return Math.Min(cap(strongest), Math.Floor(sum * 100 * multiplier) / 100);
    }

    private static void Validate(CombatEquipmentItem item, GameConfigCatalog catalog)
    {
        if (item.ItemId == Guid.Empty || !Slots.Contains(item.Slot, StringComparer.Ordinal) || item.Level is < 0 or > 5 ||
            item.Element == CardElement.None || !Enum.IsDefined(item.Element))
        {
            throw new DomainValidationException("Equipment combat attributes are invalid.");
        }
        _ = catalog.EquipmentQuality(item.Quality);
        if (item.EffectAffix is not (null or "Piercing" or "Bulwark" or "Vitality") ||
            item.SecondaryTrait is not (null or "DrawInterval" or "ForcedEscape") ||
            item.SecondaryTrait == "ForcedEscape" && item.Slot != "Feet" ||
            item.Quality is "White" or "Green" or "Blue" && item.EffectAffix is not null)
        {
            throw new DomainValidationException("Equipment affixes are invalid for its slot or quality.");
        }
    }

    private static void Add(Dictionary<CardElement, double> values, CardElement element, double value) =>
        values[element] = Get(values, element) + value;

    private static double Get(Dictionary<CardElement, double> values, CardElement element) =>
        values.TryGetValue(element, out var value) ? value : 0;

}
