using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class ExplorationInventoryTests
{
    [Fact]
    public void Resource_items_stack_but_equipment_uses_one_slot_each()
    {
        var inventory = new ExplorationInventory(20, 0);

        Assert.True(inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 10)));
        Assert.True(inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 5)));
        Assert.True(inventory.TryAdd(new ExplorationItem("equipment-1", ExplorationItemKind.Equipment)));

        Assert.Equal(2, inventory.Items.Count);
        Assert.Equal(15, inventory.Items.Single(item => item.ItemId == "gold").Quantity);
    }

    [Fact]
    public void Choice_replacement_is_pending_until_finalized_and_never_drops_the_old_item()
    {
        var inventory = new ExplorationInventory(20, 0);
        inventory.TryAdd(new ExplorationItem("old", ExplorationItemKind.Equipment));

        var pending = inventory.BeginChoiceReplacement("old", new ExplorationItem("new", ExplorationItemKind.Equipment));

        Assert.Equal("new", Assert.Single(inventory.Items).ItemId);
        Assert.Equal("old", inventory.FinalizeChoiceReplacement(pending.Token).ItemId);
        Assert.Null(inventory.PendingReplacement);
    }

    [Fact]
    public void Safe_slots_are_limited_to_the_selected_package()
    {
        var inventory = new ExplorationInventory(28, 1);
        inventory.TryAdd(new ExplorationItem("potion", ExplorationItemKind.HealthPotion));
        inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 5));

        Assert.True(inventory.TrySetSafe("potion", true));
        Assert.False(inventory.TrySetSafe("gold", true));
    }

    [Fact]
    public void Health_potions_use_one_slot_per_bottle()
    {
        var inventory = new ExplorationInventory(20, 0);

        Assert.True(inventory.TryAdd(new ExplorationItem("health_potion:1", ExplorationItemKind.HealthPotion)));
        Assert.True(inventory.TryAdd(new ExplorationItem("health_potion:2", ExplorationItemKind.HealthPotion)));

        Assert.Equal(2, inventory.Items.Count);
    }
}
