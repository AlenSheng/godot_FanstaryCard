using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

/// <summary>
/// Locks the v0.70/current-server numerical contract. These tests intentionally
/// describe the existing CombatResolver behavior; they do not propose a new formula.
/// </summary>
public sealed class CurrentNumericalBaselineTests
{
    [Fact]
    public void A_three_fire_is_46()
    {
        var result = Resolve([Fire(8), Fire(3), Fire(12)],
            equipment: FireEquipment(.14), resistance: _ => -.30);
        AssertBaseline(result, 46, 0, CardElement.Fire, 3, 1.4, 0, 0);
        AssertSegments(result, ("Fire", 46));
    }

    [Fact]
    public void A_fuel_four_fire_is_72()
    {
        var result = Resolve([Fire(8), Fire(3), Fire(6), Fuel(12)],
            equipment: FireEquipment(.14), resistance: _ => -.30);
        AssertBaseline(result, 72, 0, CardElement.Fire, 4, 1.6, 0, 0);
    }

    [Fact]
    public void A_fuel_five_fire_is_113()
    {
        var result = Resolve([Fire(8), Fire(3), Fire(6), Fire(10), Fuel(12)],
            equipment: FireEquipment(.14), resistance: _ => -.30);
        AssertBaseline(result, 113, 0, CardElement.Fire, 5, 1.8, 0, 0);
    }

    [Fact]
    public void Element_damage_floors_each_card_before_sum()
    {
        var result = Resolve([Fire(3), Fire(3), Fire(3)], equipment: FireEquipment(.14));
        AssertBaseline(result, 12, 0, CardElement.Fire, 3, 1.4, 0, 0);
        AssertSegments(result, ("Fire", 12));
    }

    [Fact]
    public void First_element_is_core_even_when_later_element_has_more_cards()
    {
        var result = Resolve([Fire(8), Element(CardElement.Water, 7), Element(CardElement.Water, 7)],
            equipment: FireEquipment(.14), resistance: _ => -.30);
        AssertBaseline(result, 23, 6, CardElement.Fire, 1, 1.0, 2, .4);
        AssertSegments(result, ("Fire", 11), ("Water", 12));
    }

    [Fact]
    public void Selection_order_fire_first_uses_fire_shared_multiplier()
    {
        var result = Resolve([Fire(8), Element(CardElement.Water, 7)],
            equipment: FireEquipment(.14),
            resistance: element => element == CardElement.Fire ? -.30 : .50);
        AssertBaseline(result, 19, 3, CardElement.Fire, 1, 1.0, 1, .2);
        AssertSegments(result, ("Fire", 11), ("Water", 8));
    }

    [Fact]
    public void Selection_order_water_first_uses_water_shared_multiplier()
    {
        var result = Resolve([Element(CardElement.Water, 7), Fire(8)],
            equipment: FireEquipment(.14),
            resistance: element => element == CardElement.Fire ? -.30 : .50);
        AssertBaseline(result, 6, 2, CardElement.Water, 1, 1.0, 1, .2);
        AssertSegments(result, ("Water", 3), ("Fire", 3));
    }

    [Fact]
    public void Tuning_card_can_establish_core_and_counts_toward_r()
    {
        var result = Resolve([Tuning(CardElement.Fire, 4), Fire(8)]);
        AssertBaseline(result, 13, 0, CardElement.Fire, 2, 1.2, 0, 0);
    }

    [Fact]
    public void Non_core_tuning_card_does_not_create_conflict_pair()
    {
        var result = Resolve([Fire(8), Tuning(CardElement.Water, 5)]);
        AssertBaseline(result, 13, 0, CardElement.Fire, 1, 1.0, 0, 0);
        AssertSegments(result, ("Fire", 8), ("Water", 5));
    }

    [Fact]
    public void Tuning_card_is_excluded_from_conflict_recovery_base()
    {
        var result = Resolve([Fire(8), Tuning(CardElement.Fire, 4), Element(CardElement.Water, 7)]);
        AssertBaseline(result, 17, 2, CardElement.Fire, 2, 1.0, 1, .2);
    }

    [Fact]
    public void Unrelated_third_element_keeps_damage_and_does_not_add_p()
    {
        var result = Resolve([Fire(8), Element(CardElement.Wood, 7)],
            equipment: FireEquipment(.14), resistance: _ => -.30);
        AssertBaseline(result, 21, 0, CardElement.Fire, 1, 1.0, 0, 0);
        AssertSegments(result, ("Fire", 11), ("Wood", 10));
    }

