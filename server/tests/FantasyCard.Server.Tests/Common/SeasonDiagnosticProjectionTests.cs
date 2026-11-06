using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Common;

public sealed class SeasonDiagnosticProjectionTests
{
    [Theory]
    [InlineData(80,70,80,"AboveBaseWithinEffective")][InlineData(70,70,70,"Above60PercentBase")]
    [InlineData(42,70,70,"AtOrBelow60PercentBase")][InlineData(43,70,70,"Above60PercentBase")]
    [InlineData(81,70,80,"AboveRecordedEffective")][InlineData(80,null,80,"MissingOriginal")]
    public void HealthBandsKeepLegalVitalityOvercapAndUnknownHistoricalBaseDistinct(int hp,int? baseHp,int effective,string expected)
        =>Assert.Equal(expected,SeasonDiagnosticProjection.HealthBand(hp,baseHp,effective));

    [Fact]
    public void SelectionsUseOriginalOfferBuildAndCountAbandonedRefreshesIncompleteSetsAndUnmatchedChoices()
    {
        var room=Guid.NewGuid();var player=Guid.NewGuid();var dimensions=new SeasonEventDimensions("s","D0","Mage","OriginalOfferBuild","EffectiveBaseCardMaxL0","Human","Outer","season-v1","cfg","stats","PotentialChoice");
        DurableRoomEvent Row(long seq,string id,bool selection=false)=>new($"{room:N}:{seq}",room,Guid.Empty,"cfg",null,
            new(seq,player,HeroClass.Mage,false,selection?"loot_chosen":"loot_generated",selection?"RewardChoice":"Refresh",selection?"ImmediateHeal":"PotentialChoice",TimeSpan.Zero,DateTimeOffset.UnixEpoch,null,null,"Outer",[],0,80,80,
                selection?0:null,id,10,80,RewardBias:"Fragments",BaseMaximumHp:70),selection?dimensions with{BuildType="ChangedAfterSelection"}:dimensions,"EventState",null);
        var offers=new[]{Row(1,"equipment:first"),Row(2,"fragments:first"),Row(3,"heal:first"),Row(4,"equipment:second"),Row(5,"heal:second")};
        var report=new RoomEventTelemetryReport(DateTimeOffset.UnixEpoch,DateTimeOffset.UnixEpoch.AddMinutes(1),[..offers,offers[0],Row(6,"heal:second",true),Row(7,"heal:missing",true)],1,0,0,0,"0",0,true,false);
        var result=SeasonDiagnosticProjection.Choices(report);var group=Assert.Single(result.Groups);
        Assert.Equal("OriginalOfferBuild",group.Dimensions.BuildType);Assert.Equal("AboveBaseWithinEffective",group.HealthBand);Assert.Equal("Fragments",group.OriginalBias);
        Assert.Equal(1,group.Selections);Assert.Equal(1,group.ZeroAppliedHeal);Assert.Equal(0,group.Equipment);Assert.Equal(0,group.Fragments);
        Assert.Equal(new(2,1,1,1,1,true),result.Coverage);
        var unknown=SeasonDiagnosticProjection.Choices(report with{Events=report.Events.Select(e=>e with{Event=e.Event with{RewardBias=null,BaseMaximumHp=null}}).ToArray()});
        Assert.Null(Assert.Single(unknown.Groups).OriginalBias);Assert.Equal("MissingOriginal",unknown.Groups[0].HealthBand);
    }
}
