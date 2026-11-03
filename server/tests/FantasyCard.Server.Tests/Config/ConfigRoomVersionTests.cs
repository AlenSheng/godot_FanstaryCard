using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Config;

public sealed class ConfigRoomVersionTests
{
    [Theory]
    [InlineData(false,172,21)]
    [InlineData(true,345,22)]
    public void ActualResolverAndSnapshotUseTheSelectedCardGrowthAndBackpack(bool alternate,int damage,int capacity)
    {
        var fixture = PublishedConfigTestInputs.Create("room-control-"+alternate,alternate);
        var playerId = Guid.NewGuid();
        var room = PublishedConfigTestInputs.WithTarget(PublishedConfigTestInputs.Room(fixture.Catalog,playerId),fixture.Catalog);
        var player = room.GetPlayer(playerId); PublishedConfigTestInputs.PutC01InHand(player);
        var restored = BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(fixture.Catalog),73);
        player = restored.GetPlayer(playerId);
        Assert.Equal(capacity,player.Inventory.Capacity);
        restored.PlayCards(playerId,player.Pve!.BattleId,"fire-bat",player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(),
            restored.Revision,DateTimeOffset.UnixEpoch,restored.NewCombatActionId(playerId));
        // GDD 5.13.0: fire bat has 15% same-element resistance; floor(203*.85)=172, floor(407*.85)=345.
        Assert.Equal(1000-damage,Assert.Single(player.Pve.Monsters).Hp);
        Assert.Equal(70,player.Combat.MaximumHp);
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(GameConfigCatalog.Current),73));
    }

    [Theory]
    [InlineData(false,.13,28)]
    [InlineData(true,.27,42)]
    public void EquipmentPotionAndRelicInventoryStagingRetainTheRoomCatalog(bool alternate,double bonus,int heal)
    {
        var fixture = PublishedConfigTestInputs.Create("inventory-control-"+alternate,alternate);
        var playerId = Guid.NewGuid();var room = PublishedConfigTestInputs.Room(fixture.Catalog,playerId);
        var player = room.GetPlayer(playerId);
        var item = new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Head","White","Fire",null,"DrawInterval"));
        Assert.True(player.Inventory.TryAdd(item));room.EquipInventoryItem(playerId,item.ItemId);
        Assert.Equal(bonus,player.Combat.Equipment.Elements.FireDamageBonus,8);
        room.UnequipArmor(playerId,"Head");Assert.True(player.Inventory.TryRemove(item.ItemId,out _));
        var relic = new RelicPile(Guid.NewGuid(),"victim",new(0,0));relic.Add(item);
        Assert.True(relic.TakeToInventory(player.Inventory,item.ItemId,relic.Version));
        room.EquipInventoryItem(playerId,item.ItemId);
        Assert.Equal(bonus,player.Combat.Equipment.Elements.FireDamageBonus,8);
        player.Combat.TakeDamage(50);
        Assert.True(player.Inventory.TryAdd(new("potion-control",ExplorationItemKind.HealthPotion)));
        Assert.Equal(heal,room.UsePotion(playerId).Healed);
        Assert.Equal(20+heal,player.Combat.Hp);
        var restored = BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(fixture.Catalog),73);
        restored.UnequipArmor(playerId,"Head");
        Assert.Contains(restored.GetPlayer(playerId).Inventory.Items,i => i.ItemId == item.ItemId);
    }

    [Theory]
    [InlineData(false,9,7,"White")]
    [InlineData(true,11,11,"Green")]
    public void LegacyPendingChoiceRefreshAndItsPriceUseTheRestoredRoomCatalog(bool alternate,int fragments,int cost,string quality)
    {
        var fixture = PublishedConfigTestInputs.Create("reward-control-"+alternate,alternate);
        var playerId = Guid.NewGuid();var room = PublishedConfigTestInputs.Room(fixture.Catalog,playerId,legacy:true);
        var choice = RewardChoiceState.Create(ChaosMapLayer.Outer,new Random(73),configuration:fixture.Catalog);
        var before = room.Capture();
        var restored = BattleRoom.Restore(before with { Players = before.Players.Select(p => p with
            { Phase = RoomPlayerPhase.Choice,RewardChoice = choice.Capture() }).ToArray() },CombatCardCatalog.Create(fixture.Catalog),73);
        Assert.True(restored.GetPlayer(playerId).Inventory.TryAdd(new("gold",ExplorationItemKind.Gold,100)));
        for (var index = 1; index <= 2; index++)
        {
            var receipt = restored.RefreshRewardChoice(playerId,restored.Revision,requestId:"refresh-"+index);
            Assert.Equal(fragments,receipt.Choice.Options.Single(o => o.Kind == RewardChoiceKind.EquipmentFragments).Item!.Quantity);
            Assert.Equal(quality,receipt.Choice.Options.Single(o => o.Kind == RewardChoiceKind.Equipment).Item!.Equipment!.Quality);
            Assert.Equal(100-index*cost,restored.GetPlayer(playerId).Inventory.GoldQuantity);
            restored = BattleRoom.Restore(restored.Capture(),CombatCardCatalog.Create(fixture.Catalog),73);
        }
    }

    [Theory]
    [InlineData(false,36,7,"Blue")]
    [InlineData(true,44,11,"Purple")]
    public void SeasonalPendingChoiceRefreshUsesTheOriginalMatrixScaleAndPrice(bool alternate,int fragments,int cost,string quality)
    {
        var fixture=PublishedConfigTestInputs.Create("season-reward-control-"+alternate,alternate,seasonalLootControl:true);
        var playerId=Guid.NewGuid();var room=PublishedConfigTestInputs.Room(fixture.Catalog,playerId,withMap:true);
        var before=room.Capture();var context=before.Season!;var position=before.Players[0].Position!.Value;
        var choice=RewardChoiceState.Create(ChaosMapLayer.Outer,new Random(73),configuration:fixture.Catalog,season:new(context,SeasonRewardBias.None));
        var map=before.Map! with {Cells=before.Map!.Cells.Select(cell=>cell.Position==position?cell with {IsBoss=false,MonsterGroupId="O1",TreasureElement=null}:cell).ToArray()};
        before=before with {Map=map,Players=before.Players.Select(player=>player with {Phase=RoomPlayerPhase.Choice,Pve=null,
            Combat=player.Combat with {Hp=42},RewardChoice=choice.Capture()}).ToArray()};
        var restored=BattleRoom.Restore(before,CombatCardCatalog.Create(fixture.Catalog),73);
        Assert.True(restored.GetPlayer(playerId).Inventory.TryAdd(new("gold",ExplorationItemKind.Gold,100)));
        for(var index=1;index<=2;index++)
        {
            var receipt=restored.RefreshRewardChoice(playerId,restored.Revision,requestId:"season-refresh-"+index);
            Assert.Equal(fragments,receipt.Choice.Options[1].Item!.Quantity);
            var item=receipt.Choice.Options[0].Item!.Equipment!;
            Assert.Equal(quality,item.Quality);Assert.Equal(context,item.SeasonOrigin!.Season);
            Assert.Equal(100-index*cost,restored.GetPlayer(playerId).Inventory.GoldQuantity);
            restored=BattleRoom.Restore(restored.Capture(),CombatCardCatalog.Create(fixture.Catalog),73);
        }
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(before,CombatCardCatalog.Create(GameConfigCatalog.Current),73));
    }

    [Theory]
    [InlineData(false,71,9)]
    [InlineData(true,91,11)]
    public void ControlledFullHealthKillAwardsTheSelectedLootAndRealMonsterCard(bool alternate,int gold,int fragments)
    {
        var fixture = PublishedConfigTestInputs.Create("kill-control-"+alternate,alternate);
        var playerId = Guid.NewGuid();
        // A declared one-cell consumer fixture: legal 20-card pool, full-health 78 HP fire bat, no balance claim.
        var room = PublishedConfigTestInputs.WithTarget(PublishedConfigTestInputs.Room(fixture.Catalog,playerId,withMap:true),fixture.Catalog,78);
        var player = room.GetPlayer(playerId);PublishedConfigTestInputs.PutC01InHand(player);
        room.PlayCards(playerId,player.Pve!.BattleId,"fire-bat",player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(),
            room.Revision,DateTimeOffset.UnixEpoch,room.NewCombatActionId(playerId));
        Assert.Equal(RoomPlayerPhase.Choice,player.Phase);
        // The fixture uses D5: base integers receive2.2x gold and4x fragments.
        Assert.Equal(gold*22000/10000,player.Inventory.GoldQuantity);
        Assert.Equal(fragments*40000/10000,player.Inventory.Items.Single(i => i.Kind == ExplorationItemKind.EquipmentFragments).Quantity);
        var deck = player.Combat.Deck.Capture();var pool = deck.Hand.Concat(deck.Library).Concat(deck.Discard).ToArray();
        Assert.Equal(21,pool.Length);
        Assert.Single(pool,c => fixture.Catalog.Cards.Single(d => d.CardId == c.CardId).MonsterType == "FireBat");
    }

    [Fact]
    public void ArchiveProviderValidatesIdentityAndKeepsAlreadyLoadedVersionsImmutable()
    {
        var active = GameConfigCatalog.Current;
        using var archive = new ConfigArchiveDirectory();
        var old = PublishedConfigTestInputs.Create("archive-a");
        var next = PublishedConfigTestInputs.Create("archive-b",true);
        PublishedConfigTestInputs.Store(archive.Root,old.Catalog.Version,old.Bytes,old.Hash);
        PublishedConfigTestInputs.Store(archive.Root,next.Catalog.Version,next.Bytes,next.Hash);
        var catalogs = new PublishedConfigCatalogs(next.Catalog,archive.Root);
        var loaded = catalogs.Resolve(old.Catalog.Version);
        Assert.Equal(old.Hash,loaded.ContentHash);
        PublishedConfigTestInputs.Store(archive.Root,old.Catalog.Version,next.Bytes,next.Hash);
        Assert.Same(loaded,catalogs.Resolve(old.Catalog.Version));
        Assert.Throws<InvalidDataException>(() => new PublishedConfigCatalogs(next.Catalog,archive.Root).Resolve(old.Catalog.Version));
        Assert.Throws<DirectoryNotFoundException>(() => catalogs.Resolve("missing-version"));
        Assert.Throws<InvalidDataException>(() => catalogs.Resolve("../escape"));
        Assert.Same(active,GameConfigCatalog.Current);
    }
}
