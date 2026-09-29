using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class GuardianShieldBonusPolicyTests
{
    [Theory]
    [InlineData(0, 14)]
    [InlineData(1, 14)]
    [InlineData(2, 15)]
    [InlineData(3, 15)]
    [InlineData(4, 16)]
    [InlineData(5, 16)]
    public void Default_policy_preserves_current_integer_steps(int weaponLevel, int expected)
    {
        var state = State(weaponLevel);

        var resolved = state.PreviewShield(9);

        Assert.Equal(expected, resolved.Shield);
        Assert.Null(resolved.RemainderTenthsAfter);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
    }

    [Theory]
    [InlineData(0, 5)]
    [InlineData(1, 7)]
    [InlineData(2, 9)]
    [InlineData(3, 11)]
    [InlineData(4, 13)]
    [InlineData(5, 15)]
    public void Fractional_policy_delivers_expected_five_play_weapon_contribution(int weaponLevel, int expectedWeaponContribution)
    {
        var state = State(weaponLevel, GuardianShieldBonusPolicy.FractionalRemainder);
        var totalGain = 0;

        for (var index = 0; index < 5; index++)
            totalGain += PlayShield(state, 1);

        Assert.Equal(5 + expectedWeaponContribution, totalGain);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
    }

    [Fact]
    public void Resolve_preview_calculates_next_remainder_without_mutating_state()
    {
        var state = State(1, GuardianShieldBonusPolicy.FractionalRemainder);
        var card = new CombatCardDefinition("shield", new(Shield: 1));

        var first = CombatResolver.Resolve([card], state);
        var second = CombatResolver.Resolve([card], state);

        Assert.Equal(2, first.Shield);
        Assert.Equal(4, first.GuardianShieldRemainderTenthsAfter);
        Assert.Equal(first.Shield, second.Shield);
        Assert.Equal(first.GuardianShieldRemainderTenthsAfter, second.GuardianShieldRemainderTenthsAfter);
        Assert.Equal(first.Damage, second.Damage);
        Assert.Equal(first.Heal, second.Heal);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
        Assert.Equal(0, state.Shield);
    }

    [Fact]
    public void Successful_candidate_plays_commit_deterministic_remainder()
    {
        var state = State(1, GuardianShieldBonusPolicy.FractionalRemainder);

        Assert.Equal(2, PlayShield(state, 1));
        Assert.Equal(4, state.GuardianShieldRemainderTenths);
        Assert.Equal(2, PlayShield(state, 1));
        Assert.Equal(8, state.GuardianShieldRemainderTenths);
        Assert.Equal(3, PlayShield(state, 1));
        Assert.Equal(2, state.GuardianShieldRemainderTenths);
    }

    [Fact]
    public void Full_shield_does_not_generate_or_consume_remainder()
    {
        var state = State(1, GuardianShieldBonusPolicy.FractionalRemainder);
        _ = PlayShield(state, 1);
        Assert.Equal(4, state.GuardianShieldRemainderTenths);
        state.GainShield(100);
        Assert.Equal(50, state.Shield);

        var preview = state.PreviewShield(1);
        state.CommitGuardianShieldRemainder(preview.RemainderTenthsAfter);

        Assert.Null(preview.RemainderTenthsAfter);
        Assert.Equal(4, state.GuardianShieldRemainderTenths);
        Assert.Equal(50, state.Shield);
    }

    [Fact]
    public void Shield_cap_truncation_discards_candidate_remainder()
    {
        var state = State(1, GuardianShieldBonusPolicy.FractionalRemainder);
        _ = PlayShield(state, 1);
        Assert.Equal(4, state.GuardianShieldRemainderTenths);
        state.GainShield(47);
        Assert.Equal(49, state.Shield);

        var preview = state.PreviewShield(1);
        var gain = state.GainShield(preview.Shield);
        state.CommitGuardianShieldRemainder(preview.RemainderTenthsAfter);

        Assert.Equal(2, preview.Shield);
        Assert.Equal(1, gain);
        Assert.Equal(50, state.Shield);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
    }

    [Fact]
    public void Leaving_cell_clear_shield_also_clears_candidate_remainder()
    {
        var state = State(1, GuardianShieldBonusPolicy.FractionalRemainder);
        _ = PlayShield(state, 1);
        Assert.Equal(4, state.GuardianShieldRemainderTenths);

        state.ClearShield();

        Assert.Equal(0, state.Shield);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
    }

    [Fact]
    public void Candidate_remainder_round_trips_through_combat_snapshot()
    {
        var state = State(1, GuardianShieldBonusPolicy.FractionalRemainder);
        _ = PlayShield(state, 1);
        var snapshot = state.Capture();
        var restored = State(1, GuardianShieldBonusPolicy.FractionalRemainder);

        restored.Restore(snapshot);

        Assert.Equal(state.Shield, restored.Shield);
        Assert.Equal(4, restored.GuardianShieldRemainderTenths);
        Assert.Equivalent(snapshot, restored.Capture(), strict: true);
    }

    [Fact]
    public void Current_policy_never_commits_fractional_remainder()
    {
        var state = State(1, GuardianShieldBonusPolicy.CurrentSteps);
        var preview = state.PreviewShield(1);

        state.CommitGuardianShieldRemainder(preview.RemainderTenthsAfter);

        Assert.Null(preview.RemainderTenthsAfter);
        Assert.Equal(0, state.GuardianShieldRemainderTenths);
    }

    [Fact]
    public void Invalid_guardian_policy_is_rejected()
    {
        Assert.Throws<DomainValidationException>(() => new PlayerCombatState(
            HeroClass.Guardian,
            Enumerable.Repeat("common-01", 20).ToArray(),
            new Random(31),
            guardianShieldBonusPolicy: (GuardianShieldBonusPolicy)999));
    }

    private static PlayerCombatState State(
        int weaponLevel,
        GuardianShieldBonusPolicy policy = GuardianShieldBonusPolicy.CurrentSteps) =>
        new(
            HeroClass.Guardian,
            Enumerable.Repeat("common-01", 20).ToArray(),
            new Random(31),
            weaponLevel: weaponLevel,
            guardianShieldBonusPolicy: policy);

    private static int PlayShield(PlayerCombatState state, int cardShield)
    {
        var preview = state.PreviewShield(cardShield);
        var gain = state.GainShield(preview.Shield);
        state.CommitGuardianShieldRemainder(preview.RemainderTenthsAfter);
        return gain;
    }
}
