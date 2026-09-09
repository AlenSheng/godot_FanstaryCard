using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RelicPileTests
{
    [Fact]
    public void Taking_from_full_inventory_requires_putting_an_item_back_into_the_same_pile()
    {
        var inventory = new ExplorationInventory(20, 0);
        inventory.TryAdd(new ExplorationItem("old", ExplorationItemKind.Equipment));
        var pile = new RelicPile(Guid.NewGuid(), "victim", new MapPosition(1, 1));
        pile.Add(new ExplorationItem("new", ExplorationItemKind.Equipment));
        var version = pile.Version;

        Assert.True(pile.TakeToInventory(inventory, "new", version, "old"));
        Assert.Contains(inventory.Items, item => item.ItemId == "new");
        Assert.Contains(pile.Items, item => item.ItemId == "old");
    }

    [Fact]
    public void Stale_pile_version_cannot_take_an_item()
    {
        var pile = new RelicPile(Guid.NewGuid(), "victim", new MapPosition(1, 1));
        pile.Add(new ExplorationItem("gold", ExplorationItemKind.Gold, 10));

        Assert.Throws<InvalidOperationException>(() => pile.TryTake("gold", pile.Version - 1, out _));
    }

    [Fact]
    public void Resources_stack_when_retrieved_without_consuming_a_slot()
    {
        var inventory = new ExplorationInventory(20, 0);
        inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 5));
        var pile = new RelicPile(Guid.NewGuid(), "victim", new MapPosition(1, 1));
        pile.Add(new ExplorationItem("gold", ExplorationItemKind.Gold, 7));

        Assert.True(pile.TakeToInventory(inventory, "gold", pile.Version));
        Assert.Equal(12, Assert.Single(inventory.Items).Quantity);
    }
}
