using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class FenxianImmediateDrawPolicyTests
{
    [Fact]
    public void Default_policy_preserves_current_rhythm_based_draws()
    {
        var state = State();

        var results = Enumerable.Range(0, 5)
            .Select(_ => state.UpdateFenxian(CardElement.Fire, 1))
            .ToArray();

        Assert.Equal(new[] { 0, 0, 1, 1, 2 }, results.Select(result => result.Draw).ToArray());
        var expectedCharge = new[] { .18, .30, .42, .50, .50 };
        for (var index = 0; index < expectedCharge.Length; index++)
        {
            Assert.Equal(expectedCharge[index], results[index].Charge, 6);
        }
        Assert.Equal(5, state.FenxianCombo);
        Assert.Equal(5, state.FenxianChargeLevel);
    }

    [Fact]
    public void Cards_spent_policy_does_not_return_a_single_core_card_even_at_max_combo()
    {
        var state = State(FenxianImmediateDrawPolicy.CoreCardsSpent);

        var results = Enumerable.Range(0, 8)
            .Select(_ => state.UpdateFenxian(CardElement.Fire, 1))
            .ToArray();

        Assert.All(results, result => Assert.Equal(0, result.Draw));
        Assert.Equal(5, state.FenxianChargeLevel);
        Assert.Equal(.50, results[^1].Charge, 6);
    }

    [Fact]
    public void Cards_spent_policy_keeps_three_four_five_card_identity()
    {
        var three = State(FenxianImmediateDrawPolicy.CoreCardsSpent).UpdateFenxian(CardElement.Fire, 3);
        var four = State(FenxianImmediateDrawPolicy.CoreCardsSpent).UpdateFenxian(CardElement.Fire, 4);
        var five = State(FenxianImmediateDrawPolicy.CoreCardsSpent).UpdateFenxian(CardElement.Fire, 5);

        Assert.Equal(1, three.Draw);
        Assert.Equal(1, four.Draw);
        Assert.Equal(2, five.Draw);
        Assert.Equal(.42, three.Charge, 6);
        Assert.Equal(.50, four.Charge, 6);
        Assert.Equal(.50, five.Charge, 6);
    }

    [Fact]
    public void Cards_spent_policy_keeps_combo_for_charge_but_not_for_draw_count()
    {
        var state = State(FenxianImmediateDrawPolicy.CoreCardsSpent);

        var first = state.UpdateFenxian(CardElement.Fire, 2);
        var second = state.UpdateFenxian(CardElement.Fire, 2);
        var third = state.UpdateFenxian(CardElement.Fire, 2);

        Assert.Equal(new[] { 0, 0, 0 }, new[] { first.Draw, second.Draw, third.Draw });
        Assert.Equal(.30, first.Charge, 6);
        Assert.Equal(.42, second.Charge, 6);
        Assert.Equal(.50, third.Charge, 6);
        Assert.Equal(4, state.FenxianChargeLevel);
    }

    [Fact]
    public void Core_change_resets_combo_without_changing_cards_spent_draw_rule()
    {
        var state = State(FenxianImmediateDrawPolicy.CoreCardsSpent);
        _ = state.UpdateFenxian(CardElement.Fire, 3);
        _ = state.UpdateFenxian(CardElement.Fire, 3);

        var changed = state.UpdateFenxian(CardElement.Water, 3);

        Assert.Equal(1, state.FenxianCombo);
        Assert.Equal(CardElement.Water, state.LastFenxianCore);
        Assert.Equal(3, state.FenxianChargeLevel);
        Assert.Equal(1, changed.Draw);
        Assert.Equal(.42, changed.Charge, 6);
    }

    [Fact]
    public void Candidate_single_card_sequence_exhausts_starting_hand_without_natural_draws()
    {
        var state = State(FenxianImmediateDrawPolicy.CoreCardsSpent);
        var hand = 3;
        var plays = 0;

        while (hand > 0 && plays < 20)
        {
            hand--;
            var fenxian = state.UpdateFenxian(CardElement.Fire, 1);
            hand += fenxian.Draw;
            plays++;
        }

        Assert.Equal(3, plays);
        Assert.Equal(0, hand);
    }

    [Fact]
    public void Non_mage_never_receives_fenxian_rewards_under_candidate_policy()
    {
        var state = new PlayerCombatState(
            HeroClass.Priest,
            Enumerable.Repeat("common-01", 20).ToArray(),
            new Random(31),
            fenxianImmediateDrawPolicy: FenxianImmediateDrawPolicy.CoreCardsSpent);

        var result = state.UpdateFenxian(CardElement.Water, 5);

        Assert.Equal((0d, 0), result);
        Assert.Equal(0, state.FenxianCombo);
        Assert.Null(state.LastFenxianCore);
    }

    [Fact]
    public void Invalid_policy_is_rejected_at_state_construction()
    {
        Assert.Throws<DomainValidationException>(() => new PlayerCombatState(
            HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(),
            new Random(31),
            fenxianImmediateDrawPolicy: (FenxianImmediateDrawPolicy)999));
    }

    private static PlayerCombatState State(
        FenxianImmediateDrawPolicy policy = FenxianImmediateDrawPolicy.CurrentRhythm) =>
        new(
            HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(),
            new Random(31),
            fenxianImmediateDrawPolicy: policy);
}
