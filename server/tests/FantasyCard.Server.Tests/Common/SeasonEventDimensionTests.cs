using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Common;

public sealed class SeasonEventDimensionTests
{
    private static (RoomEventObservation Row,IReadOnlyDictionary<string,RoomBuildProfile> Profiles) Fixture()
    {
        var room=new BattleRoom(Guid.NewGuid(),"dimension-config",CombatCardCatalog.CreatePrototype(),73);var player=Guid.NewGuid();
        room.AddPlayer(new(player,HeroClass.Mage,Enumerable.Repeat("common-01",20).ToArray(),null));room.InitializeMap(ChaosMapGenerator.Generate(73,1),DateTimeOffset.UnixEpoch);room.AbandonBattle(player);
        var snapshot=room.Capture().Observations!;return(snapshot.Events[0],snapshot.Profiles!.ToDictionary(p=>p.ProfileId));
    }

    [Fact]
    public void RoomDimensionsUseOriginalBattleBindingAndFrozenRealm()
    {
        var input=Fixture();var season=new SeasonContext("original-season",2,"season-v1","dimension-config","original-stats");
        var result=SeasonEventDimensionRules.Room("dimension-config",season,"D5",input.Row,input.Profiles);
        Assert.Equal("D2",result.Dimensions.DifficultyId);Assert.Equal("original-season",result.Dimensions.SeasonId);Assert.Equal("original-stats",result.Dimensions.StatsVersion);
        Assert.Equal("BattleStart",result.Basis);Assert.Equal("MonoFire/NoActiveEffectSet",result.Dimensions.BuildType);Assert.Equal("EffectiveBaseCardMaxL0",result.Dimensions.GrowthStage);
    }

    [Fact]
    public void MissingOriginalBindingDoesNotUseKnownLatestProfileAsTheBattleBuild()
    {
        var input=Fixture();var result=SeasonEventDimensionRules.Room("dimension-config",null,"Standard",input.Row with{BattleBuildProfileId=null},input.Profiles);
        Assert.Equal("MissingOriginal",result.Basis);Assert.Null(result.Dimensions.BuildType);Assert.Null(result.Dimensions.GrowthStage);Assert.Null(result.Profile);
        Assert.Equal("Standard",result.Dimensions.DifficultyId);Assert.Null(result.Dimensions.SeasonId);
    }

    [Fact]
    public void StoredProfileNeedsItsOriginalFingerprintAndDoesNotReadLiveState()
    {
        var profile=Fixture().Profiles.Values.Single();var parsed=SeasonEventDimensionRules.StoredProfile(JsonSerializer.Serialize(profile));Assert.NotNull(parsed);
        Assert.Equal(profile.ProfileId,parsed.ProfileId);Assert.Equal(JsonSerializer.Serialize(profile),JsonSerializer.Serialize(parsed));
        Assert.Null(SeasonEventDimensionRules.StoredProfile(JsonSerializer.Serialize(profile with{GrowthStage="account-day14"})));
        Assert.Null(SeasonEventDimensionRules.StoredProfile("{}"));Assert.Null(SeasonEventDimensionRules.StoredProfile(null));
    }

    [Fact]
    public void CoverageReportsUnknownLobbyDimensionsWithoutInventingAPlayedD0OrPlayerClass()
    {
        var dimensions=new SeasonEventDimensions("s",null,null,null,null,"Unknown","Lobby","season-v1","v","stats","Completed");
        var counts=SeasonEventDimensionRules.UnknownCounts([dimensions]);Assert.Equal(1,counts["build"]);Assert.Equal(1,counts["growth"]);Assert.Equal(1,counts["difficulty"]);Assert.Equal(0,counts["configVersion"]);
    }
}
