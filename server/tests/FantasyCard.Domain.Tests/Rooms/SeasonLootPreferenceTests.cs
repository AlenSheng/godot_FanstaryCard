using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class SeasonLootPreferenceTests
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web);
    [Theory]
    [InlineData("Wood")] [InlineData("Fire")] [InlineData("Earth")] [InlineData("Metal")] [InlineData("Water")]
    public void EachPreferenceHasFortyPercentAndFourExactFifteenPercentIntervals(string preferred)
    {
        var policy=new SeasonLootPreferenceConfig("Fire",4000,1500);policy.Validate();
        var cursor=0;
        foreach(var element in SeasonLootPreferenceConfig.Elements)
        {
            var width=element==preferred?4000:1500;
            Assert.Equal(element,policy.Roll(preferred,cursor));
            Assert.Equal(element,policy.Roll(preferred,cursor+width-1));
            cursor+=width;
        }
        Assert.Equal(10000,cursor);
        Assert.Equal("Fire",policy.Resolve(null));
        Assert.Throws<DomainValidationException>(()=>policy.Resolve("None"));
        Assert.Throws<ArgumentOutOfRangeException>(()=>policy.Roll(preferred,-1));
        Assert.Throws<ArgumentOutOfRangeException>(()=>policy.Roll(preferred,10000));
    }

    [Theory]
    [InlineData("None",4000,1500)] [InlineData("Fire",3999,1500)] [InlineData("Fire",4000,1501)]
    public void InvalidWeightsCannotBecomeAProbabilityFallback(string defaultElement,int preferred,int other) =>
        Assert.Throws<InvalidDataException>(()=>new SeasonLootPreferenceConfig(defaultElement,preferred,other).Validate());

    [Fact]
    public void FactoryPreferenceChangesOnlyElementWithoutTakingExtraRandomNumbers()
    {
        var config=GameConfigCatalog.Current;
        Assert.NotNull(config.SeasonLootPreference);
        var context=new SeasonContext("preference",2,"season-v1",config.Version,"season-equipment-v1");
        var first=new CombatRandom(73);var second=new CombatRandom(73);
        var fire=RewardChoiceState.Create(ChaosMapLayer.Core,first,configuration:config,season:new(context,SeasonRewardBias.None,"Fire"));
        var water=RewardChoiceState.Create(ChaosMapLayer.Core,second,configuration:config,season:new(context,SeasonRewardBias.None,"Water"));
        Assert.Equal(first.State,second.State);
        var a=fire.Options[0].Item!.Equipment!;var b=water.Options[0].Item!.Equipment!;
        Assert.Equal(a with {Element=b.Element},b);
        Assert.Equal(fire.Options[1],water.Options[1]);Assert.Equal(fire.Options[2],water.Options[2]);
        Assert.Equal("Fire",fire.Capture().SeasonLoot!.LootPreferenceElement);
        Assert.Equal("Water",water.Capture().SeasonLoot!.LootPreferenceElement);
    }

    [Fact]
    public void ActualRewardRefreshAndRecoveryKeepThePlayersLockedPreferenceAndIndependentStreams()
    {
        var (room,id)=ChoiceRoom();var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);
        var snapshot=room.Capture();var player=snapshot.Players.Single();
        Assert.Equal("Water",player.LootPreferenceElement);Assert.Equal("Water",player.RewardChoice!.SeasonLoot!.LootPreferenceElement);
        var restored=BattleRoom.Restore(snapshot,catalog,73);
        Assert.Equivalent(snapshot,restored.Capture(),strict:true);
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(snapshot with {Players=[player with {LootPreferenceElement=null}]},catalog,73));
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(snapshot with {Players=[player with {LootPreferenceElement="Fire"}]},catalog,73));
        var before=room.Capture().RandomStreams!;
        room.RefreshRewardChoice(id,room.Revision,requestId:"same-preference");
        restored.RefreshRewardChoice(id,restored.Revision,requestId:"same-preference");
        Assert.Equivalent(room.Capture(),restored.Capture(),strict:true);
        var after=room.Capture();
        Assert.Equal("Water",after.Players[0].RewardChoice!.SeasonLoot!.LootPreferenceElement);
        Assert.NotEqual(before.Reward,after.RandomStreams!.Reward);
        Assert.Equal(before.Loot,after.RandomStreams.Loot);Assert.Equal(before.PlayerSeed,after.RandomStreams.PlayerSeed);
        Assert.Equal(before.Bot,after.RandomStreams.Bot);Assert.Equal(before.Duel,after.RandomStreams.Duel);
    }

    [Fact]
    public void LegacyAbsentPreferenceStaysAbsentInTheSerializedRequestContext()
    {
        var context=new SeasonRewardContext(new("legacy-shape",0,"season-v1","old-config","old-stats"),SeasonRewardBias.None);
        Assert.DoesNotContain("lootPreferenceElement",JsonSerializer.Serialize(context,Json),StringComparison.Ordinal);
    }

    [Fact]
    public void ActualVersionFourArchiveKeepsItsAbsentPreferenceAndRestoresWithoutAnUpgrade()
    {
        var directory=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(directory is not null)
        {
            var candidate=Path.Combine(directory.FullName,"server/config/archive/season-v1-config-4/fantasycard.config.bytes");
            if(File.Exists(candidate)){path=candidate;break;}
            directory=directory.Parent;
        }
        Assert.NotNull(path);
        var config=GameConfigCatalog.Load(File.ReadAllBytes(path));
        Assert.Equal("season-v1-config-4",config.Version);Assert.Null(config.SeasonLootPreference);
        var catalog=CombatCardCatalog.Create(config);
        var season=new SeasonContext("original",2,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:season);
        var player=room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        Assert.Null(player.LootPreferenceElement);
        var snapshot=room.Capture();var json=JsonSerializer.Serialize(snapshot,Json);
        Assert.DoesNotContain("lootPreferenceElement",json,StringComparison.Ordinal);
        Assert.Equivalent(snapshot,BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(json,Json)!,catalog,73).Capture(),strict:true);
        Assert.Throws<DomainValidationException>(()=>room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,LootPreferenceElement:"Water")));
        Assert.Equal(snapshot.RandomStreams,room.Capture().RandomStreams);
    }

    private static (BattleRoom Room,Guid Player) ChoiceRoom()
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);
        var context=new SeasonContext("preference",2,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:context);var id=Guid.NewGuid();
        var player=room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null,LootPreferenceElement:"Water"));
        var map=ChaosMapGenerator.Generate(73,1).Capture();var start=map.SpawnPositions[0];
        map=map with {Cells=map.Cells.Select(cell=>cell.Position==start?cell with {Layer=ChaosMapLayer.Core,MonsterGroupId="E1",IsBoss=false}:cell).ToArray()};
        room.InitializeMap(ChaosMapState.Restore(map));
        foreach(var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp+monster.Shield-1);SeasonFenxianTests.SetHand(player,"C01");
            room.PlayCards(id,player.Pve.BattleId,monster.MonsterId,[player.Combat.Deck.Hand[0].InstanceId],room.Revision,DateTimeOffset.UnixEpoch,room.NewCombatActionId(id));
            room.Advance(TimeSpan.FromMilliseconds(500),DateTimeOffset.UnixEpoch);
        }
        Assert.True(player.Inventory.TryAdd(new("refresh-gold",ExplorationItemKind.Gold,1000)));
        return(room,id);
    }
}
