using FantasyCard.Domain.Players;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Domain.Combat;

public sealed class CombatCardCatalog
{
    private readonly Dictionary<string, CombatCardDefinition> _definitions;

    public CombatCardCatalog(IEnumerable<CombatCardDefinition> definitions)
    {
        ArgumentNullException.ThrowIfNull(definitions);
        _definitions = definitions.ToDictionary(definition => definition.CardId, StringComparer.Ordinal);
    }

    public CombatCardDefinition Get(string cardId) =>
        _definitions.TryGetValue(cardId, out var definition)
            ? definition
            : throw new DomainValidationException($"Combat card '{cardId}' is not present in the active config.");

    public static CombatCardCatalog CreatePrototype()
    {
        var cards = GameConfigCatalog.Current.Cards
            .Select(card => new CombatCardDefinition(card.CardId, card.Effect))
            .ToList();
        cards.AddRange(new List<CombatCardDefinition>
        {
            Elemental("common-01", CardElement.Fire, 8),
            Elemental("common-02", CardElement.Fire, 3),
            Elemental("common-03", CardElement.Fire, 6),
            Elemental("common-04", CardElement.Wood, 7),
            Elemental("common-05", CardElement.Wood, 6),
            Elemental("common-06", CardElement.Water, 6),
            Elemental("common-07", CardElement.Metal, 7),
            Elemental("common-08", CardElement.Metal, 6),
            Elemental("common-09", CardElement.Earth, 6),
            Elemental("common-10", CardElement.Earth, 6),
            Direct("common-11", 6),
            Direct("common-12", 8),
            Direct("common-13", 6),
            Direct("common-14", 7),
            Effect("common-15", new CombatCardEffect(Heal: 6)),
            Effect("common-16", new CombatCardEffect(DrawCharge: 0.4)),
            Effect("common-17", new CombatCardEffect(Shield: 5)),
            Effect("common-18", new CombatCardEffect(DrawSpeedModifier: -0.15, DrawSpeedSeconds: 8)),
            Effect("common-19", new CombatCardEffect(StunSeconds: 0.8)),
            Effect("common-20", new CombatCardEffect(DrawBlockSeconds: 3)),
            Elemental("common-21", CardElement.Fire, 10),
            Effect("common-22", new CombatCardEffect(ImmediateDraw: 1)),
            Effect("common-23", new CombatCardEffect(ElementalDamage: 4, Element: CardElement.Water, Heal: 6)),
            Effect("common-24", new CombatCardEffect(Shield: 8)),
            Effect("common-25", new CombatCardEffect(DrawSpeedModifier: -0.25, DrawSpeedSeconds: 10)),
            Effect("common-26", new CombatCardEffect(StunSeconds: 1.2)),
            Effect("common-27", new CombatCardEffect(DrawBlockSeconds: 4)),
            Effect("common-28", new CombatCardEffect(Heal: 16)),
            Effect("common-29", new CombatCardEffect(DrawSpeedModifier: -0.35, DrawSpeedSeconds: 12)),
            Elemental("common-30", CardElement.Metal, 13)
        });
        cards.AddRange(ClassCards("priest", HeroClass.Priest));
        cards.AddRange(ClassCards("mage", HeroClass.Mage));
        cards.AddRange(ClassCards("guardian", HeroClass.Guardian));
        return new CombatCardCatalog(cards);
    }

    private static IEnumerable<CombatCardDefinition> ClassCards(string prefix, HeroClass heroClass) =>
        heroClass switch
        {
            HeroClass.Priest =>
            [
                Effect($"{prefix}-01", new CombatCardEffect(Heal: 7)),
                Effect($"{prefix}-02", new CombatCardEffect(Heal: 6)),
                Elemental($"{prefix}-03", CardElement.Water, 8),
                Direct($"{prefix}-04", 8),
                Effect($"{prefix}-05", new CombatCardEffect(Heal: 4, Shield: 5)),
                Effect($"{prefix}-06", new CombatCardEffect(StunSeconds: 1.2)),
                Effect($"{prefix}-07", new CombatCardEffect(DrawSpeedModifier: -0.15, DrawSpeedSeconds: 8))
            ],
            HeroClass.Mage =>
            [
                Elemental($"{prefix}-01", CardElement.Fire, 8),
                Elemental($"{prefix}-02", CardElement.Fire, 8),
                Elemental($"{prefix}-03", CardElement.Fire, 6),
                Elemental($"{prefix}-04", CardElement.Water, 8),
                Elemental($"{prefix}-05", CardElement.Earth, 7),
                Direct($"{prefix}-06", 8),
                Effect($"{prefix}-07", new CombatCardEffect(DrawSpeedModifier: -0.15, DrawSpeedSeconds: 8))
            ],
            HeroClass.Guardian =>
            [
                Effect($"{prefix}-01", new CombatCardEffect(Shield: 9)),
                Effect($"{prefix}-02", new CombatCardEffect(Shield: 6)),
                Effect($"{prefix}-03", new CombatCardEffect(Shield: 7)),
                Effect($"{prefix}-04", new CombatCardEffect(DirectDamage: 7, Shield: 4)),
                Direct($"{prefix}-05", 8),
                Effect($"{prefix}-06", new CombatCardEffect(StunSeconds: 1, Shield: 4)),
                Effect($"{prefix}-07", new CombatCardEffect(HealthCost: 4, Heal: 8))
            ],
            _ => throw new ArgumentOutOfRangeException(nameof(heroClass))
        };

    private static CombatCardDefinition Elemental(string id, CardElement element, int value) =>
        Effect(id, new CombatCardEffect(ElementalDamage: value, Element: element));

    private static CombatCardDefinition Direct(string id, int value) =>
        Effect(id, new CombatCardEffect(DirectDamage: value));

    private static CombatCardDefinition Effect(string id, CombatCardEffect effect) =>
        new(id, effect);
}
