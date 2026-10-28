using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class EquipmentCombatRulesTests
{
    [Fact]
    public void Two_green_fire_items_add_main_attributes_without_a_set_multiplier()
    {
        var profile = EquipmentCombatRules.Calculate([
            Item("Head", "Green", CardElement.Fire, secondary: "DrawInterval"),
            Item("Feet", "Green", CardElement.Fire, secondary: "ForcedEscape")
        ]);

        Assert.Equal(.14, profile.DamageBonus(CardElement.Fire), 6);
        Assert.Equal(.08, profile.Resistance(CardElement.Fire), 6);
        Assert.Equal(-.05, profile.DrawIntervalModifier, 6);
        Assert.Equal(.03, profile.ForcedEscapeBonus, 6);
        Assert.Equal(0, profile.PiercingBonus);
    }

    [Fact]
    public void Enhancement_uses_quality_specific_per_level_values()
    {
        var profile = EquipmentCombatRules.Calculate([
            Item("Head", "Orange", CardElement.Fire, level: 5, secondary: "DrawInterval")
        ]);

        Assert.Equal(.37, profile.DamageBonus(CardElement.Fire), 6);
        Assert.Equal(.205, profile.Resistance(CardElement.Fire), 6);
        Assert.Equal(-.305, profile.DrawIntervalModifier, 6);
    }

    [Fact]
    public void Affix_thresholds_multipliers_and_caps_match_the_gdd()
    {
        var threePurple = EquipmentCombatRules.Calculate([
            Item("Head", "Purple", CardElement.Fire, affix: "Piercing"),
            Item("Chest", "Purple", CardElement.Fire, affix: "Piercing"),
            Item("Hands", "Purple", CardElement.Fire, affix: "Piercing")
        ]);
        var orangeAndPurple = EquipmentCombatRules.Calculate([
            Item("Head", "Orange", CardElement.Fire, affix: "Piercing"),
            Item("Chest", "Purple", CardElement.Fire, affix: "Piercing")
        ]);
        var cappedRed = EquipmentCombatRules.Calculate([
            Item("Head", "Red", CardElement.Fire, affix: "Piercing"),
            Item("Chest", "Purple", CardElement.Fire, affix: "Piercing"),
            Item("Hands", "Purple", CardElement.Fire, affix: "Piercing"),
            Item("Legs", "Purple", CardElement.Fire, affix: "Piercing"),
            Item("Feet", "Purple", CardElement.Fire, affix: "Piercing")
        ]);

        Assert.Equal(.24, threePurple.PiercingBonus, 6);
        Assert.Equal(.27, orangeAndPurple.PiercingBonus, 6);
        Assert.Equal(.50, cappedRed.PiercingBonus, 6);
    }

    [Fact]
    public void More_than_one_orange_or_red_item_is_rejected()
    {
        Assert.Throws<DomainValidationException>(() => EquipmentCombatRules.Calculate([
            Item("Head", "Orange", CardElement.Fire),
            Item("Chest", "Red", CardElement.Water)
        ]));
    }

    [Fact]
    public void Combat_formula_applies_attack_bonus_target_resistance_then_piercing()
    {
        var profile = new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(FireDamageBonus: .14),
            PiercingBonus: .24);
        var attacker = State(HeroClass.Mage, profile);
        CombatCardDefinition[] cards = [
            Card("slash", 8),
            Card("spark", 3),
            Card("burst", 12)
        ];

        var versusMetalGuard = CombatResolver.Resolve(cards, attacker, _ => -.30);
        var versusPlayer = CombatResolver.Resolve(cards, attacker, _ => .08);

        // User reaffirmed the 54cab7f rules on 2026-09-28: first core card is
        // baseline, later core cards add 20%, and elemental cards floor individually.
        Assert.Equal(1.4, versusMetalGuard.ResonanceMultiplier, 6);
        Assert.Equal(3, versusMetalGuard.CoreCount);
        Assert.Equal(46, versusMetalGuard.DamageSegments!.Single(segment => segment.Kind == "Fire").Amount); // 16 + 6 + 24
        Assert.Equal(3, versusMetalGuard.DamageSegments!.Single(segment => segment.Kind == "Direct").Amount); // 1 + 0 + 2
        Assert.Equal(49, versusMetalGuard.Damage);
        Assert.Equal(32, versusPlayer.DamageSegments!.Single(segment => segment.Kind == "Fire").Amount); // 11 + 4 + 17
        Assert.Equal(3, versusPlayer.DamageSegments!.Single(segment => segment.Kind == "Direct").Amount);
        Assert.Equal(35, versusPlayer.Damage);
    }

    [Theory]
    [InlineData(.14, -.30, 0, 46, 0)]
    [InlineData(.14, .15, 0, 30, 0)]
    [InlineData(.14, .08, 0, 32, 0)]
    [InlineData(.14, .35, 0, 23, 0)]
    [InlineData(.75, .49, .40, 26, 8)]
    [InlineData(.82, .45, .45, 31, 9)]
    [InlineData(.75, .54, .40, 25, 8)]
    [InlineData(.92, .45, .50, 32, 11)]
    [InlineData(1.27, .45, .50, 38, 11)]
    [InlineData(.75, .60, .40, 20, 8)]
    [InlineData(1.12, .45, .50, 36, 11)]
    [InlineData(1.47, .45, .50, 42, 11)]
    [InlineData(.44, -.30, 0, 58, 0)]
    [InlineData(.44, .08, 0, 41, 0)]
    public void Approved_current_gdd_examples_preserve_separate_elemental_and_direct_segments(
        double bonus, double resistance, double piercing, int elemental, int direct)
    {
        var state = State(HeroClass.Mage, new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(FireDamageBonus: bonus), PiercingBonus: piercing));
        var result = CombatResolver.Resolve([Card("slash", 8), Card("spark", 3), Card("burst", 12)], state, _ => resistance);
        Assert.Equal(1.4, result.ResonanceMultiplier, 6);
        Assert.Equal(elemental, result.DamageSegments!.Where(segment => segment.Kind == "Fire").Sum(segment => segment.Amount));
        Assert.Equal(direct, result.DamageSegments!.Where(segment => segment.Kind == "Direct").Sum(segment => segment.Amount));
        Assert.Equal(elemental + direct, result.Damage);
    }

    [Fact]
    public void Bulwark_reduction_is_guardian_only_and_vitality_raises_heal_cap()
    {
        var equipment = new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(),
            BulwarkDamageReduction: .12,
            BulwarkShieldBonus: .24,
            VitalityHealBonus: .24,
            VitalityOvercapBonus: .16);
        var guardian = State(HeroClass.Guardian, equipment);
        var mage = State(HeroClass.Mage, equipment);

        Assert.Equal(44, guardian.ResolveIncomingDamage(51));
        Assert.Equal(51, mage.ResolveIncomingDamage(51));
        Assert.Equal(17, guardian.ResolveShield(9));
        Assert.Equal(81, mage.EffectiveMaximumHp);
        mage.TakeDamage(1);
        Assert.Equal(7, mage.ResolveHeal(6));
        Assert.Equal(7, mage.Heal(mage.ResolveHeal(6)));
        Assert.Equal(76, mage.Hp);
        mage.TakeDamage(6);
        Assert.Equal(7, mage.Heal(mage.ResolveRecovery(6)));
        Assert.Equal(77, mage.Hp);
    }

    [Fact]
    public void Draw_interval_uses_default_floor_unless_rapid_draw_is_equipped()
    {
        var ordinary = State(HeroClass.Mage, new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(), DrawIntervalModifier: -.70));
        var rapid = State(HeroClass.Mage, new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(), DrawIntervalModifier: -.70, HasRapidDraw: true));

        ordinary.Advance(TimeSpan.FromSeconds(1.7), drawEnabled: true);
        rapid.Advance(TimeSpan.FromSeconds(1.5), drawEnabled: true);

        Assert.Equal(3, ordinary.Deck.Hand.Count);
        Assert.Equal(4, rapid.Deck.Hand.Count);
        ordinary.Advance(TimeSpan.FromSeconds(.1), drawEnabled: true);
        Assert.Equal(4, ordinary.Deck.Hand.Count);
    }

    private static PlayerCombatState State(HeroClass heroClass, CombatEquipmentProfile profile) =>
        new(heroClass, Enumerable.Range(1, 20).Select(index => $"card-{index}").ToArray(), new Random(17), equipment: profile);

    private static CombatCardDefinition Card(string id, int damage) =>
        new(id, new CombatCardEffect(ElementalDamage: damage, Element: CardElement.Fire));

    private static CombatEquipmentItem Item(
        string slot,
        string quality,
        CardElement element,
        int level = 0,
        string? affix = null,
        string? secondary = null) =>
        new(Guid.NewGuid(), slot, quality, level, element, affix, secondary);
}
