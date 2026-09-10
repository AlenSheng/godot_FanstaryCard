using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class SettlementAssetClassifierTests
{
    [Fact]
    public void Death_returns_safe_items_but_moves_unsafe_items_and_armor_to_the_relic_pile()
    {
        var inventory = new ExplorationInventory(28, 1);
        inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 10, true));
        inventory.TryAdd(new ExplorationItem("potion:1", ExplorationItemKind.HealthPotion));
        var armor = new SettlementAsset("Equipment", "armor-1", false);
        var weapon = new SettlementAsset("ClassWeapon", "mage-weapon", false);

        var result = SettlementAssetClassifier.ClassifyDeath(inventory.Items, [armor], weapon);

        Assert.Contains(result.ReturnToPlayer, item => item.AssetId == "gold");
        Assert.Contains(result.ToRelicPile, item => item.AssetId == "potion:1");
        Assert.Contains(result.ToRelicPile, item => item.AssetId == "armor-1");
        Assert.DoesNotContain(result.ToRelicPile, item => item.AssetId == "mage-weapon");
        Assert.Contains(result.ExcludedFromRelicPile, item => item.AssetId == "mage-weapon");
    }

    [Fact]
    public void Generated_equipment_metadata_survives_settlement_classification()
    {
        var data = new EquipmentRewardData("Feet", "Orange", "Fire", "Piercing", "ForcedEscape");
        var inventory = new ExplorationInventory(20, 0);
        inventory.TryAdd(new ExplorationItem(
            Guid.NewGuid().ToString("D"),
            ExplorationItemKind.Equipment,
            Equipment: data));

        var result = SettlementAssetClassifier.ClassifyDeath(
            inventory.Items,
            [],
            new SettlementAsset("ClassWeapon", "mage-weapon", false));

        Assert.Equal(data, Assert.Single(result.ToRelicPile).Equipment);
    }
}
