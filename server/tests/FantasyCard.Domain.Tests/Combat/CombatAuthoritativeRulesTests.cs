using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class CombatAuthoritativeRulesTests
{
    [Theory]
    [InlineData(1, 10)]
    [InlineData(2, 24)]
    [InlineData(3, 42)]
    [InlineData(4, 64)]
    [InlineData(5, 90)]
    public void Current_pure_core_curve_is_locked(int count, int damage)
    {
        var result = CombatResolver.Resolve(Enumerable.Repeat(Fire(10), count).ToArray(), State());
        Assert.Equal(damage, result.Damage);
        Assert.Equal(count, result.CoreCount);
        Assert.Equal(1 + .2 * (count - 1), result.ResonanceMultiplier, 6);
    }

    [Fact]
    public void Current_example_a_three_four_and_five_fire_are_locked()
    {
        var fuel = new CombatCardDefinition("fuel", new(ElementalDamage: 12,
            Element: CardElement.Fire, SameElementBonus: 2));
        CombatCardDefinition[] cards = [Fire(8), Fire(3), fuel, Fire(6), Fire(10)];
        var state = State(equipment: new(new(FireDamageBonus: .14)));
        Assert.Equal(46, CombatResolver.Resolve(cards[..3], state, _ => -.30).Damage);
        Assert.Equal(72, CombatResolver.Resolve(cards[..4], state, _ => -.30).Damage);
        Assert.Equal(113, CombatResolver.Resolve(cards, state, _ => -.30).Damage);
    }

    [Fact]
    public void Selection_order_changes_core_even_when_later_element_is_more_common()
    {
        CombatCardDefinition[] cards = [Fire(8), Element(CardElement.Water, 7), Element(CardElement.Water, 7)];
        var state = State(equipment: new(new(FireDamageBonus: .14)));
        var firstFire = CombatResolver.Resolve(cards, state, _ => -.30);
        var firstWater = CombatResolver.Resolve([cards[1], cards[0], cards[2]], state, _ => -.30);
        Assert.Equal(CardElement.Fire, firstFire.CoreElement);
        Assert.Equal(1, firstFire.CoreCount);
        Assert.Equal(CardElement.Water, firstWater.CoreElement);
        Assert.Equal(2, firstWater.CoreCount);
    }

    [Theory]
    [InlineData(1, 0)]
    [InlineData(2, 0)]
    [InlineData(3, 1)]
    [InlineData(4, 1)]
    [InlineData(5, 2)]
    public void Experimental_fenxian_rebate_tracks_cards_spent_not_combo(int count, int expectedDraw)
    {
        var state = new PlayerCombatState(HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(), new Random(31),
            fenxianImmediateDrawPolicy: FenxianImmediateDrawPolicy.CoreCardsSpent);
        for (var index = 0; index < 8; index++)
        {
            var (_, draw) = state.UpdateFenxian(CardElement.Fire, count);
            Assert.Equal(expectedDraw, draw);
        }
        Assert.Equal(5, state.FenxianChargeLevel);
        Assert.True(expectedDraw + .5 < count);
        var restored = new PlayerCombatState(HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(), new Random(31),
            fenxianImmediateDrawPolicy: FenxianImmediateDrawPolicy.CoreCardsSpent);
        restored.Restore(state.Capture());
        Assert.Equal(expectedDraw, restored.UpdateFenxian(CardElement.Fire, count).Draw);
    }

    [Fact]
    public void Existing_fenxian_behavior_remains_the_default()
    {
        var state = State();
        for (var index = 0; index < 4; index++) state.UpdateFenxian(CardElement.Fire, 1);
        Assert.Equal(2, state.UpdateFenxian(CardElement.Fire, 1).Draw);
        Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, state.Capture().FenxianPolicy);
    }

    [Theory]
    [InlineData(0, 5)]
    [InlineData(1, 7)]
    [InlineData(2, 9)]
    [InlineData(3, 11)]
    [InlineData(4, 13)]
    [InlineData(5, 15)]
    public void Experimental_guardian_weapon_accumulates_exact_five_cast_yield(int level, int expectedBonus)
    {
        var state = new PlayerCombatState(HeroClass.Guardian,
            Enumerable.Repeat("common-01", 20).ToArray(), new Random(31),
            weaponLevel: level, guardianShieldBonusPolicy: GuardianShieldBonusPolicy.FractionalRemainder);
        var totalBonus = 0;
        for (var index = 0; index < 5; index++)
        {
            var preview = state.PreviewShield(1);
            Assert.Equal(preview, state.PreviewShield(1));
            totalBonus += state.GainShield(preview.Shield) - 1;
            state.CommitGuardianShieldRemainder(preview.RemainderTenthsAfter);
        }
        Assert.Equal(expectedBonus, totalBonus);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
    }

    [Fact]
    public void Guardian_remainder_is_snapshotted_and_dropped_on_shield_cap()
    {
        var state = new PlayerCombatState(HeroClass.Guardian,
            Enumerable.Repeat("common-01", 20).ToArray(), new Random(31),
            weaponLevel: 1, guardianShieldBonusPolicy: GuardianShieldBonusPolicy.FractionalRemainder);
        var first = state.PreviewShield(1);
        state.GainShield(first.Shield);
        state.CommitGuardianShieldRemainder(first.RemainderTenthsAfter);
        Assert.Equal(4, state.GuardianShieldRemainderTenths);
        var restored = new PlayerCombatState(HeroClass.Guardian,
            Enumerable.Repeat("common-01", 20).ToArray(), new Random(31),
            weaponLevel: 1, guardianShieldBonusPolicy: GuardianShieldBonusPolicy.FractionalRemainder);
        restored.Restore(state.Capture());
        Assert.Equal(state.ResolveShield(1), restored.ResolveShield(1));
        Assert.Equal(4, restored.GuardianShieldRemainderTenths);
        var capped = restored.PreviewShield(100);
        restored.GainShield(capped.Shield);
        restored.CommitGuardianShieldRemainder(capped.RemainderTenthsAfter);
        Assert.Equal(0, restored.GuardianShieldRemainderTenths);
        restored.ClearShield();
        Assert.Equal(0, restored.Shield);
    }

    [Fact]
    public void Frozen_conflict_examples_preserve_damage_and_recovery()
    {
        var state = State(equipment: new(new(FireDamageBonus: .14)));
        var exampleB = CombatResolver.Resolve([Fire(8), Fire(3), Fire(12), Element(CardElement.Water, 7)], state, _ => -.30);
        var exampleC = CombatResolver.Resolve([Fire(8), Fire(8), Element(CardElement.Water, 7), Element(CardElement.Water, 7)], state, _ => -.30);

        Assert.Equal(48, exampleB.Damage);
        Assert.Equal(6, exampleB.Heal);
        Assert.Equal(34, exampleC.Damage);
        Assert.Equal(8, exampleC.Heal);
        Assert.Equal(CardElement.Fire, exampleC.CoreElement);
    }

    [Fact]
    public void Core_first_branches_keep_unrelated_damage_and_recompute_counter_damage()
    {
        var state = State();
        var result = CombatResolver.Resolve([
            Element(CardElement.Earth, 6),
            Element(CardElement.Water, 6),
            Element(CardElement.Metal, 8),
            Element(CardElement.Water, 8)], state);

        Assert.Equal(CardElement.Earth, result.CoreElement);
        Assert.Equal(1, result.CoreCount);
        Assert.Equal(21, result.Damage);
        Assert.Equal(new[] { new CombatDamageSegment("Earth", 6), new("Water", 7), new("Metal", 8) }, result.DamageSegments);

        var directOnly = CombatResolver.Resolve([Direct(9)], state, _ => .99);
        Assert.Null(directOnly.CoreElement);
        Assert.Equal(9, directOnly.Damage);
    }

    [Fact]
    public void Unrelated_third_element_does_not_add_conflict_pairs_and_selection_order_breaks_ties()
    {
        var state = State();
        var withEarth = CombatResolver.Resolve([Fire(8), Fire(8), Element(CardElement.Water, 7), Element(CardElement.Earth, 6)], state);
        var withoutEarth = CombatResolver.Resolve([Fire(8), Fire(8), Element(CardElement.Water, 7)], state);
        var waterFirst = CombatResolver.Resolve([Element(CardElement.Water, 7), Fire(8)], state);

        Assert.Equal(27, withEarth.Damage);
        Assert.Equal(withoutEarth.Heal, withEarth.Heal);
        Assert.Equal(CardElement.Water, waterFirst.CoreElement);
        Assert.Equal(13, waterFirst.Damage);
    }

    [Fact]
    public void Class_reveal_is_played_only_and_piercing_reads_fuel_then_reveal_bases()
    {
        var state = State(equipment: new(new(), PiercingBonus: .24));
        var fuel = new CombatCardDefinition("fuel", new(ElementalDamage: 12, Element: CardElement.Fire, SameElementBonus: 2));
        CombatCardDefinition[] cards = [fuel, Fire(8), Fire(8), Fire(8)];
        var normal = CombatResolver.Resolve(cards, state);
        var revealed = CombatResolver.Resolve([.. cards, new("reveal", new(IsClassReveal: true))], state);

        Assert.Equal(64, normal.Damage);
        Assert.Equal(86, revealed.Damage);
        Assert.Equal(10, revealed.DamageSegments!.Single(segment => segment.Kind == "Direct").Amount);
        Assert.Equal(0, normal.Shield);
    }

    [Fact]
    public void Resonance_bonus_is_at_most_one_and_raises_five_cards_to_two()
    {
        var state = State();
        var bonus = new CombatCardDefinition("bonus", new(ElementalDamage: 8, Element: CardElement.Fire, ResonanceBonus: 1));
        var three = CombatResolver.Resolve([bonus, bonus, Fire(8)], state);
        var five = CombatResolver.Resolve([bonus, Fire(8), Fire(8), Fire(8), Fire(8)], state);
        var plain = CombatResolver.Resolve([Fire(8), Fire(8), Fire(8), Fire(8), Fire(8)], state);

        Assert.Equal(36, three.Damage);
        Assert.Equal(80, five.Damage);
        Assert.Equal(70, plain.Damage);
    }

    [Fact]
    public void Tidal_reverse_changes_conflict_cancellation_and_recovery_coefficient()
    {
        var state = State(equipment: new(new(FireDamageBonus: .14)));
        var result = CombatResolver.Resolve([Fire(8), Fire(3), Fire(12), Element(CardElement.Water, 7),
            new("tidal", new(ConflictCancelBonus: .15, ConflictHealCoefficient: .70))], state, _ => -.30);

        Assert.Equal(46, result.Damage);
        Assert.Equal(12, result.Heal);
    }

    [Fact]
    public void Element_tuning_uses_resonance_without_taking_or_creating_conflict_cancellation()
    {
        var state = State();
        var protectedResult = CombatResolver.Resolve(
            [Fire(10), Tuning(CardElement.Fire, 10), Element(CardElement.Water, 1)], state);
        var ordinaryResult = CombatResolver.Resolve(
            [Fire(10), Fire(10), Element(CardElement.Water, 1)], state);
        var tuningOnlyCore = CombatResolver.Resolve(
            [Tuning(CardElement.Fire, 10), Element(CardElement.Water, 10)], state);

        Assert.Equal(20, protectedResult.Damage);
        Assert.Equal(3, protectedResult.Heal);
        Assert.Equal(20, ordinaryResult.Damage);
        Assert.Equal(4, ordinaryResult.Heal);
        Assert.Equal(18, tuningOnlyCore.Damage);
        Assert.Equal(2, tuningOnlyCore.Heal);
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
        Assert.Equal(30, combined.Damage);
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
    private static CombatCardDefinition Direct(int value) => new("direct", new(DirectDamage: value));
    private static CombatCardDefinition Tuning(CardElement element, int value) =>
        new("tuning", new(ElementalDamage: value, Element: element, IsElementTuning: true));
}