    [Fact]
    public void Multiple_resonance_bonus_cards_still_contribute_only_one_virtual_stack()
    {
        var bonus = new CombatCardDefinition("bonus", new(ResonanceBonus: 1));
        var result = Resolve([Fire(10), Fire(10), bonus, bonus]);
        AssertBaseline(result, 28, 0, CardElement.Fire, 2, 1.4, 0, 0);
    }

    [Fact]
    public void Boss_dual_element_without_core_uses_each_elements_own_multiplier()
    {
        var result = Resolve([Boss()],
            equipment: new(new(FireDamageBonus: .14)),
            resistance: element => element == CardElement.Fire ? -.30 : .60);
        AssertBaseline(result, 14, 0, null, 0, 1.0, 0, 0);
        AssertSegments(result, ("Fire", 11), ("Metal", 3));
    }

    [Fact]
    public void Boss_dual_element_with_core_uses_core_shared_multiplier_for_both_segments()
    {
        var result = Resolve([Element(CardElement.Water, 7), Boss()],
            equipment: new(new(WaterDamageBonus: .20)),
            resistance: element => element == CardElement.Water ? .50 : 0);
        AssertBaseline(result, 12, 0, CardElement.Water, 1, 1.0, 0, 0);
        AssertSegments(result, ("Water", 4), ("Fire", 4), ("Metal", 4));
    }

    [Fact]
    public void Direct_damage_has_no_core_and_ignores_element_resistance()
    {
        var result = Resolve([Direct(9)], resistance: _ => .99);
        AssertBaseline(result, 9, 0, null, 0, 1.0, 0, 0);
        AssertSegments(result, ("Direct", 9));
    }

    [Fact]
    public void Conflict_cancellation_caps_at_eighty_percent()
    {
        var result = Resolve([Fire(8), Element(CardElement.Water, 1), Element(CardElement.Water, 1),
            Element(CardElement.Water, 1), Element(CardElement.Water, 1)]);
        AssertBaseline(result, 8, 11, CardElement.Fire, 1, 1.0, 4, .8);
        AssertSegments(result, ("Fire", 8));
    }

    [Fact]
    public void Conflict_cancel_bonus_and_heal_coefficient_use_maximum_selected_values()
    {
        var modifier = new CombatCardDefinition("modifier", new(ConflictCancelBonus: .15, ConflictHealCoefficient: .70));
        var result = Resolve([Fire(8), Element(CardElement.Water, 7), modifier]);
        AssertBaseline(result, 12, 3, CardElement.Fire, 1, 1.0, 1, .35);
    }

    [Fact]
    public void Ordinary_heal_receives_conflict_heal_multiplier_then_adds_conflict_recovery()
    {
        var result = Resolve([Fire(8), Element(CardElement.Water, 7), new("heal", new(Heal: 8))]);
        AssertBaseline(result, 13, 12, CardElement.Fire, 1, 1.0, 1, .2);
    }

    [Fact]
    public void Priest_card_heal_gets_passive_and_weapon_but_conflict_recovery_does_not()
    {
        var state = State(HeroClass.Priest, new(new(), VitalityHealBonus: .20));
        state.TakeDamage(40);
        var result = CombatResolver.Resolve([Fire(8), Element(CardElement.Water, 7), new("heal", new(Heal: 8))], state);
        AssertBaseline(result, 13, 18, CardElement.Fire, 1, 1.0, 1, .2);
    }

    [Fact]
    public void Class_reveal_applies_before_resonance_and_per_card_floor()
    {
        var result = Resolve([Fire(8), Fire(3), Fire(12), new("reveal", new(IsClassReveal: true))]);
        AssertBaseline(result, 39, 0, CardElement.Fire, 3, 1.4, 0, 0);
        AssertSegments(result, ("Fire", 39));
    }

    [Fact]
    public void Class_reveal_applies_to_matching_secondary_boss_segment()
    {
        var result = Resolve([Boss(), new("reveal", new(IsClassReveal: true))]);
        AssertBaseline(result, 18, 0, null, 0, 1.0, 0, 0);
        AssertSegments(result, ("Fire", 10), ("Metal", 8));
    }

    [Fact]
    public void Piercing_reads_each_cards_processed_damage_base_and_adds_to_direct_segment()
    {
        var result = Resolve([Fire(8), Direct(7)], equipment: new(new(), PiercingBonus: .25));
        AssertBaseline(result, 18, 0, CardElement.Fire, 1, 1.0, 0, 0);
        AssertSegments(result, ("Fire", 8), ("Direct", 10));
    }

