using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonJourneyTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ThirtyDayJourneyReadsPerLevelCeilingFromTheOriginalSeasonAndStillAuditsItsActualCredit()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db,duration:30);
        await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p,"Outer"));
        var read=await p.Journey.GetAsync(p.Player,Ct);Assert.Equal(30,read.DurationDays);Assert.Equal(8959,read.MaximumExperience);
        Assert.Equal(143,read.Levels[0].RequiredExperience);Assert.Equal(8959,read.Levels[^1].CumulativeExperience);
        Assert.Equal(p.Config.SeasonJourney!.Threshold(20,30),read.ReferenceExperience);Assert.Equal(12,read.Experience);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task FourActualOuterClearsGiveBaseTwentyFourOnceEvenWhenDeathAndConcurrentRecoveryFollow()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        var done=await JourneyTestInputs.DeadAfterClears(db,p,"Outer","Outer","Outer","Outer");
        await Task.WhenAll(Enumerable.Range(0,6).Select(_=>JourneyTestInputs.Observe(db,p,done)));
        var read=await p.Journey.GetAsync(p.Player,Ct);Assert.Equal(48,read.Experience);
        Assert.Equal(24,await db.ScalarAsync<long>("SELECT sum(base_experience)::bigint FROM season_journey_sources WHERE player_id=$1",p.Player));
        Assert.Equal(24,await db.ScalarAsync<long>("SELECT sum(catch_up_experience)::bigint FROM season_journey_sources WHERE player_id=$1",p.Player));
        Assert.Equal(4,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_sources WHERE player_id=$1",p.Player));
        Assert.All(read.Contracts,row=>Assert.Equal(0,row.Progress));
        var restarted=new SeasonJourneyRepository(db.DataSource,p.Clock,new PublishedConfigCatalogs(GameConfigCatalog.Current));
        Assert.Equivalent(read,await restarted.GetAsync(p.Player,Ct),strict:true);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task DeathWithoutAnActualClearGivesNoExperienceOrWeeklyProgress()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p));
        var read=await p.Journey.GetAsync(p.Player,Ct);Assert.Equal(0,read.Experience);Assert.Equal(0,read.Version);
        Assert.All(read.Contracts,row=>Assert.Equal(0,row.Progress));Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_sources"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task OneBossAdvancesOnlyTheOldestOpenWeekAndItsThreeHundredExperienceNeverDoubles()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p,"Elite","Boss"));
        var read=await p.Journey.GetAsync(p.Player,Ct);Assert.Equal(510,read.Experience);
        var boss=Assert.Single(read.Contracts,c=>c.CompletionKind=="Boss"&&c.State=="Completed");
        Assert.Equal(1,boss.Week);Assert.Equal(300,boss.ExperienceCredited);
        Assert.All(read.Contracts.Where(c=>c.CompletionKind=="Boss"&&c.Week>1),row=>Assert.Equal(0,row.Progress));
        Assert.Equal(1,read.Contracts.Single(c=>c.CompletionKind=="Elite"&&c.Week==1).Progress);
        Assert.Equal(2,await db.ScalarAsync<long>("SELECT count(*) FROM season_weekly_contract_events"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ThreeExtractionsGrantSeventyEachAndOneContractAcrossRealClassUpdates()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        for(var i=0;i<3;i++)await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.Extract(db,p));
        Assert.Equal(510,(await p.Journey.GetAsync(p.Player,Ct)).Experience);
        foreach(var hero in new[]{HeroClassDto.Priest,HeroClassDto.Guardian})
        {
            var version=await db.ScalarAsync<long>("SELECT version FROM players WHERE user_id=$1",p.Player);
            var changed=await new PlayerRepository(db.DataSource).UpdateAsync(p.Player,new(null,hero,version),"class-"+hero,p.Clock.Now,Ct);
            Assert.Equal(UpdatePlayerResult.Updated,changed.Status);var read=await p.Journey.GetAsync(p.Player,Ct);
            Assert.Equal(510,read.Experience);Assert.Single(read.Contracts,c=>c.CompletionKind=="Extracted"&&c.State=="Completed");
        }
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT sum(catch_up_experience)::bigint FROM season_journey_sources"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task LateOriginalClearsRemainInTheirOldJourneyWithoutFundingTheNextSeason()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);p.Clock.Now=p.Season.EndsAtUtc.AddSeconds(-30);
        var done=await JourneyTestInputs.DeadAfterClears(db,p,"Outer");p.Clock.Now=p.Season.EndsAtUtc.AddDays(1);
        var next=SeasonDefinition.FromCalendarDays("next-journey",DateOnly.FromDateTime(p.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),p.Config.Version,p.Season.StatsVersion);
        await p.Seasons.PublishAsync(next,p.Config.ContentHash,Ct);await p.Seasons.EnsurePlayerAsync(p.Player,next.ContextFor(0),Ct);
        await JourneyTestInputs.Observe(db,p,done);
        Assert.Equal(12,(await p.Journey.GetAsync(p.Player,Ct,p.Season.SeasonId)).Experience);
        var current=await p.Journey.GetAsync(p.Player,Ct);Assert.Equal(next.SeasonId,current.SeasonId);Assert.Equal(0,current.Experience);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ForgedCompletionTimeRollsBackAndTheOriginalCheckpointStillRecovers()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        var done=await JourneyTestInputs.DeadAfterClears(db,p,"Outer");var player=done.Snapshot.Players[0];
        var changed=done with {Snapshot=done.Snapshot with {Players=[player with {JourneyCompletions=player.JourneyCompletions!.Select(c=>c with {CompletedAt=c.CompletedAt.AddSeconds(-1)}).ToArray()}]}};
        await Assert.ThrowsAsync<InvalidDataException>(()=>JourneyTestInputs.Observe(db,p,changed));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",done.Match));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_sources"));
        await JourneyTestInputs.Observe(db,p,done);Assert.Equal(12,(await p.Journey.GetAsync(p.Player,Ct)).Experience);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task LedgerCommitFailureLeavesNoSourceOrPartialExperienceAndRetryCreditsOnce()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);var done=await JourneyTestInputs.DeadAfterClears(db,p,"Outer");
        await db.ExecuteAsync("CREATE FUNCTION fail_journey_credit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated journey credit fault'; END $$; CREATE TRIGGER journey_credit_fault BEFORE INSERT ON season_journey_ledger FOR EACH ROW EXECUTE FUNCTION fail_journey_credit();");
        await Assert.ThrowsAsync<PostgresException>(()=>JourneyTestInputs.Observe(db,p,done));
        Assert.Equal(0,(await p.Journey.GetAsync(p.Player,Ct)).Experience);Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_sources"));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",done.Match));
        await db.ExecuteAsync("DROP TRIGGER journey_credit_fault ON season_journey_ledger;");
        await JourneyTestInputs.Observe(db,p,done);await JourneyTestInputs.Observe(db,p,done);
        Assert.Equal(12,(await p.Journey.GetAsync(p.Player,Ct)).Experience);Assert.Equal(1,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_sources"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task JourneyHistoryPagesDoNotRepeatAndExplicitOldSourceDoesNotSwitchToCurrent()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);var done=await JourneyTestInputs.Extract(db,p);await JourneyTestInputs.Observe(db,p,done);
        p.Clock.Now=p.Season.EndsAtUtc.AddDays(1);var next=SeasonDefinition.FromCalendarDays("next-page",DateOnly.FromDateTime(p.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),p.Config.Version,p.Season.StatsVersion);
        await p.Seasons.PublishAsync(next,p.Config.ContentHash,Ct);
        var first=await p.Journey.GetAsync(p.Player,Ct,null,1);Assert.Equal(next.SeasonId,first.SeasonId);Assert.Equal(next.SeasonId,Assert.Single(first.Seasons).SeasonId);Assert.Equal(1,first.NextOffset);
        var second=await p.Journey.GetAsync(p.Player,Ct,p.Season.SeasonId,1,first.NextOffset!.Value);
        Assert.Equal(p.Season.SeasonId,second.SeasonId);Assert.Equal(p.Season.SeasonId,Assert.Single(second.Seasons).SeasonId);Assert.Null(second.NextOffset);Assert.Equal(70,second.Experience);
        Assert.Equal("None",(await p.Journey.GetAsync(p.Player,Ct,"unknown-original")).State);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task AuditDetectsAnExperienceAggregateThatNoLongerMatchesItsSources()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p,"Outer"));
        var audit=new EconomyReconciliationRepository(db.DataSource);Assert.True((await audit.InspectAsync(Ct)).IsHealthy);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_journeys SET experience=experience+1 WHERE player_id=$1",p.Player);
        Assert.True((await audit.InspectAsync(Ct)).JourneyExperienceMismatchCount>0);
    }
}
