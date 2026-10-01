using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class CombatExperienceStaleActionTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();

    [Fact]
    public void Missing_living_target_returns_a_reasoned_wait_without_mutation()
    {
        var (room, player) = Create();
        foreach (var monster in player.Pve!.Monsters) monster.TakeDamage(monster.Hp + monster.Shield);
        var before = room.Capture();
        var action = CombatExperience.ChooseAction(Catalog, room, player, "baseline_all_hand");
        Assert.Equal("no_living_target", action.WaitReason);
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Theory]
    [InlineData("target", "target_no_longer_alive")]
    [InlineData("hand", "hand_changed")]
    [InlineData("frozen", "battle_not_active")]
    public void Execution_rechecks_state_and_returns_wait_without_business_mutation(string invalidation, string expected)
    {
        var (room, player) = Create();
        var action = CombatExperience.ChooseAction(Catalog, room, player, "baseline_all_hand");
        Assert.Null(action.WaitReason);
        if (invalidation == "target")
        {
            var target = player.Pve!.GetTarget(action.TargetId!);
            target.TakeDamage(target.Hp + target.Shield);
        }
        else if (invalidation == "hand") player.Combat.Deck.DiscardPlayed(player.Combat.Deck.Hand.ToArray());
        else player.Pve!.Freeze();
        var before = room.Capture();
        Assert.Null(CombatExperience.Execute(room, player, action, DateTimeOffset.UnixEpoch, out var reason));
        Assert.Equal(expected, reason);
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Fact]
    public void Unexpected_domain_error_is_not_converted_to_wait()
    {
        var (room, player) = Create();
        player.Combat.Deck.Restore(new([new(Guid.NewGuid(), "unknown-card")], [], [], 0));
        var action = CombatExperience.ChooseAction(Catalog, room, player, "baseline_all_hand");
        Assert.Throws<DomainValidationException>(() => CombatExperience.Execute(room, player, action,
            DateTimeOffset.UnixEpoch, out _));
    }

    private static (BattleRoom Room, RoomPlayerState Player) Create()
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 37);
        var monster = new MonsterCombatState("test-monster", 500, 500, 0, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Attack, 1, CardElement.Wood)]);
        var player = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage,
            Enumerable.Repeat("common-01", 20).ToArray(), new(Guid.NewGuid(), null, [monster])));
        return (room, player);
    }
}
