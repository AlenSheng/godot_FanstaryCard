using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class CombatSelectionOrderContractTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(10);

    [Fact]
    public void Preview_resolves_core_from_selected_instance_order_without_mutating_room()
    {
        var room = CreateRoom();
        var player = room.GetPlayer(room.Capture().Players[0].PlayerId);
        SetHand(player, "common-02", "common-06"); // fire 3, water 6
        var fire = player.Combat.Deck.Hand.Single(card => card.CardId == "common-02");
        var water = player.Combat.Deck.Hand.Single(card => card.CardId == "common-06");
        var before = room.Capture();

        var fireFirst = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "test-monster",
            [fire.InstanceId, water.InstanceId], room.Revision, Now);
        var waterFirst = room.PreviewCards(player.PlayerId, player.Pve.BattleId, "test-monster",
            [water.InstanceId, fire.InstanceId], room.Revision, Now);

        Assert.Equal(CardElement.Fire, fireFirst.CoreElement);
        Assert.Equal(CardElement.Water, waterFirst.CoreElement);
        Assert.Equal(1, fireFirst.CoreCount);
        Assert.Equal(1, waterFirst.CoreCount);
        Assert.Equal(7, fireFirst.Damage);
        Assert.Equal(8, waterFirst.Damage);
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    private static BattleRoom CreateRoom()
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 77);
        var playerId = Guid.NewGuid();
        var monster = new MonsterCombatState("test-monster", 500, 500, 0, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Attack, 3, CardElement.Wood)]);
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(),
            new(Guid.NewGuid(), null, [monster]), DisplayName: "Player"));
        return room;
    }

    private static void SetHand(RoomPlayerState player, params string[] cardIds)
    {
        player.Combat.Deck.Restore(new(
            cardIds.Select(id => new CombatCardInstance(Guid.NewGuid(), id)).ToArray(),
            Enumerable.Range(0, 20).Select(_ => new CombatCardInstance(Guid.NewGuid(), "common-01")).ToArray(),
            [],
            0));
    }
}
