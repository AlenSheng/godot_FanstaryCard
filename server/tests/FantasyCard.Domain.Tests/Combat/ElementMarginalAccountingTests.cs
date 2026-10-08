using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class ElementMarginalAccountingTests(ITestOutputHelper output)
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static PlayerCombatState State() => new(HeroClass.Mage,
        Enumerable.Range(1, 20).Select(i => $"C{i:D2}").ToArray(), new Random(53));

    [Fact]
    public void Same_quality_water_request_is_not_an_applied_draw_when_hand_is_full()
    {
        var fire = GameConfigCatalog.Current.Cards.Single(c => c.CardId == "ET-FIRE-G");
        var water = GameConfigCatalog.Current.Cards.Single(c => c.CardId == "ET-WATER-G");
        Assert.Equal(fire.Rarity, water.Rarity); Assert.Equal(fire.UnlockCost, water.UnlockCost);
        var state = State(); state.DrawImmediate(2);
        var original = state.Deck.Capture(); var draft = CombatResolver.Resolve([Catalog.Get(water.CardId)], state);
        Assert.Equal(1, draft.ImmediateDraw);
        state.DrawImmediate(draft.ImmediateDraw);
        Assert.Equivalent(original, state.Deck.Capture(), strict: true);
        output.WriteLine("PR13_MARGINAL requestedDraw=1 actualDraw=0 overflowDraw=1 publishedCard=ET-WATER-G sameQuality=Green sameLevel=0 naturalSeconds=0");
    }

    [Fact]
    public void Same_quality_metal_control_reports_union_instead_of_sum_of_printed_windows()
    {
        var fire = GameConfigCatalog.Current.Cards.Single(c => c.CardId == "ET-FIRE-G");
        var metal = GameConfigCatalog.Current.Cards.Single(c => c.CardId == "ET-METAL-G");
        Assert.Equal(fire.Rarity, metal.Rarity); Assert.Equal(fire.UnlockCost, metal.UnlockCost);
        var state = State(); var draft = CombatResolver.Resolve([Catalog.Get(metal.CardId)], state);
        var target = new MonsterCombatState("one-real-target", 500, 500, 0, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Attack, 3, CardElement.Wood)]);
        var one = state.ResolveTargetStun(target.MonsterId, draft.Stun);
        var two = state.ResolveTargetStun(target.MonsterId, draft.Stun);
        var three = state.ResolveTargetStun(target.MonsterId, draft.Stun);
        target.ApplyStun(one); target.ApplyStun(two); target.ApplyStun(three);
        Assert.Equal(draft.Stun, one); Assert.Equal(one / 2, two); Assert.Equal(TimeSpan.Zero, three);
        Assert.Equal(one, target.StunRemaining); Assert.True(one + two > target.StunRemaining);
        output.WriteLine($"PR13_MARGINAL nominalSeconds={(one + two).TotalSeconds} actualUnionSeconds={target.StunRemaining.TotalSeconds} castsAtSameMonotonicInstant=true publishedCard=ET-METAL-G");
    }

    [Fact]
    public void Full_health_and_shield_split_real_effective_recovery_from_overflow()
    {
        var state = State(); state.GainShield(state.MaximumHp / 2);
        var heal = CombatResolver.Resolve([Catalog.Get("C15")], state);
        var shield = CombatResolver.Resolve([Catalog.Get("C17")], state);
        var effectiveHeal = state.Heal(heal.Heal); var effectiveShield = state.GainShield(shield.Shield);
        Assert.True(heal.Heal > 0); Assert.True(shield.Shield > 0);
        Assert.Equal(0, effectiveHeal); Assert.Equal(0, effectiveShield);
        Assert.Equal(state.MaximumHp, state.Hp); Assert.Equal(state.MaximumHp / 2, state.Shield);
        output.WriteLine($"PR13_MARGINAL requestedHeal={heal.Heal} effectiveHeal={effectiveHeal} healOverflow={heal.Heal-effectiveHeal} requestedShield={shield.Shield} effectiveShield={effectiveShield} shieldOverflow={shield.Shield-effectiveShield} printedLevelZeroCards=C15,C17");
    }
}
