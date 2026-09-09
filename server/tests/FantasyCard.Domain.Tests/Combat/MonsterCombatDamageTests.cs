using FantasyCard.Domain.Combat;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class MonsterCombatDamageTests
{
    [Fact]
    public void Elemental_damage_applies_player_equipment_resistance_after_monster_amplification()
    {
        var monster = new MonsterCombatState(
            "fire-herald", 100, 100, 0, TimeSpan.FromSeconds(4),
            [new MonsterIntentState(MonsterIntentKind.Attack, 9, CardElement.Fire)],
            elementalAmplification: .15);

        Assert.Equal(9, monster.ResolveIntentDamage(monster.Intents[0], .08));
    }

    [Theory]
    [InlineData(CardElement.Metal, .25)]
    [InlineData(CardElement.Water, .15)]
    [InlineData(CardElement.Fire, -.30)]
    [InlineData(CardElement.Wood, .25)]
    [InlineData(CardElement.Earth, 0)]
    public void Elite_resistance_vector_matches_the_gdd(CardElement incoming, double expected)
    {
        var monster = new MonsterCombatState(
            "metal-guard", 200, 200, 12, TimeSpan.FromSeconds(4.4),
            [new MonsterIntentState(MonsterIntentKind.Attack, 4, CardElement.Metal)],
            elementalAmplification: .15);

        Assert.Equal(expected, monster.ElementalResistance(incoming), 6);
    }

    [Fact]
    public void Boss_switches_phase_only_after_the_current_step_finishes()
    {
        var boss = CreateBoss();

        boss.TakeDamage(140);

        Assert.True(boss.BossPhaseTransitionPending);
        Assert.Equal(1, boss.BossPhase);
        Assert.Equal(.35, boss.ElementalResistance(CardElement.Fire), 6);

        boss.ResolveIntentDamage(boss.Intents[0]);

        Assert.False(boss.BossPhaseTransitionPending);
        Assert.Equal(2, boss.BossPhase);
        Assert.Equal(TimeSpan.FromSeconds(3.8), boss.AttackInterval);
        Assert.Equal(CardElement.Metal, boss.Intents[0].Element);
        Assert.Equal(-.30, boss.ElementalResistance(CardElement.Fire), 6);
    }

    [Fact]
    public void Pending_boss_transition_survives_snapshot_and_stun_cancel_completes_it()
    {
        var boss = CreateBoss();
        boss.SetRuntimeState(
            0,
            TimeSpan.Zero,
            TimeSpan.FromSeconds(.4),
            false,
            0,
            TimeSpan.Zero,
            new Dictionary<string, TimeSpan>());
        boss.TakeDamage(140);
        var restored = MonsterCombatState.Restore(boss.Capture());

        restored.ApplyStun(TimeSpan.FromSeconds(1));

        Assert.Equal(2, restored.BossPhase);
        Assert.False(restored.BossPhaseTransitionPending);
        Assert.Equal(0, restored.IntentIndex);
    }

    private static MonsterCombatState CreateBoss() => new(
        "annihilation-core",
        280,
        280,
        0,
        TimeSpan.FromSeconds(4.4),
        [
            new(MonsterIntentKind.Attack, 4, CardElement.Fire),
            new(MonsterIntentKind.Attack, 4, CardElement.Wood),
            new(MonsterIntentKind.Shield, 10, CardElement.None),
            new(MonsterIntentKind.Attack, 5, CardElement.Fire),
            new(MonsterIntentKind.Charge, 0, CardElement.None),
            new(MonsterIntentKind.Direct, 6, CardElement.None)
        ],
        .20);
    [Fact]
    public void ElementalIntent_AppliesAmplificationThenFloors()
    {
        var monster = new MonsterCombatState(
            "elite", 100, 100, 0, TimeSpan.FromSeconds(4),
            [new MonsterIntentState(MonsterIntentKind.Attack, 5, CardElement.Fire)],
            elementalAmplification: 0.20);

        Assert.Equal(6, monster.ResolveIntentDamage(monster.Intents[0]));
    }

    [Fact]
    public void DirectIntent_DoesNotApplyElementalAmplification()
    {
        var monster = new MonsterCombatState(
            "elite", 100, 100, 0, TimeSpan.FromSeconds(4),
            [new MonsterIntentState(MonsterIntentKind.Direct, 5, CardElement.None)],
            elementalAmplification: 0.20);

        Assert.Equal(5, monster.ResolveIntentDamage(monster.Intents[0]));
    }
}
