using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class Pr13BoundaryContractTests
{
    private static PlayerCombatState State() => new(HeroClass.Mage,
        Enumerable.Repeat("common-01", 20).ToArray(), new Random(31));

    [Fact]
    public void Published_policy_contract_has_no_retired_bool_or_remainder_property()
    {
        var parameters = typeof(PlayerCombatState).GetConstructors().Single().GetParameters();
        Assert.DoesNotContain(parameters, p => p.Name == "useConsumptionBasedFenxian");
        Assert.Contains(parameters, p => p.Name == "fenxianImmediateDrawPolicy" && p.ParameterType == typeof(FenxianImmediateDrawPolicy));
        Assert.Contains(parameters, p => p.Name == "guardianShieldBonusPolicy" && p.ParameterType == typeof(GuardianShieldBonusPolicy));
        Assert.Null(typeof(PlayerCombatState).GetProperty("GuardianShieldRemainder"));
        Assert.Equal(typeof(int), typeof(PlayerCombatState).GetProperty("GuardianShieldRemainderTenths")!.PropertyType);
        var state = State();
        Assert.Equal(FenxianImmediateDrawPolicy.CurrentRhythm, state.FenxianDrawPolicy);
        Assert.Equal(GuardianShieldBonusPolicy.CurrentSteps, state.GuardianShieldPolicy);
    }

    [Fact]
    public void Stun_window_expires_at_exactly_eight_seconds_but_not_7999_milliseconds()
    {
        var state = State();
        Assert.Equal(TimeSpan.FromSeconds(2), state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
        state.Advance(TimeSpan.FromMilliseconds(7999), false);
        Assert.Equal(TimeSpan.FromSeconds(1), state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
        state.Advance(TimeSpan.FromMilliseconds(1), false);
        Assert.Equal(TimeSpan.FromSeconds(2), state.ResolveTargetStun("target", TimeSpan.FromSeconds(2)));
    }

    [Fact]
    public void Restored_stun_windows_keep_target_identity_and_remaining_deadline()
    {
        var state = State();
        state.ResolveTargetStun("first", TimeSpan.FromSeconds(2));
        state.Advance(TimeSpan.FromSeconds(3), false);
        state.ResolveTargetStun("second", TimeSpan.FromSeconds(2));
        var restored = State();
        restored.Restore(state.Capture());
        Assert.Equal(TimeSpan.FromSeconds(1), restored.ResolveTargetStun("first", TimeSpan.FromSeconds(2)));
        Assert.Equal(TimeSpan.FromSeconds(1), restored.ResolveTargetStun("second", TimeSpan.FromSeconds(2)));
        Assert.Equal(TimeSpan.FromSeconds(2), restored.ResolveTargetStun("third", TimeSpan.FromSeconds(2)));
        restored.Advance(TimeSpan.FromSeconds(5), false);
        Assert.Equal(TimeSpan.FromSeconds(2), restored.ResolveTargetStun("first", TimeSpan.FromSeconds(2)));
        Assert.Equal(TimeSpan.Zero, restored.ResolveTargetStun("second", TimeSpan.FromSeconds(2)));
    }

    [Fact]
    public void Full_hand_caps_requested_draw_without_consuming_library_or_copying_instances()
    {
        var state = State();
        state.DrawImmediate(2);
        Assert.Equal(5, state.Deck.Hand.Count);
        var before = state.Deck.Capture();
        state.SetFenxian(CardElement.Fire, 4, 4);
        var request = state.UpdateFenxian(CardElement.Fire, 1);
        Assert.Equal(2, request.Draw);
        state.DrawImmediate(request.Draw);
        Assert.Equivalent(before, state.Deck.Capture(), strict: true);
    }

    [Fact]
    public void Exhausted_library_shuffles_discard_without_losing_or_duplicating_instances()
    {
        var random = new Random(31);
        var deck = CombatDeck.Create(Enumerable.Repeat("common-01", 20).ToArray(), random);
        var identities = deck.Hand.Concat(deck.Library).Select(c => c.InstanceId).Order().ToArray();
        for (var play = 0; play < 120; play++)
        {
            var selected = deck.SelectFromHand([deck.Hand[0].InstanceId]);
            deck.DiscardPlayed(selected);
            deck.DrawImmediate(1, random);
            Assert.Equal(3, deck.Hand.Count);
            Assert.Equal(identities, deck.Hand.Concat(deck.Library).Concat(deck.Discard).Select(c => c.InstanceId).Order().ToArray());
        }
    }
}
