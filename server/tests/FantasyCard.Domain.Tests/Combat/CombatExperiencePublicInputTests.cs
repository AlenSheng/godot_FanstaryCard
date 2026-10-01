using System.Reflection;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class CombatExperiencePublicInputTests
{
    [Theory]
    [InlineData("basic")]
    [InlineData("build")]
    public void Hidden_future_intent_cannot_change_the_selected_cards(string strategy)
    {
        var player = new PlayerCombatState(HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), new Random(17));
        player.Deck.Restore(new([new(Guid.NewGuid(), "common-01"), new(Guid.NewGuid(), "common-06"),
            new(Guid.NewGuid(), "common-18")], [], [], 0));
        var fire = Target(CardElement.Fire);
        var water = Target(CardElement.Water);
        Assert.Equal(fire.Intents[fire.IntentIndex], water.Intents[water.IntentIndex]);
        Assert.NotEqual(fire.ElementalResistance(CardElement.Fire), water.ElementalResistance(CardElement.Fire));
        var before = player.Capture();

        var first = Select(player, fire, strategy);
        var second = Select(player, water, strategy);

        Assert.Equal(first.Select(card => card.InstanceId), second.Select(card => card.InstanceId));
        Assert.Equivalent(before, player.Capture(), strict: true);
    }

    private static MonsterCombatState Target(CardElement future) => new("counterexample", 7, 7, 0,
        TimeSpan.FromSeconds(4), [new(MonsterIntentKind.Charge, 0, CardElement.None), new(MonsterIntentKind.Attack, 1, future)]);

    private static CombatCardInstance[] Select(PlayerCombatState player, MonsterCombatState target, string strategy) =>
        (CombatCardInstance[])typeof(CombatExperience).GetMethod("Select", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, [CombatCardCatalog.CreatePrototype(), player, target, strategy])!;
}
