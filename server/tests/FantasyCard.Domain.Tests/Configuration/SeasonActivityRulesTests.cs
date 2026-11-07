using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Configuration;

public sealed class SeasonActivityRulesTests
{
    private static SeasonActivityConfig Policy()=>new(SeasonActivityConfig.Version,"Extracted",4,12,"Asia/Shanghai",0,true,
        [new("activity-one",12,3),new("activity-two",33,3)],
        [new("event-fragments",3,"bound_fragments",10,4),new("event-warrior",3,"bound_warrior_soul",6,4),new("event-class",3,"bound_class_soul",2,4),new("event-potion",6,"potion",1,1)]);

    [Fact]
    public void ActualPublishedPolicyHasTheBoundBudgetAndTheOriginalConfigNineArchiveHasNoActivities()
    {
        var c=GameConfigCatalog.Current;var p=Assert.IsType<SeasonActivityConfig>(c.SeasonActivity);p.Validate();Assert.Equal(12,p.TokenCap);
        var d=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(d is not null){var candidate=Path.Combine(d.FullName,"server/config/archive/season-v1-config-9/fantasycard.config.bytes");if(File.Exists(candidate)){path=candidate;break;}d=d.Parent;}
        Assert.NotNull(path);var old=GameConfigCatalog.Load(File.ReadAllBytes(path));Assert.Null(old.SeasonActivity);Assert.NotNull(old.SeasonShop);
    }

    [Theory][InlineData(30)][InlineData(42)][InlineData(60)]
    public void TwoThreeDayWindowsStayInsideTheirOriginalSeasonAndUseLeftClosedRightOpenEdges(int duration)
    {
        var p=Policy();p.Validate();var season=SeasonDefinition.FromCalendarDays("event-season",new(2026,11,1),"test-config","season-equipment-v1",duration);
        var windows=p.Windows(season);Assert.Equal(2,windows.Count);Assert.True(windows[0].EndsAt<=windows[1].StartsAt);
        foreach(var window in windows)
        {
            Assert.Equal(TimeSpan.FromDays(3),window.EndsAt-window.StartsAt);Assert.True(window.StartsAt>=season.StartsAtUtc&&window.EndsAt<=season.EndsAtUtc);
            Assert.True(window.Contains(window.StartsAt));Assert.False(window.Contains(window.EndsAt));Assert.False(window.Contains(window.StartsAt.AddTicks(-1)));
            Assert.Equal(0,window.StartsAt.ToOffset(TimeSpan.FromHours(8)).Hour);
        }
    }

    [Theory]
    [InlineData("event-fragments",4,12,40)] [InlineData("event-warrior",4,12,24)] [InlineData("event-class",4,12,8)] [InlineData("event-potion",1,6,1)]
    public void PublishedChoicesConsumeTheSharedTokenBudgetInsteadOfGivingEachBranchItsOwnTwelve(string rule,int quantity,int cost,int reward)
    {
        var p=Policy();Assert.Equal((cost,reward),p.Quote(rule,quantity));
        Assert.Throws<DomainValidationException>(()=>p.Quote(rule,quantity+1));Assert.Throws<DomainValidationException>(()=>p.Quote(rule,0));
    }

    [Fact]
    public void RedGoldDiamondAndUnboundRewardKindsCannotEnterTheDefaultPolicy()
    {
        var p=Policy();Assert.Throws<DomainValidationException>(()=>p.Exchange("red-material"));
        Assert.Throws<InvalidDataException>(()=>(p with {TokenCap=24}).Validate());
        Assert.Throws<InvalidDataException>(()=>(p with {Exchanges=[new("red",3,"red-material",1,4)]}).Validate());
        Assert.Throws<InvalidDataException>(()=>(p with {Calendar=[new("one",40,3),new("two",41,3)]}).Validate());
    }

    [Fact]
    public void ActualExtractionTimestampUsesTheCompletionInstantAndSurvivesJsonRecovery()
    {
        var c=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(c);var room=new BattleRoom(Guid.NewGuid(),c.Version,catalog,42);
        var id=Guid.NewGuid();room.AddPlayer(new(id,HeroClass.Mage,c.Cards.Where(x=>x.IsCodex&&x.InitiallyUnlocked&&x.HeroClass is null).Take(20).Select(x=>x.CardId).ToArray(),null));
        room.InitializeMap(ChaosMapGenerator.Generate(42,1));var s=room.Capture();var boss=s.Map!.Cells.Single(x=>x.IsBoss).Position;
        s=s with {Players=s.Players.Select(x=>x with {Position=boss,Phase=RoomPlayerPhase.ActionBar,Pve=null}).ToArray()};room=BattleRoom.Restore(s,catalog,42);
        var end=new DateTimeOffset(2026,11,12,0,0,5,TimeSpan.Zero);room.RequestExtraction(id);room.Advance(TimeSpan.FromSeconds(5),end);
        var done=Assert.Single(room.Capture().Players);Assert.Equal(RoomPlayerPhase.Extracted,done.Phase);Assert.Equal(end.AddSeconds(-2),done.ExtractionCompletedAt);
        var restored=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(room.Capture()))!,catalog,42);
        Assert.Equal(done.ExtractionCompletedAt,Assert.Single(restored.Capture().Players).ExtractionCompletedAt);
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(s with {Players=s.Players.Select(x=>x with {ExtractionCompletedAt=end}).ToArray()},catalog,42));
    }
}