    [Fact]
    public void Negative_resistance_increases_element_damage()
    {
        var result = Resolve([Fire(10)], resistance: _ => -.30);
        AssertBaseline(result, 13, 0, CardElement.Fire, 1, 1.0, 0, 0);
    }

    [Fact]
    public void Non_core_unrelated_element_uses_core_equipment_and_resistance()
    {
        var result = Resolve([Fire(8), Element(CardElement.Wood, 10)],
            equipment: new(new(FireDamageBonus: .50)),
            resistance: element => element == CardElement.Fire ? .20 : .90);
        AssertBaseline(result, 21, 0, CardElement.Fire, 1, 1.0, 0, 0);
        AssertSegments(result, ("Fire", 9), ("Wood", 12));
    }

    [Fact]
    public void Dual_element_segments_share_existing_core_multiplier()
    {
        var result = Resolve([Element(CardElement.Water, 10), Boss()],
            equipment: new(new(WaterDamageBonus: .50)),
            resistance: element => element == CardElement.Water ? .20 : 0);
        AssertBaseline(result, 30, 0, CardElement.Water, 1, 1.0, 0, 0);
        AssertSegments(result, ("Water", 12), ("Fire", 9), ("Metal", 9));
    }

    [Fact]
    public void Prototype_catalog_real_cards_follow_same_current_baseline()
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var result = Resolve([catalog.Get("common-01"), catalog.Get("common-02"), catalog.Get("common-03")],
            equipment: FireEquipment(.14), resistance: _ => -.30);

        AssertBaseline(result, 34, 0, CardElement.Fire, 3, 1.4, 0, 0);
        AssertSegments(result, ("Fire", 34));
    }

    private static CardResolutionDraft Resolve(
        IReadOnlyList<CombatCardDefinition> cards,
        CombatEquipmentProfile? equipment = null,
        Func<CardElement, double>? resistance = null) =>
        CombatResolver.Resolve(cards, State(equipment: equipment), resistance);

    private static PlayerCombatState State(
        HeroClass heroClass = HeroClass.Mage,
        CombatEquipmentProfile? equipment = null) =>
        new(heroClass, Enumerable.Repeat("common-01", 20).ToArray(), new Random(31), equipment: equipment);

    private static CombatEquipmentProfile FireEquipment(double damageBonus) =>
        new(new(FireDamageBonus: damageBonus));

    private static CombatCardDefinition Fire(int value) => Element(CardElement.Fire, value);

    private static CombatCardDefinition Element(CardElement element, int value) =>
        new($"damage-{element}-{value}", new(ElementalDamage: value, Element: element));

    private static CombatCardDefinition Direct(int value) =>
        new($"direct-{value}", new(DirectDamage: value));

    private static CombatCardDefinition Fuel(int value) =>
        new($"fuel-{value}", new(ElementalDamage: value, Element: CardElement.Fire, SameElementBonus: 2));

    private static CombatCardDefinition Tuning(CardElement element, int value) =>
        new($"tuning-{element}-{value}", new(ElementalDamage: value, Element: element, IsElementTuning: true));

    private static CombatCardDefinition Boss() =>
        new("boss", new(ElementalDamage: 8, Element: CardElement.Fire,
            SecondaryElementalDamage: 8, SecondaryElement: CardElement.Metal));

    private static void AssertBaseline(
        CardResolutionDraft actual,
        int damage,
        int heal,
        CardElement? core,
        int coreCount,
        double resonance,
        int conflictPairs,
        double cancellation)
    {
        Assert.Equal(damage, actual.Damage);
        Assert.Equal(heal, actual.Heal);
        Assert.Equal(core, actual.CoreElement);
        Assert.Equal(coreCount, actual.CoreCount);
        Assert.Equal(resonance, actual.ResonanceMultiplier, 6);
        Assert.Equal(conflictPairs, actual.ConflictPairCount);
        Assert.Equal(cancellation, actual.ConflictCancellation, 6);
    }

    private static void AssertSegments(CardResolutionDraft actual, params (string Kind, int Amount)[] expected)
    {
        var actualSegments = actual.DamageSegments!.ToDictionary(segment => segment.Kind, segment => segment.Amount, StringComparer.Ordinal);
        Assert.Equal(expected.Length, actualSegments.Count);
        foreach (var (kind, amount) in expected)
        {
            Assert.Equal(amount, actualSegments[kind]);
        }
    }
}
