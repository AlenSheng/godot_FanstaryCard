using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Bots;

public sealed class SeasonBotRewardTests
{
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];
    private static readonly Guid Human=Guid.Parse("10000000-0000-4000-8000-000000000001");
    private static readonly Guid Other=Guid.Parse("10000000-0000-4000-8000-000000000002");
    private static readonly Guid Bot=Guid.Parse("20000000-0000-4000-8000-000000000001");
    private static readonly Guid SecondBot=Guid.Parse("20000000-0000-4000-8000-000000000002");

    [Theory]
    [InlineData(true)] [InlineData(false)]
    public void ActualHumanKillAwardsOnlyTheSeparateBudgetAndNeverTheFiveProjectedPieces(bool equipmentRoll)
    {
        var room=ReadyRoom(Seed(equipmentRoll));var bot=room.GetPlayer(Bot);
        Assert.Equal(5,bot.WornArmor.Count);Assert.All(bot.WornArmor,item=>Assert.True(item.IsCombatProjection));
        Assert.Empty(bot.BotLoot);
        Assert.True(bot.Inventory.TryAdd(new("projected-potion",ExplorationItemKind.HealthPotion,IsCombatProjection:true)));
        Kill(room,Human,Bot);
        var winner=room.GetPlayer(Human);var receipt=Assert.IsType<BotVictoryRewardReceipt>(winner.BotVictoryReward);
        Assert.Equal(5,winner.Inventory.GoldQuantity);
        Assert.Equal(1,winner.Inventory.Items.Single(item=>item.Kind==ExplorationItemKind.EquipmentFragments).Quantity);
        Assert.Equal(equipmentRoll,receipt.Equipment is not null);
        if(receipt.Equipment is { } item)
        {
            Assert.Equal("Blue",item.Equipment!.Quality);Assert.Equal(0,item.Equipment.Level);
            Assert.Equal("BotVictory",item.Equipment.SeasonOrigin!.Source);Assert.Equal(Human,item.Equipment.SeasonOrigin.BotRewardOwnerId);
        }
        Assert.DoesNotContain(room.Capture().RelicPiles!,pile=>pile.VictimId==Bot.ToString("D"));
        Assert.Empty(bot.Inventory.Items);Assert.Empty(bot.WornArmor);
        Assert.Equivalent(room.Capture(),Restore(room).Capture(),strict:true);
    }

    [Fact]
    public void TheSameHumanCannotRerollAfterRecoveryOrASecondBotWhileAnotherHumanHasItsOwnBudget()
    {
        var room=ReadyRoom(Seed(true));Kill(room,Human,Bot);var first=room.GetPlayer(Human).BotVictoryReward;
        room=Restore(room);var duel=room.StartDuel(Human,SecondBot,DateTimeOffset.UnixEpoch);
        room.EndDuelWithDeath(duel.DuelId,SecondBot);
        Assert.Equal(first,room.GetPlayer(Human).BotVictoryReward);Assert.Equal(5,room.GetPlayer(Human).Inventory.GoldQuantity);
        Assert.Null(room.GetPlayer(Other).BotVictoryReward);
        var independent=ReadyRoom(Seed(false));Kill(independent,Human,Bot);Kill(independent,Other,SecondBot);
        Assert.Equal(5,independent.GetPlayer(Human).Inventory.GoldQuantity);Assert.Equal(5,independent.GetPlayer(Other).Inventory.GoldQuantity);
    }

    [Fact]
    public void ARealBoundPlusFiveItemPassesThroughTheBotWithItsOriginalIdentityAndNoProjectionCopy()
    {
        var real=new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Head","Orange","Water","Vitality","DrawInterval",5,true,StatsVersion:"season-equipment-v1"),IsGenerated:false);
        var room=ReadyRoom(Seed(false),real);
        var first=room.StartDuel(Bot,Other,DateTimeOffset.UnixEpoch);room.EndDuelWithDeath(first.DuelId,Other);
        var humanPile=Assert.Single(room.Capture().RelicPiles!);
        room.TakeRelicItem(Bot,humanPile.PileId,real.ItemId,humanPile.Version);
        Assert.Contains(room.GetPlayer(Bot).Inventory.Items,item=>item.ItemId==real.ItemId && item.Equipment==real.Equipment && !item.IsCombatProjection);
        Kill(room,Human,Bot);
        var botPile=Assert.Single(room.Capture().RelicPiles!);var recovered=Assert.Single(botPile.Items);
        Assert.Equal(real.ItemId,recovered.ItemId);Assert.Equal(real.Equipment,recovered.Equipment);Assert.Equal(false,recovered.IsGenerated);
        room.TakeRelicItem(Human,botPile.PileId,real.ItemId,botPile.Version);
        Assert.Contains(room.GetPlayer(Human).Inventory.Items,item=>item.ItemId==real.ItemId && item.Equipment!.Level==5 && item.Equipment.IsBound);
        Assert.Equivalent(room.Capture(),Restore(room).Capture(),strict:true);
    }

    [Theory]
    [InlineData(true)] [InlineData(false)]
    public void ScriptedBotPveCanDieOrClearWithoutManufacturingNormalChoiceResources(bool lowHp)
    {
        var room=Create(73);room.InitializeMap(ChaosMapGenerator.Generate(73,4));var bot=room.GetPlayer(Bot);
        if(lowHp)bot.Combat.TakeDamage(bot.Combat.Hp+bot.Combat.Shield-1);
        room.Advance(TimeSpan.FromSeconds(90),DateTimeOffset.UnixEpoch.AddSeconds(90));
        Assert.Null(bot.RewardChoice);Assert.Empty(bot.BotLoot);
        Assert.DoesNotContain(bot.Inventory.Items,item=>!item.IsCombatProjection);
        Assert.Equal(lowHp?RoomPlayerPhase.Dead:RoomPlayerPhase.ActionBar,bot.Phase);
        if(lowHp)Assert.Empty(bot.WornArmor);
        Assert.DoesNotContain(room.Capture().RelicPiles!,pile=>pile.VictimId==Bot.ToString("D"));
    }

    [Fact]
    public void BotVersusBotUsesActualCardsAndCanKillBeforeTheLegacyTimer()
    {
        var room=ReadyRoom(73);var duel=room.StartDuel(Bot,SecondBot,DateTimeOffset.UnixEpoch);
        var victim=room.GetPlayer(SecondBot);victim.Combat.TakeDamage(victim.Combat.Hp+victim.Combat.Shield-1);
        SeasonFenxianTests.SetHand(room.GetPlayer(Bot),"C01");
        room.Advance(TimeSpan.FromMilliseconds(100),DateTimeOffset.UnixEpoch.AddMilliseconds(100));
        Assert.Equal(RoomPlayerPhase.Dead,victim.Phase);Assert.Empty(room.Capture().Duels);
        Assert.Null(room.GetPlayer(Bot).BotVictoryReward);
        Assert.NotEmpty(room.DrainCombatFeedback());
    }

    [Fact]
    public void VictoryRewardAdvancesOnlyItsSeparateRandomStream()
    {
        var room=ReadyRoom(Seed(true));var duel=room.StartDuel(Human,Bot,DateTimeOffset.UnixEpoch);
        var before=room.Capture().RandomStreams!;room.EndDuelWithDeath(duel.DuelId,Bot);var after=room.Capture().RandomStreams!;
        Assert.NotEqual(before.BotReward,after.BotReward);
        Assert.Equal(before with {BotReward=after.BotReward},after);
    }

    [Fact]
    public void BotRetreatLeavesTransferredRealGearRecoverableAndDoesNotAwardAVictory()
    {
        var real=new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Head","Orange","Water","Vitality","DrawInterval",5,true,StatsVersion:"season-equipment-v1"),IsGenerated:false);
        var room=ReadyRoom(73,real);var duel=room.StartDuel(Bot,Other,DateTimeOffset.UnixEpoch);
        room.EndDuelWithDeath(duel.DuelId,Other);var pile=Assert.Single(room.Capture().RelicPiles!);
        room.TakeRelicItem(Bot,pile.PileId,real.ItemId,pile.Version);
        var snapshot=room.Capture();var boss=snapshot.Map!.Cells.Single(cell=>cell.IsBoss).Position;
        snapshot=snapshot with {Players=snapshot.Players.Select(player=>player.PlayerId==Human || player.PlayerId==Bot
            ?player with {Position=boss,Phase=RoomPlayerPhase.ActionBar,Pve=null,BotPveRemaining=null}:player).ToArray()};
        room=BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73);
        room.RequestExtraction(Bot);room.Advance(TimeSpan.FromSeconds(90),DateTimeOffset.UnixEpoch.AddSeconds(90));
        Assert.Equal(RoomPlayerPhase.Extracted,room.GetPlayer(Bot).Phase);
        var left=Assert.Single(room.Capture().RelicPiles!);Assert.Equal(real.ItemId,Assert.Single(left.Items).ItemId);
        room.TakeRelicItem(Human,left.PileId,real.ItemId,left.Version);
        Assert.Contains(room.GetPlayer(Human).Inventory.Items,item=>item.ItemId==real.ItemId && item.Equipment==real.Equipment);
        Assert.Null(room.GetPlayer(Human).BotVictoryReward);
    }

    [Theory]
    [InlineData("rng")] [InlineData("human-projection")] [InlineData("pile-projection")] [InlineData("stripped-flag")]
    public void RecoveryRejectsProjectionLeaksAndMissingRewardState(string mutation)
    {
        var room=ReadyRoom(73);var snapshot=room.Capture();var projection=room.GetPlayer(Bot).WornArmor[0];
        switch(mutation)
        {
            case "rng":snapshot=snapshot with {RandomStreams=snapshot.RandomStreams! with {BotReward=null}};break;
            case "human-projection":snapshot=snapshot with {Players=snapshot.Players.Select(player=>player.PlayerId==Human?player with
                {Inventory=player.Inventory! with {Items=[projection with {SlotIndex=0}]}}:player).ToArray()};break;
            case "pile-projection":snapshot=snapshot with {RelicPiles=[new(Guid.NewGuid(),Bot.ToString("D"),room.GetPlayer(Bot).Position!.Value,1,[projection])]};break;
            default:snapshot=snapshot with {Players=snapshot.Players.Select(player=>player.PlayerId==Bot?player with
                {WornArmor=player.WornArmor!.Select(item=>item with {IsCombatProjection=false}).ToArray()}:player).ToArray()};break;
        }
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73));
    }

    [Fact]
    public void FullInventoryConsumesTheBudgetWithoutRerollAndRecordsEquipmentRecycling()
    {
        var room=ReadyRoom(Seed(true));var player=room.GetPlayer(Human);
        for(var i=0;i<player.Inventory.Capacity;i++)Assert.True(player.Inventory.TryAdd(new("held-"+i,ExplorationItemKind.HealthPotion)));
        Kill(room,Human,Bot);var receipt=Assert.IsType<BotVictoryRewardReceipt>(player.BotVictoryReward);
        Assert.False(receipt.GoldRetained);Assert.False(receipt.FragmentsRetained);Assert.False(receipt.EquipmentRetained);
        Assert.NotNull(receipt.Equipment);Assert.Single(room.CapturePlayer(Human).RecycledEquipment!);
        Assert.Equivalent(room.Capture(),Restore(room).Capture(),strict:true);
    }

    private static BattleRoom Restore(BattleRoom room) => BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(GameConfigCatalog.Current),73);
    private static int Seed(bool equipment)
    {
        for(var seed=0;seed<100;seed++)if((new CombatRandom(unchecked(seed^0x42525744)).Next(10000)<1000)==equipment)return seed;
        throw new InvalidOperationException("Deterministic bot reward observation seed unavailable.");
    }
    private static BattleRoom ReadyRoom(int seed,ExplorationItem? real=null)
    {
        var room=Create(seed,real);room.InitializeMap(ChaosMapGenerator.Generate(seed,4));var snapshot=room.Capture();var position=snapshot.Map!.SpawnPositions[0];
        snapshot=snapshot with {Players=snapshot.Players.Select(player=>player with {Phase=RoomPlayerPhase.ActionBar,Pve=null,Position=position,BotPveRemaining=null}).ToArray()};
        return BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),seed);
    }
    private static BattleRoom Create(int seed,ExplorationItem? real=null)
    {
        var config=GameConfigCatalog.Current;Assert.NotNull(config.SeasonBotRewards);
        var season=new SeasonContext("bot-controls",5,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),seed,season:season);
        room.AddPlayer(new(Human,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        room.AddPlayer(new(Other,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,WornArmor:real is null?[]:[real]));
        foreach(var id in new[]{Bot,SecondBot})
        {
            var armor=Slots.Select((slot,index)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
                Equipment:new(slot,index==0?"Orange":"Purple","Fire","Piercing","DrawInterval",5,StatsVersion:season.StatsVersion),IsGenerated:false)).ToArray();
            room.AddPlayer(new(id,HeroClass.Guardian,SeasonFenxianTests.Starter(HeroClass.Guardian),null,WornArmor:armor,IsBot:true));
        }
        return room;
    }
    private static void Kill(BattleRoom room,Guid human,Guid bot)
    {
        var duel=room.StartDuel(human,bot,DateTimeOffset.UnixEpoch.Add(room.Elapsed));var victim=room.GetPlayer(bot);
        victim.Combat.TakeDamage(victim.Combat.Hp+victim.Combat.Shield-1);SeasonFenxianTests.SetHand(room.GetPlayer(human),"C01");
        room.PlayCards(human,duel.DuelId,bot.ToString("D"),[room.GetPlayer(human).Combat.Deck.Hand[0].InstanceId],room.Revision,
            DateTimeOffset.UnixEpoch.Add(room.Elapsed),room.NewCombatActionId(human));
        Assert.Equal(RoomPlayerPhase.Dead,victim.Phase);
    }
}
