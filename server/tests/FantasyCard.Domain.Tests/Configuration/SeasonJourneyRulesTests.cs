using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Configuration;

public sealed class SeasonJourneyRulesTests
{
    private static SeasonJourneyConfig Rules()=>new(SeasonJourneyConfig.Version,6,10,25,80,70,2,21,6850,20,
        Enumerable.Range(0,30).Select(level=>200+15*level).ToArray(),
        [new("weekly-extraction","Extracted",3,300),new("weekly-elite","Elite",5,300),new("weekly-boss","Boss",1,300)]);
    private static SeasonDefinition Season(int days=42)=>SeasonDefinition.FromCalendarDays("journey-rules",new(2026,11,1),"test-config","season-equipment-v1",days);

    [Fact]
    public void PublishedJourneyUsesTheFormalGroupAndOriginalConfigTenRemainsWithoutJourneyAwards()
    {
        var current=GameConfigCatalog.Current;var policy=Assert.IsType<SeasonJourneyConfig>(current.SeasonJourney);
        policy.Validate();Assert.Equal("season-v1-config-11",current.Version);
        Assert.Equal(12525,policy.Threshold(30,42));Assert.Equal(8959,policy.Threshold(30,30));
        Assert.Equal(3,policy.WeeklyContracts.Single(c=>c.CompletionKind=="Extracted").Target);
        Assert.Equal(5,policy.WeeklyContracts.Single(c=>c.CompletionKind=="Elite").Target);
        Assert.Equal(1,policy.WeeklyContracts.Single(c=>c.CompletionKind=="Boss").Target);
        var directory=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(directory is not null)
        {
            var candidate=Path.Combine(directory.FullName,"server/config/archive/season-v1-config-10/fantasycard.config.bytes");
            if(File.Exists(candidate)){path=candidate;break;}directory=directory.Parent;
        }
        Assert.NotNull(path);var original=GameConfigCatalog.Load(File.ReadAllBytes(path));
        Assert.Null(original.SeasonJourney);Assert.NotNull(original.SeasonActivity);
    }

    [Theory]
    [InlineData(30,8959)]
    [InlineData(42,12525)]
    [InlineData(60,12525)]
    public void CompleteTrackUsesPerLevelCeilingAndKeepsPermanentProgressionSeparate(int days,int total)
    {
        var rules=Rules();rules.Validate();Assert.Equal(total,rules.Threshold(30,days));
        Assert.Equal(30,rules.Progress(total,days).Level);Assert.Equal(0,rules.Progress(total,days).ExperienceToNext);
        Assert.Equal(29,rules.Progress(total-1,days).Level);Assert.Equal(70,rules.ExtractionExperience);
        if(days==42)Assert.Equal(6850,rules.Threshold(20,days));
        for(var level=0;level<30;level++)Assert.Equal((int)Math.Ceiling((200+15*level)*Math.Min(days,42)/42d),rules.Cost(level,days));
    }

    [Fact]
    public void CatchUpNeverCrossesTheReferenceAndDoesNotDoubleExtractionOrInventDeathExperience()
    {
        var rules=Rules();var season=Season();var when=season.StartsAtUtc.AddDays(20);
        Assert.Equal(6850,rules.ReferenceAt(season,when));
        Assert.Equal(new SeasonJourneyGrant(6,6,12,12),rules.Grant(season,when,0,"Outer"));
        Assert.Equal(new SeasonJourneyGrant(6,4,10,6850),rules.Grant(season,when,6840,"Outer"));
        Assert.Equal(0,rules.Grant(season,when,6849,"Outer").CatchUpExperience);
        Assert.Equal(new SeasonJourneyGrant(70,0,70,70),rules.Grant(season,when,0,"Extracted"));
        Assert.Throws<DomainValidationException>(()=>rules.Grant(season,when,0,"Dead"));
        Assert.Throws<DomainValidationException>(()=>rules.SourceExperience("PvpKill"));
        Assert.Equal(new SeasonJourneyGrant(1,0,1,12525),rules.Grant(season,when,12524,"Boss"));
        Assert.Equal(0,rules.Grant(season,when,12525,"Boss").CreditedExperience);
    }

    [Fact]
    public void ExperienceKindIsBasedOnTheClearedCellNotGenericDeathOrRawCoreLayer()
    {
        var rules=Rules();var position=new MapPosition(2,2);
        Assert.Equal("Elite",SeasonJourneyConfig.CellKind(new(position,ChaosMapLayer.Outer,false,false,false,"E1")));
        Assert.Equal("Boss",SeasonJourneyConfig.CellKind(new(position,ChaosMapLayer.Core,true,false,false,"BOSS")));
        Assert.Equal("Outer",SeasonJourneyConfig.CellKind(new(position,ChaosMapLayer.Outer,false,false,false,"BOX")));
        Assert.Equal("Middle",SeasonJourneyConfig.CellKind(new(position,ChaosMapLayer.Middle,false,false,false,"M1")));
        Assert.Equal(24,4*rules.SourceExperience("Outer"));
    }

    [Fact]
    public void WeekAndReferenceUseSeasonNaturalDaysAndStopAtOriginalBoundaries()
    {
        var rules=Rules();var season=Season();
        Assert.Equal(1,SeasonJourneyConfig.WeekAt(season,season.StartsAtUtc.AddDays(7).AddTicks(-1)));
        Assert.Equal(2,SeasonJourneyConfig.WeekAt(season,season.StartsAtUtc.AddDays(7)));
        Assert.Equal(6,SeasonJourneyConfig.WeekAt(season,season.EndsAtUtc.AddTicks(-1)));
        Assert.Equal(6850,rules.ReferenceAt(season,season.EndsAtUtc.AddTicks(-1)));
        Assert.Throws<DomainValidationException>(()=>rules.Grant(season,season.EndsAtUtc,0,"Outer"));
        var shortSeason=Season(30);
        Assert.Equal(rules.Threshold(20,30),rules.ReferenceAt(shortSeason,shortSeason.StartsAtUtc.AddDays(20)));
    }

    [Fact]
    public void ExperienceAndContractInflationAreRejectedAtTheConfigurationBoundary()
    {
        var rules=Rules();
        Assert.Throws<InvalidDataException>(()=>(rules with {CatchUpMultiplier=3}).Validate());
        Assert.Throws<InvalidDataException>(()=>(rules with {EliteExperience=50}).Validate());
        Assert.Throws<InvalidDataException>(()=>(rules with {WeeklyContracts=[new("x","Extracted",1,900),new("y","Elite",1,300),new("z","Boss",1,300)]}).Validate());
    }
}
