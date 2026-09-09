using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Settlement;

public sealed class SettlementMaterialMappingTests
{
    [Theory]
    [InlineData(HeroClass.Priest, "priest_soul")]
    [InlineData(HeroClass.Mage, "mage_soul")]
    [InlineData(HeroClass.Guardian, "guardian_soul")]
    public void Actual_pve_drop_and_legacy_identifier_map_to_same_class_account(HeroClass heroClass, string column)
    {
        var catalog = new CombatCardCatalog([new("hit", new CombatCardEffect(DirectDamage: 10000))]);
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 7);
        var id = Guid.NewGuid();
        var player = room.AddPlayer(new(id, heroClass, Enumerable.Repeat("hit", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(7, 1));
        foreach (var monster in player.Pve!.Monsters)
            room.PlayCards(id, player.Pve.BattleId, monster.MonsterId,
                [player.Combat.Deck.Hand[0].InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
        var soul = Assert.Single(player.Inventory.Items, item => item.Kind == ExplorationItemKind.ClassSoul);
        var asset = new SettlementAsset(soul.Kind.ToString(), soul.ItemId, soul.IsSafe, soul.Quantity);
        Assert.Equal(column, SettlementMaterialMapping.GetColumn(asset));
        Assert.Equal(column, SettlementMaterialMapping.GetColumn(asset with { AssetId = $"{heroClass}Soul" }));
        Assert.Equal(1, asset.Quantity);
    }

    [Fact]
    public void Unknown_class_assets_do_not_guess_an_account()
    {
        Assert.Null(SettlementMaterialMapping.GetColumn(new("ClassSoul", "class_soul:Unknown", false)));
        Assert.Null(SettlementMaterialMapping.GetColumn(new("ClassSoul", "mage_soul; DROP TABLE players", false)));
        Assert.Null(SettlementMaterialMapping.GetColumn(new("Equipment", "MageSoul", false)));
    }
}
