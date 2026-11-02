using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonEquipmentRuntimeTests
{
    private const string Stats="season-equipment-v1";
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];

    [Fact]
    public void PublishedRoomDerivesNewStatsFromActualArmorAndRejectsChangedSavedAttributes()
    {
        var catalog=CombatCardCatalog.Create(GameConfigCatalog.Current);var room=Room(catalog);var id=Guid.NewGuid();
        var armor=Armor();var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,WornArmor:armor));
        Assert.Equal(2.6,player.Combat.NaturalDrawIntervalSeconds,8);Assert.Equal(Stats,player.Combat.Equipment.StatsVersion);
        var saved=room.Capture();Assert.Equivalent(saved,BattleRoom.Restore(saved,catalog,73).Capture(),strict:true);
        var invalid=saved with {Players=saved.Players.Select(p=>p with {Combat=p.Combat with
            {Equipment=p.Combat.Equipment! with {DrawIntervalModifier=-.8}}}).ToArray()};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(invalid,catalog,73));
        Assert.Throws<DomainValidationException>(()=>new BattleRoom(Guid.NewGuid(),GameConfigCatalog.Current.Version,catalog,73,
            season:new("runtime",5,"season-v1",GameConfigCatalog.Current.Version,"unknown-stats")));
    }

    [Fact]
    public void ActualInventorySwapUsesTheSameVersionAndPreservesUniqueDataAndEmptyLoadoutPolicy()
    {
        var room=Room(CombatCardCatalog.Create(GameConfigCatalog.Current));var id=Guid.NewGuid();
        var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,WornArmor:Armor()));
        var red=new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Head","Red","Fire","Piercing","DrawInterval",5,UniqueAffix:"RapidDraw",StatsVersion:Stats),IsGenerated:false);
        Assert.True(player.Inventory.TryAdd(red));room.EquipInventoryItem(id,red.ItemId);
        Assert.Equal(2.12,player.Combat.NaturalDrawIntervalSeconds,8); // red+5 with four purple+0 and the 4-point unique reduction
        Assert.Equal("RapidDraw",player.WornArmor.Single(item=>item.ItemId==red.ItemId).Equipment!.UniqueAffix);
        foreach(var slot in Slots)room.UnequipArmor(id,slot);
        Assert.Equal(4,player.Combat.NaturalDrawIntervalSeconds,8);Assert.Equal(Stats,player.Combat.Equipment.StatsVersion);
        Assert.Equivalent(room.Capture(),BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(GameConfigCatalog.Current),73).Capture(),strict:true);
    }

    private static BattleRoom Room(CombatCardCatalog catalog)=>new(Guid.NewGuid(),GameConfigCatalog.Current.Version,catalog,73,
        season:new SeasonContext("runtime",5,"season-v1",GameConfigCatalog.Current.Version,Stats));
    private static ExplorationItem[] Armor()=>Slots.Select(slot=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
        Equipment:new(slot,"Purple","Fire",null,"DrawInterval",StatsVersion:Stats),IsGenerated:false)).ToArray();

    [Fact]
    public void InitialArmorAndInventorySwapRejectADifferentItemStatsVersionWithoutChangingState()
    {
        var room=Room(CombatCardCatalog.Create(GameConfigCatalog.Current));var id=Guid.NewGuid();
        var foreign=Armor()[0];foreign=foreign with {Equipment=foreign.Equipment! with {StatsVersion="foreign-stats"}};
        Assert.Throws<DomainValidationException>(()=>room.AddPlayer(new(id,HeroClass.Mage,
            SeasonFenxianTests.Starter(HeroClass.Mage),null,WornArmor:[foreign])));
        var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,WornArmor:Armor()));
        Assert.True(player.Inventory.TryAdd(foreign));var before=room.Capture();
        Assert.Throws<DomainValidationException>(()=>room.EquipInventoryItem(id,foreign.ItemId));
        Assert.Equivalent(before,room.Capture(),strict:true);
    }

    [Fact]
    public void LegacyInfernoMayKeepItsHistoricalDifferentElementThroughUnequipAndReequip()
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var id=Guid.NewGuid();var itemId=Guid.NewGuid();
        var item=new ExplorationItem(itemId.ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Head","Red","Fire","Piercing","DrawInterval",UniqueAffix:"Inferno",UniqueElement:"Water"),IsGenerated:false);
        Assert.True(EquipmentRewardRules.IsValid(item.Equipment!));
        var legacy=EquipmentCombatRules.Calculate([new(itemId,"Head","Red",0,CardElement.Fire,"Piercing","DrawInterval","Inferno",CardElement.Water)],config);
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73);
        var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,WornArmor:[item],Equipment:legacy));
        room.UnequipArmor(id,"Head");room.EquipInventoryItem(id,item.ItemId);
        Assert.Equal(.35,player.Combat.Equipment.DamageBonus(CardElement.Water),8);
        Assert.Equal(.32,player.Combat.Equipment.DamageBonus(CardElement.Fire),8);
    }
}
