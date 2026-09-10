using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class CombatAuthoritativeRulesTests
{
    [Fact]
    public void Frozen_conflict_examples_preserve_damage_and_recovery()
    {
        var state = State(equipment: new(new(FireDamageBonus: .14)));
        var exampleB = CombatResolver.Resolve([Fire(8), Fire(3), Fire(12), Element(CardElement.Water, 7)], state, _ => -.30);
        var exampleC = CombatResolver.Resolve([Fire(8), Fire(8), Element(CardElement.Water, 7), Element(CardElement.Water, 7)], state, _ => -.30);

        Assert.Equal(40, exampleB.Damage);
        Assert.Equal(7, exampleB.Heal);
        Assert.Equal(17, exampleC.Damage);
        Assert.Equal(9, exampleC.Heal);
        Assert.Equal(CardElement.Fire, exampleC.CoreElement);
    }

    [Fact]
    public void Unrelated_third_element_does_not_add_conflict_pairs_and_selection_order_breaks_ties()
    {
        var state = State();
        var withEarth = CombatResolver.Resolve([Fire(8), Fire(8), Element(CardElement.Water, 7), Element(CardElement.Earth, 6)], state);
        var withoutEarth = CombatResolver.Resolve([Fire(8), Fire(8), Element(CardElement.Water, 7)], state);
        var waterFirst = CombatResolver.Resolve([Element(CardElement.Water, 7), Fire(8)], state);

        Assert.Equal(withoutEarth.Damage, withEarth.Damage);
        Assert.Equal(withoutEarth.Heal, withEarth.Heal);
        Assert.Equal(CardElement.Water, waterFirst.CoreElement);
        Assert.Equal(5, waterFirst.Damage);
    }

    [Fact]
    public void Class_reveal_is_played_only_and_piercing_reads_fuel_then_reveal_bases()
    {
        var state = State(equipment: new(new(), PiercingBonus: .24));
        var fuel = new CombatCardDefinition("fuel", new(ElementalDamage: 12, Element: CardElement.Fire, SameElementBonus: 2));
        CombatCardDefinition[] cards = [fuel, Fire(8), Fire(8), Fire(8)];
        var normal = CombatResolver.Resolve(cards, state);
        var revealed = CombatResolver.Resolve([.. cards, new("reveal", new(IsClassReveal: true))], state);

        Assert.Equal(82, normal.Damage); // 38 * 2 + (3 + 1 + 1 + 1).
        Assert.Equal(106, revealed.Damage); // (18 + 10 + 10 + 10) * 2 + (4 + 2 + 2 + 2).
        Assert.Equal(10, revealed.DamageSegments!.Single(segment => segment.Kind == "Direct").Amount);
        Assert.Equal(0, normal.Shield);
    }

    [Fact]
    public void Resonance_bonus_is_at_most_one_and_only_bonus_can_raise_five_cards_to_three_point_five()
    {
        var state = State();
        var bonus = new CombatCardDefinition("bonus", new(ElementalDamage: 8, Element: CardElement.Fire, ResonanceBonus: 1));
        var three = CombatResolver.Resolve([bonus, bonus, Fire(8)], state);
        var five = CombatResolver.Resolve([bonus, Fire(8), Fire(8), Fire(8), Fire(8)], state);
        var plain = CombatResolver.Resolve([Fire(8), Fire(8), Fire(8), Fire(8), Fire(8)], state);

        Assert.Equal(48, three.Damage);
        Assert.Equal(140, five.Damage);
        Assert.Equal(120, plain.Damage);
    }

    [Fact]
    public void Tidal_reverse_changes_conflict_cancellation_and_recovery_coefficient()
    {
        var state = State(equipment: new(new(FireDamageBonus: .14)));
        var result = CombatResolver.Resolve([Fire(8), Fire(3), Fire(12), Element(CardElement.Water, 7),
            new("tidal", new(ConflictCancelBonus: .15, ConflictHealCoefficient: .70))], state, _ => -.30);

        Assert.Equal(33, result.Damage);
        Assert.Equal(14, result.Heal);
    }

    [Fact]
    public void Conflict_card_healing_uses_priest_then_vitality_but_conflict_recovery_only_uses_vitality()
    {
        var state = State(HeroClass.Priest, new(new(), VitalityHealBonus: .20));
        state.TakeDamage(40);
        var result = CombatResolver.Resolve([Fire(8), Element(CardElement.Water, 7), new("heal", new(Heal: 8))], state);

        // Card: floor(floor(8 * 1.25 * 1.4) * 1.06) * 1.2 = 16; conflict: floor((0 + 2) * 1.2) = 2.
        Assert.Equal(18, result.Heal);
    }

    [Fact]
    public void Boss_card_resolves_fire_metal_and_shield_without_resonance_or_conflict()
    {
        var state = State(equipment: new(new(FireDamageBonus: .25, MetalDamageBonus: .50), PiercingBonus: .25));
        var boss = new CombatCardDefinition("boss", new(ElementalDamage: 8, Element: CardElement.Fire, Shield: 8,
            SecondaryElementalDamage: 8, SecondaryElement: CardElement.Metal));
        var result = CombatResolver.Resolve([boss], state, element => element == CardElement.Fire ? .20 : .25);
        var combined = CombatResolver.Resolve([boss, Fire(8)], state, element => element == CardElement.Fire ? .20 : .25);

        Assert.Equal(21, result.Damage);
        Assert.Equal(8, result.Shield);
        Assert.Equal(0, result.Heal);
        Assert.Null(result.CoreElement);
        Assert.Equal(new[] { new CombatDamageSegment("Fire", 8), new("Metal", 9), new("Direct", 4) }, result.DamageSegments);
        Assert.Equal(1, combined.CoreCount);
        Assert.Equal(31, combined.Damage);
        Assert.Equal(0, combined.Heal);
    }

    [Fact]
    public void Guardian_shield_uses_health_after_cost_and_one_combined_floor_without_a_free_shield_on_other_cards()
    {
        var state = State(HeroClass.Guardian, new(new(), BulwarkShieldBonus: .10));
        var result = CombatResolver.Resolve([new("shield", new(Shield: 18, HealthCost: 6))], state);

        Assert.Equal(29, result.Shield);
        Assert.Equal(100, state.Hp);
        Assert.Equal(0, CombatResolver.Resolve([Fire(8)], state).Shield);
    }

    [Fact]
    public void Damage_segments_group_types_and_round_to_actual_shield_plus_hp_damage()
    {
        CombatDamageSegment[] segments = [new("Fire", 20), new("Fire", 16), new("Direct", 21)];
        var reduced = CombatResolver.ResolveDamageSegments(segments, 50, .88);
        var overkill = CombatResolver.ResolveDamageSegments(segments, 7, .88);

        Assert.Equal(new[] { new CombatDamageSegment("Fire", 32), new("Direct", 18) }, reduced);
        Assert.Equal(7, overkill.Sum(segment => segment.Amount));
        Assert.All(overkill, segment => Assert.True(segment.Amount > 0));
        Assert.Empty(CombatResolver.ResolveDamageSegments(segments, 0));
    }

    [Fact]
    public void Stun_window_halves_second_stun_ignores_third_and_expires_without_extending()
    {
        var state = State();
        Assert.Equal(TimeSpan.FromSeconds(2), state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
        state.Advance(TimeSpan.FromSeconds(3), false);
        Assert.Equal(TimeSpan.FromSeconds(1), state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
        Assert.Equal(TimeSpan.Zero, state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
        Assert.Equal(TimeSpan.FromSeconds(2), state.ResolveTargetStun("other", TimeSpan.FromSeconds(2)));
        state.Advance(TimeSpan.FromSeconds(5), false);
        Assert.Equal(TimeSpan.FromSeconds(2), state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
    }

    [Fact]
    public void Converted_draw_block_doubles_charge_for_exact_duration_and_survives_snapshot()
    {
        var state = State(equipment: new(new(), DrawIntervalModifier: -.20));
        state.ApplyDrawBlockSpeed(TimeSpan.FromSeconds(1));
        state.ApplyDrawBlockSpeed(TimeSpan.FromSeconds(.5));
        Assert.Equal(1.6, state.DrawIntervalSeconds);
        var restored = State(equipment: state.Equipment);
        restored.Restore(state.Capture());

        restored.Advance(TimeSpan.FromSeconds(2), true);

        Assert.Equal(.9375, restored.Deck.DrawCharge, 6);
        Assert.Equal(TimeSpan.Zero, restored.DrawBlockSpeedRemaining);
        Assert.Equal(3.2, restored.DrawIntervalSeconds);
    }

    private static PlayerCombatState State(HeroClass heroClass = HeroClass.Mage, CombatEquipmentProfile? equipment = null) =>
        new(heroClass, Enumerable.Repeat("common-01", 20).ToArray(), new Random(31), equipment: equipment);

    private static CombatCardDefinition Fire(int value) => Element(CardElement.Fire, value);
    private static CombatCardDefinition Element(CardElement element, int value) => new("damage", new(ElementalDamage: value, Element: element));
}
