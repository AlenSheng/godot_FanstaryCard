using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class SeasonRedRewardTests
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web);
    [Theory]
    [InlineData(0,false)] [InlineData(1,false)] [InlineData(2,true)]
    [InlineData(3,true)] [InlineData(4,true)] [InlineData(5,true)]
    public void CoreBossUsesAnIndependentRollOnlyAfterTheEligibleTerminalKill(int difficulty,bool eligible)
    {
        var (room,id)=BossRoom(difficulty);var before=room.Capture();Kill(room,id);
        var after=room.Capture();var player=after.Players.Single();
        Assert.Equal(eligible,player.PendingRedEvaluation is not null);
        if(eligible)
        {
            var random=new CombatRandom(0);random.Restore(before.RandomStreams!.Red!.Value);
            Assert.Equal(random.Next(10000),player.PendingRedEvaluation!.Roll);
            Assert.Equal(random.Next(),player.PendingRedEvaluation.EquipmentSeed);
            Assert.Equal(random.State,after.RandomStreams!.Red);
            Assert.Equal(TimeSpan.Zero,player.PendingRedEvaluation.OccurredAt.Offset);
        }
        else Assert.Equal(before.RandomStreams!.Red,after.RandomStreams!.Red);
        var restored=BattleRoom.Restore(after,CombatCardCatalog.Create(GameConfigCatalog.Current),73);
        Assert.Equivalent(after,restored.Capture(),strict:true);
    }

    [Theory]
    [InlineData(0,true)] [InlineData(39,true)] [InlineData(40,false)] [InlineData(9999,false)]
    public void BossProbabilityHasExactlyFortyWinningBasisPointsAndNoOrdinaryOrDisabledChestPath(int roll,bool hit)
    {
        var policy=GameConfigCatalog.Current.SeasonRed!;policy.Validate();
        Assert.Equal(hit,policy.Hits("ChaosBoss",2,roll));
        Assert.False(policy.Hits("ChaosBoss",1,roll));Assert.False(policy.Hits("ShopChest",2,roll));
        Assert.False(policy.Hits("Activity",2,roll));
        Assert.Throws<DomainValidationException>(()=>policy.Hits("OrdinaryChoice",2,roll));
    }

    [Fact]
    public void FullBagKeepsTheExactMintUntilExplicitReplacementAndThenTheNormalChoiceContinues()
    {
        var (room,id)=BossRoom(2);Kill(room,id);var player=room.GetPlayer(id);
        while(player.Inventory.FreeSlots>0)Assert.True(player.Inventory.TryAdd(new(Guid.NewGuid().ToString("D"),ExplorationItemKind.HealthPotion)));
        var pending=player.PendingRedEvaluation!;var item=Red();var receipt=new RedDropReceipt(pending.AttemptId,"Minted",item);
        Assert.Throws<DomainValidationException>(()=>room.RefreshRewardChoice(id,room.Revision));
        Assert.Throws<DomainValidationException>(()=>room.ClaimReward(id,player.RewardChoice!.Options[0].OptionId));
        room.ApplyRedDrop(id,receipt);room.ApplyRedDrop(id,receipt);
        Assert.Equal(item,player.PendingRedItem);Assert.DoesNotContain(player.Inventory.Items,value=>value.ItemId==item.ItemId);
        var snapshot=room.Capture();room=BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73);player=room.GetPlayer(id);
        Assert.Equal(item,player.PendingRedItem);
        Assert.Throws<DomainValidationException>(()=>room.ClaimReward(id,"red:"+item.ItemId));
        Assert.Throws<DomainValidationException>(()=>room.ClaimReward(id,"red:"+item.ItemId,equip:true));
        Assert.Throws<DomainValidationException>(()=>room.ClaimReward(id,"red:"+item.ItemId,"missing"));
        Assert.Equivalent(snapshot,room.Capture(),strict:true);
        var replaced=player.Inventory.Items[0];room.ClaimReward(id,"red:"+item.ItemId,replaced.ItemId);
        Assert.Null(player.PendingRedItem);Assert.Single(player.Inventory.Items,value=>value.ItemId==item.ItemId);
        Assert.DoesNotContain(player.Inventory.Items,value=>value.ItemId==replaced.ItemId);Assert.NotNull(player.RewardChoice);
        var healing=player.RewardChoice.Options.Single(option=>(int)option.Kind==3);
        room.ClaimReward(id,healing.OptionId);Assert.Equal(RoomPlayerPhase.ActionBar,player.Phase);
        Assert.Equal(receipt,player.RedReward);
    }

    [Theory]
    [InlineData("Miss")] [InlineData("Exhausted")] [InlineData("Closed")]
    public void NonMintedResultsAreDurableAndDoNotReroll(string status)
    {
        var (room,id)=BossRoom(2);Kill(room,id);var before=room.Capture().RandomStreams;
        var receipt=new RedDropReceipt(room.GetPlayer(id).PendingRedEvaluation!.AttemptId,status,null);
        room.ApplyRedDrop(id,receipt);room.ApplyRedDrop(id,receipt);
        Assert.Null(room.GetPlayer(id).PendingRedEvaluation);Assert.Equal(before,room.Capture().RandomStreams);
        Assert.Throws<DomainValidationException>(()=>room.ApplyRedDrop(id,receipt with {Status=status=="Miss"?"Closed":"Miss"}));
        Assert.Equivalent(room.Capture(),BattleRoom.Restore(room.Capture(),CombatCardCatalog.Create(GameConfigCatalog.Current),73).Capture(),strict:true);
    }

    [Fact]
    public void PendingOrReceiptTamperingCannotRestoreAsAnotherBossRollOrRealItem()
    {
        var (room,id)=BossRoom(2);Kill(room,id);var original=room.Capture();var player=original.Players.Single();
        foreach(var pending in new[]{player.PendingRedEvaluation! with {AttemptId=Guid.NewGuid()},player.PendingRedEvaluation! with {Roll=10000},
            player.PendingRedEvaluation! with {Source="ShopChest"},player.PendingRedEvaluation! with {EquipmentSeed=-1}})
            Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(original with {Players=[player with {PendingRedEvaluation=pending}]},CombatCardCatalog.Create(GameConfigCatalog.Current),73));
        room.ApplyRedDrop(id,new(player.PendingRedEvaluation!.AttemptId,"Minted",Red()));
        var minted=room.Capture();player=minted.Players.Single();
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(minted with {Players=[player with {RedReward=player.RedReward! with {Equipment=Red() with {IsGenerated=true}}}]},CombatCardCatalog.Create(GameConfigCatalog.Current),73));
    }

    [Fact]
    public void AFullBagRedWaitsThroughARealDuelAndReturnsToItsOriginalChoiceWithoutAnotherRoll()
    {
        var (room,id)=BossRoom(2);Kill(room,id);var player=room.GetPlayer(id);
        while(player.Inventory.FreeSlots>0)Assert.True(player.Inventory.TryAdd(new(Guid.NewGuid().ToString("D"),ExplorationItemKind.HealthPotion)));
        var item=Red();room.ApplyRedDrop(id,new(player.PendingRedEvaluation!.AttemptId,"Minted",item));
        var peer=Guid.NewGuid();room.AddPlayer(new(peer,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        var snapshot=room.Capture();snapshot=snapshot with {Players=snapshot.Players.Select(value=>value.PlayerId==peer
            ?value with {Position=player.Position,Phase=RoomPlayerPhase.ActionBar}:value).ToArray()};
        room=BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73);player=room.GetPlayer(id);
        var random=room.Capture().RandomStreams!.Red;
        var duel=room.StartDuel(id,peer,DateTimeOffset.UnixEpoch);
        Assert.Throws<DomainValidationException>(()=>room.ClaimReward(id,"red:"+item.ItemId,player.Inventory.Items[0].ItemId));
        room.Advance(TimeSpan.FromMilliseconds(500),DateTimeOffset.UnixEpoch);
        var victim=room.GetPlayer(peer);victim.Combat.TakeDamage(victim.Combat.Hp+victim.Combat.Shield-1);
        SeasonFenxianTests.SetHand(player,"C01");
        room.PlayCards(id,duel.DuelId,peer.ToString("D"),[player.Combat.Deck.Hand[0].InstanceId],room.Revision,DateTimeOffset.UnixEpoch,room.NewCombatActionId(id));
        Assert.Equal(RoomPlayerPhase.Choice,player.Phase);Assert.Equal(item,player.PendingRedItem);
        Assert.Equal(random,room.Capture().RandomStreams!.Red);
        room.ClaimReward(id,"red:"+item.ItemId,player.Inventory.Items[0].ItemId);
        Assert.Null(player.PendingRedItem);Assert.Single(player.Inventory.Items,value=>value.ItemId==item.ItemId);
    }

    [Fact]
    public void AReservedRealRedSurvivesDisconnectDeathAndAnotherHumansRelicPickup()
    {
        var (room,id)=BossRoom(2);Kill(room,id);var player=room.GetPlayer(id);
        while(player.Inventory.FreeSlots>0)Assert.True(player.Inventory.TryAdd(new(Guid.NewGuid().ToString("D"),ExplorationItemKind.HealthPotion)));
        var item=Red();room.ApplyRedDrop(id,new(player.PendingRedEvaluation!.AttemptId,"Minted",item));
        var redRandom=room.Capture().RandomStreams!.Red;
        room.MarkRedStatePersisted();Assert.False(room.HasRedWork);
        room.MarkPlayerDisconnected(id);room.Advance(TimeSpan.FromSeconds(61),DateTimeOffset.UnixEpoch.AddSeconds(61));
        Assert.True(room.HasRedWork);
        Assert.Equal(RoomPlayerPhase.Dead,player.Phase);Assert.Null(player.PendingRedItem);
        var pile=Assert.Single(room.Capture().RelicPiles!);Assert.Single(pile.Items,value=>value.ItemId==item.ItemId);
        var peer=Guid.NewGuid();room.AddPlayer(new(peer,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        var snapshot=room.Capture();snapshot=snapshot with {Players=snapshot.Players.Select(value=>value.PlayerId==peer
            ?value with {Position=pile.Position,Phase=RoomPlayerPhase.ActionBar}:value).ToArray()};
        room=BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73);
        room.TakeRelicItem(peer,pile.PileId,item.ItemId,pile.Version);
        var picked=Assert.Single(room.GetPlayer(peer).Inventory.Items,value=>value.ItemId==item.ItemId);
        Assert.Equal(item.Equipment,picked.Equipment);Assert.False(picked.IsGenerated);Assert.Equal(redRandom,room.Capture().RandomStreams!.Red);
        Assert.DoesNotContain(room.GetRelicPile(pile.PileId).Items,value=>value.ItemId==item.ItemId);
    }

    [Fact]
    public void NewMintsCanProduceEveryValidUniqueAtLevelZeroWithoutAQualityPromotion()
    {
        var uniques=new HashSet<string>(StringComparer.Ordinal);
        foreach(var seed in Enumerable.Range(0,100))
        {
            var gear=SeasonRedConfig.Equipment(seed,"season-equipment-v1","Water",GameConfigCatalog.Current.SeasonLootPreference);
            Assert.True(EquipmentRewardRules.IsValid(gear));Assert.Equal("Red",gear.Quality);Assert.Equal(0,gear.Level);
            if(gear.UniqueAffix=="Inferno")Assert.Equal(gear.Element,gear.UniqueElement);
            if(gear.UniqueAffix=="GoldenCicada")Assert.Equal("Feet",gear.Slot);
            uniques.Add(gear.UniqueAffix!);
        }
        Assert.Equal(5,uniques.Count);
    }

    [Fact]
    public void VersionSixArchiveDoesNotAcquireTheNewPolicyOrSerializedStream()
    {
        var directory=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(directory is not null)
        {
            var candidate=Path.Combine(directory.FullName,"server/config/archive/season-v1-config-6/fantasycard.config.bytes");
            if(File.Exists(candidate)){path=candidate;break;}directory=directory.Parent;
        }
        Assert.NotNull(path);var config=GameConfigCatalog.Load(File.ReadAllBytes(path));Assert.Null(config.SeasonRed);
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,season:new("old",2,"season-v1",config.Version,"season-equipment-v1"));
        room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        var snapshot=room.Capture();Assert.Null(snapshot.RandomStreams!.Red);
        Assert.DoesNotContain("pendingRed",JsonSerializer.Serialize(snapshot,Json),StringComparison.Ordinal);
        Assert.Equivalent(snapshot,BattleRoom.Restore(snapshot,CombatCardCatalog.Create(config),73).Capture(),strict:true);
    }

    private static ExplorationItem Red()=>new(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
        Equipment:SeasonRedConfig.Equipment(73,"season-equipment-v1","Water",GameConfigCatalog.Current.SeasonLootPreference),IsGenerated:false);
    private static (BattleRoom Room,Guid Id) BossRoom(int difficulty)
    {
        var config=GameConfigCatalog.Current;var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,
            season:new("red-controls",difficulty,"season-v1",config.Version,"season-equipment-v1"));var id=Guid.NewGuid();
        room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        var map=ChaosMapGenerator.Generate(73,1).Capture();var start=map.SpawnPositions[0];
        map=map with {Cells=map.Cells.Select(cell=>cell.Position==start?cell with {Layer=ChaosMapLayer.Core,IsBoss=true,MonsterGroupId="BOSS"}:cell).ToArray()};
        room.InitializeMap(ChaosMapState.Restore(map));return(room,id);
    }
    private static void Kill(BattleRoom room,Guid id)
    {
        var player=room.GetPlayer(id);
        foreach(var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp+monster.Shield-1);SeasonFenxianTests.SetHand(player,"C01");
            room.PlayCards(id,player.Pve.BattleId,monster.MonsterId,[player.Combat.Deck.Hand[0].InstanceId],room.Revision,
                DateTimeOffset.UnixEpoch.ToOffset(TimeSpan.FromHours(8)),room.NewCombatActionId(id));
            room.Advance(TimeSpan.FromMilliseconds(500),DateTimeOffset.UnixEpoch);
        }
        Assert.Equal(RoomPlayerPhase.Choice,player.Phase);
    }
}
