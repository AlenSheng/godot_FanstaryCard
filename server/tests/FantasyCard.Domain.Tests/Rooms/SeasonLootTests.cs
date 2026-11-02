using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class SeasonLootTests
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web);
    private static readonly string[] Layers=["outer","middle","elite","boss"];
    private static readonly int[] Seeds=[31,73];
    private static readonly int[] BiasedFragmentAmounts=[5,8];
    // Independent proposal percentages, ordered outer/middle/elite/Boss for each D tier.
    private static readonly int[][] Expected=[
        [70,30,0,0,0],[0,60,40,0,0],[0,20,80,0,0],[0,0,100,0,0],
        [20,60,20,0,0],[0,25,65,10,0],[0,0,65,35,0],[0,0,20,80,0],
        [0,30,65,5,0],[0,0,55,43,2],[0,0,25,65,10],[0,0,0,70,30],
        [0,10,60,30,0],[0,0,30,65,5],[0,0,10,70,20],[0,0,0,50,50],
        [0,0,45,55,0],[0,0,15,75,10],[0,0,0,65,35],[0,0,0,35,65],
        [0,0,25,75,0],[0,0,5,80,15],[0,0,0,50,50],[0,0,0,20,80]];

    [Fact]
    public void AllPublishedProbabilityEdgesMatchTheIndependentTwentyFourRowProposal()
    {
        var config=GameConfigCatalog.Current;
        Assert.Equal(24,config.SeasonLootRules.Count);
        for(var difficulty=0;difficulty<6;difficulty++)
        for(var layer=0;layer<4;layer++)
        {
            var rule=config.SeasonLoot(difficulty,Layers[layer]);
            Assert.Equal(Expected[difficulty*4+layer].Select(value=>value*100),rule.Weights);
            var threshold=0;
            for(var rank=0;rank<5;rank++)
            {
                var weight=Expected[difficulty*4+layer][rank]*100;
                if(weight>0)
                {
                    Assert.Equal(SeasonLootConfig.Quality(rank),rule.Roll(threshold));
                    Assert.Equal(SeasonLootConfig.Quality(rank),rule.Roll(threshold+weight-1));
                }
                threshold+=weight;
            }
            Assert.Throws<ArgumentOutOfRangeException>(()=>rule.Roll(-1));
            Assert.Throws<ArgumentOutOfRangeException>(()=>rule.Roll(10000));
        }
    }

    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)] [InlineData(3)] [InlineData(4)] [InlineData(5)]
    public void ActualFactoryUsesPublishedMatrixSinglePromotionAndPreservedOrigin(int difficulty)
    {
        var config=GameConfigCatalog.Current;var season=Context(difficulty);
        foreach(var layerId in Layers)
        foreach(var bias in Enum.GetValues<SeasonRewardBias>())
        foreach(var seed in Seeds)
        {
            var layer=layerId switch {"outer"=>ChaosMapLayer.Outer,"middle"=>ChaosMapLayer.Middle,_=>ChaosMapLayer.Core};
            var choice=RewardChoiceState.Create(layer,new Random(seed),layerId=="boss",configuration:config,season:new(season,bias));
            Assert.Equal(3,choice.Options.Count);
            var item=choice.Options.Single(value=>value.Kind==RewardChoiceKind.Equipment).Item!.Equipment!;
            var origin=Assert.IsType<SeasonEquipmentOrigin>(item.SeasonOrigin);
            Assert.Equal(season,origin.Season);Assert.Equal(layerId,origin.LayerId);
            var rank=SeasonLootConfig.Rank(item.Quality);var baseRank=SeasonLootConfig.Rank(origin.BaseQuality);
            Assert.InRange(rank,0,Math.Min(config.SeasonDifficulty(difficulty).QualityCap,config.SeasonLoot(difficulty,layerId).QualityCap));
            Assert.InRange(rank-baseRank,0,1);
            if(origin.Promoted)Assert.InRange(rank,0,3);
            SeasonLootRules.RequireOrigin(item,season,config);
            var snapshot=JsonSerializer.Deserialize<RewardChoiceSnapshot>(JsonSerializer.Serialize(choice.Capture(),Json),Json)!;
            Assert.Equivalent(choice.Capture(),RewardChoiceState.Restore(snapshot,config,season).Capture(),strict:true);
            Assert.Throws<DomainValidationException>(()=>RewardChoiceState.Restore(snapshot with {SeasonLoot=null},config,season));
        }
        var treasure=RewardChoiceState.Create(ChaosMapLayer.Outer,new Random(81),isTreasure:true,configuration:config,season:new(season,SeasonRewardBias.Equipment));
        var equipment=treasure.Options[0].Item!.Equipment!;
        Assert.Equal("Treasure",equipment.SeasonOrigin!.Source);
        Assert.InRange(SeasonLootConfig.Rank(equipment.Quality)-SeasonLootConfig.Rank(equipment.SeasonOrigin.BaseQuality),0,1);
    }

    [Fact]
    public void NaturalOrangeSurvivesPromotionCapButPurpleCannotBePromotedToOrange()
    {
        var rule=GameConfigCatalog.Current.SeasonLoot(5,"boss");
        Assert.Equal("Orange",rule.ApplyCaps("Orange",true,4));
        Assert.Equal("Purple",rule.ApplyCaps("Purple",true,4));
        Assert.Equal("Purple",rule.ApplyCaps("Blue",true,4));
        Assert.Equal("Blue",GameConfigCatalog.Current.SeasonLoot(0,"outer").ApplyCaps("Purple",true,2));
        Assert.Equal("Purple",GameConfigCatalog.Current.SeasonLoot(5,"outer").ApplyCaps("Orange",true,4));
        Assert.Throws<DomainValidationException>(()=>rule.ApplyCaps("Red",false,4));
    }

    [Theory]
    [InlineData(70)] [InlineData(80)] [InlineData(100)]
    public void HealthyBiasUsesStrictBaseHealthAndCurrentCarriedValueWithoutShieldOrWeapon(int maximumHp)
    {
        var threshold=maximumHp*60/100;
        Assert.Equal(SeasonRewardBias.None,SeasonLootRules.Bias(threshold,maximumHp,ChaosMapLayer.Outer,[],[]));
        Assert.Equal(SeasonRewardBias.Equipment,SeasonLootRules.Bias(threshold+1,maximumHp,ChaosMapLayer.Outer,[],[]));
        ExplorationItem[] armor=[new("blue",ExplorationItemKind.Equipment,Equipment:new("Head","Blue","Fire",null,"DrawInterval",5))];
        Assert.Equal(8,SeasonLootRules.Value(armor));
        Assert.Equal(SeasonRewardBias.Fragments,SeasonLootRules.Bias(maximumHp,maximumHp,ChaosMapLayer.Outer,armor,[]));
        ExplorationItem[] material=[new("warrior",ExplorationItemKind.WarriorSoul,9),new("warrior2",ExplorationItemKind.WarriorSoul,1),new("gold",ExplorationItemKind.Gold,79)];
        Assert.Equal(1,SeasonLootRules.Value(material));
        Assert.Equal(SeasonRewardBias.Fragments,SeasonLootRules.Bias(maximumHp+1,maximumHp,ChaosMapLayer.Outer,armor,material));
    }

    [Fact]
    public void RefreshRecomputesBiasAndNeverAppliesPromotionToThePreviousCandidate()
    {
        var season=Context(1);var config=GameConfigCatalog.Current;
        var choice=RewardChoiceState.Create(ChaosMapLayer.Middle,new Random(73),configuration:config,season:new(season,SeasonRewardBias.None));
        choice.Refresh(new Random(81),SeasonRewardBias.Equipment);
        var expected=RewardChoiceState.Create(ChaosMapLayer.Middle,new Random(81),configuration:config,season:new(season,SeasonRewardBias.Equipment),refreshCount:1);
        Assert.Equivalent(expected.Capture(),choice.Capture(),strict:true);
        var restored=RewardChoiceState.Restore(choice.Capture(),config,season);
        restored.Refresh(new Random(99),SeasonRewardBias.Fragments);
        var raw=RewardChoiceState.Create(ChaosMapLayer.Middle,new Random(99),configuration:config,season:new(season,SeasonRewardBias.None));
        var rawQuantity=raw.Options[1].Item!.Quantity;
        // D1: raw integer is 2 or 3. floor(raw*1.4) was not doubled after truncation.
        Assert.Contains(restored.Options[1].Item!.Quantity,BiasedFragmentAmounts);
        Assert.Equal(rawQuantity==2?5:8,restored.Options[1].Item!.Quantity);
        Assert.Equal(5,SeasonDifficultyConfig.Scale(4,14000));
        Assert.Equal(4,SeasonDifficultyConfig.Scale(2,14000)*2);
    }

    [Theory]
    [InlineData("E1")] [InlineData("E6")]
    public void MiddleNeighborElitesUseEliteRewardsAndActualRoomRecoveryKeepsTheSameChoice(string group)
    {
        var config=GameConfigCatalog.Current;var context=Context(0);var catalog=CombatCardCatalog.Create(config);
        var map=ChaosMapGenerator.Generate(73,1).Capture();var start=map.SpawnPositions[0];
        map=map with {Cells=map.Cells.Select(cell=>cell.Position==start ? cell with {Layer=ChaosMapLayer.Middle,MonsterGroupId=group,IsBoss=false}:cell).ToArray()};
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:context);var id=Guid.NewGuid();
        var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));room.InitializeMap(ChaosMapState.Restore(map));
        // Controlled one-HP observation targets exercise the real kill/choice path, not route balance.
        foreach(var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp+monster.Shield-1);
            SeasonFenxianTests.SetHand(player,"C01");
            room.PlayCards(id,player.Pve.BattleId,monster.MonsterId,[player.Combat.Deck.Hand[0].InstanceId],room.Revision,DateTimeOffset.UnixEpoch,
                room.NewCombatActionId(id));
            room.Advance(TimeSpan.FromMilliseconds(500),DateTimeOffset.UnixEpoch);
        }
        Assert.Equal(RoomPlayerPhase.Choice,player.Phase);Assert.Equal(ChaosMapLayer.Core,player.RewardChoice!.Layer);
        Assert.Equal(28,player.RewardChoice.Options[2].HealPercent);
        var before=room.Capture();var restored=BattleRoom.Restore(before,catalog,73);
        Assert.Equivalent(before,restored.Capture(),strict:true);
        Assert.Equal(32,player.Inventory.GoldQuantity);
    }

    private static SeasonContext Context(int difficulty)=>new("loot",difficulty,"season-v1",GameConfigCatalog.Current.Version,"season-equipment-v1");

    [Fact]
    public void NewGeneratedOriginsSurviveInventoryAndBotBudgetRecoveryAndMissingOriginsAreRejected()
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var context=Context(2);
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:context);var id=Guid.NewGuid();
        var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        room.AddPlayer(new(Guid.NewGuid(),HeroClass.Guardian,SeasonFenxianTests.Starter(HeroClass.Guardian),null,IsBot:true));
        var reward=RewardChoiceState.Create(ChaosMapLayer.Core,new Random(73),configuration:config,season:new(context,SeasonRewardBias.None)).Options[0].Item!;
        Assert.True(player.Inventory.TryAdd(reward));
        var snapshot=room.Capture();var restored=BattleRoom.Restore(snapshot,catalog,73);
        Assert.Equivalent(snapshot,restored.Capture(),strict:true);
        var invalid=snapshot with {Players=snapshot.Players.Select(value=>value.PlayerId==id?value with
            {Inventory=value.Inventory! with {Items=value.Inventory!.Items.Select(item=>item with {Equipment=item.Equipment! with {SeasonOrigin=null}}).ToArray()}}:value).ToArray()};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(invalid,catalog,73));
    }

    [Theory]
    [InlineData(0,"Purple",false)] [InlineData(0,"Blue",true)] [InlineData(1,"Orange",false)] [InlineData(1,"Purple",true)]
    [InlineData(2,"Orange",true)] [InlineData(2,"Red",true)]
    public void EntryQualityAndCombinedOrangeRedCapsUseThePublishedDifficulty(int difficulty,string quality,bool allowed)
    {
        var config=GameConfigCatalog.Current;
        EquipmentRewardData[] single=[new("Head",quality,"Fire",quality is "Orange" or "Red"?"Piercing":null,"DrawInterval")];
        if(allowed)SeasonLootRules.RequireEntry(Context(difficulty),single,config);
        else Assert.Throws<DomainValidationException>(()=>SeasonLootRules.RequireEntry(Context(difficulty),single,config));
        EquipmentRewardData[] pair=[new("Head","Orange","Fire","Piercing","DrawInterval"),new("Chest","Red","Fire","Bulwark","DrawInterval")];
        Assert.Throws<DomainValidationException>(()=>SeasonLootRules.RequireEntry(Context(2),pair,config));
    }
}
