using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonActivityTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task OriginalEventPaginationHasNoGapsAndRejectsInvalidBounds()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);
        var first=await p.Activities.GetAsync(p.Player,Ct,p.Season.SeasonId,1,0);
        Assert.Equal(1,first.NextOffset);var latest=Assert.Single(first.Events);
        var second=await p.Activities.GetAsync(p.Player,Ct,p.Season.SeasonId,1,first.NextOffset!.Value);
        Assert.Null(second.NextOffset);var earlier=Assert.Single(second.Events);
        Assert.NotEqual(latest.EventId,earlier.EventId);Assert.True(latest.StartsAt>earlier.StartsAt);
        Assert.All(new[]{latest,earlier},e=>{Assert.Equal(p.Season.SeasonId,e.SeasonId);Assert.Equal(0,e.Earned);Assert.Empty(e.Rewards);});
        Assert.Empty((await p.Activities.GetAsync(p.Player,Ct,"unknown-original-season")).Events);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Activities.GetAsync(p.Player,Ct,null,101));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Activities.GetAsync(p.Player,Ct,null,50,-1));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_activity_token_ledger"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ActualSuccessfulExtractionCheckpointAwardsFourOnceAndStopsAtTwelve()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);
        var first=await ActivityTestInputs.Extract(db,p);await ActivityTestInputs.Observe(db,p,first);await ActivityTestInputs.Observe(db,p,first);
        Assert.Equal(4,(await ActivityTestInputs.First(p)).Earned);await ActivityTestInputs.Earn(db,p,3);
        var e=await ActivityTestInputs.First(p);Assert.Equal(12,e.Earned);Assert.Equal(12,e.Available);
        Assert.Equal(4,await db.ScalarAsync<long>("SELECT count(*) FROM season_activity_completions WHERE player_id=$1",p.Player));
        Assert.Equal(12,await db.ScalarAsync<long>("SELECT sum(credited_tokens)::bigint FROM season_activity_completions WHERE player_id=$1",p.Player));
        Assert.Equal(3,await db.ScalarAsync<long>("SELECT count(*) FROM season_activity_token_ledger WHERE player_id=$1",p.Player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task FourChoicesCompeteForOneBudgetAndPotionRemainsOnePerEvent()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p);
        var choices=new[]{("event-fragments",(string?)null),("event-warrior",(string?)null),("event-class","Mage"),("event-potion",(string?)null),("event-fragments",(string?)null),("event-potion",(string?)null)};
        async Task TryExchange(int index)
        {
            for(var retry=0;retry<8;retry++)
            {
                var e=await ActivityTestInputs.First(p);var choice=choices[index];var cost=e.Options.Single(o=>o.RuleId==choice.Item1).CostTokens;
                if(e.Available<cost)return;
                try{await p.Activities.ExchangeAsync(p.Player,e.EventId,$"concurrent-{index}-{retry}",ActivityTestInputs.Request(p,e,choice.Item1,hero:choice.Item2),Ct);return;}
                catch(DomainValidationException){ }
            }
        }
        await Task.WhenAll(Enumerable.Range(0,choices.Length).Select(TryExchange));
        var state=await ActivityTestInputs.First(p);Assert.Equal(12,state.Spent);Assert.Equal(0,state.Available);
        Assert.True(state.Rewards.Where(r=>r.RewardKind=="potion").Sum(r=>r.Quantity)<=1);Assert.Equal(12,state.Rewards.Sum(r=>r.TokenCost));
        foreach(var reward in state.Rewards)await p.Activities.ClaimAsync(p.Player,reward.RewardId,"claim-"+reward.RewardId.ToString("N"),Ct);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task TwoEventsNeverCombineTheirBoundBalances()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p,1);
        var one=await ActivityTestInputs.First(p);var next=GameConfigCatalog.Current.SeasonActivity!.Windows(p.Season)[1];p.Clock.Now=next.StartsAt.AddHours(1);
        var two=(await p.Activities.GetAsync(p.Player,Ct,p.Season.SeasonId)).Events.Single(e=>e.EventId==next.EventId);Assert.Equal(0,two.Available);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Activities.ExchangeAsync(p.Player,two.EventId,"no-rollover",ActivityTestInputs.Request(p,two,"event-fragments"),Ct));
        await ActivityTestInputs.Earn(db,p,1);var current=(await p.Activities.GetAsync(p.Player,Ct,p.Season.SeasonId)).Events;
        Assert.Equal(4,current.Single(e=>e.EventId==one.EventId).Available);Assert.Equal(4,current.Single(e=>e.EventId==two.EventId).Available);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task OldSeasonPendingClaimsCreditOnlyOldFragmentsAndPermanentSoulsWithOriginalSource()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p);
        var e=await ActivityTestInputs.First(p);var fragment=await p.Activities.ExchangeAsync(p.Player,e.EventId,"reserve-fragments",ActivityTestInputs.Request(p,e,"event-fragments",2),Ct);
        e=await ActivityTestInputs.First(p);var soul=await p.Activities.ExchangeAsync(p.Player,e.EventId,"reserve-soul",ActivityTestInputs.Request(p,e,"event-warrior"),Ct);
        e=await ActivityTestInputs.First(p);var hero=await p.Activities.ExchangeAsync(p.Player,e.EventId,"reserve-class",ActivityTestInputs.Request(p,e,"event-class",hero:"Priest"),Ct);
        p.Clock.Now=p.Season.EndsAtUtc.AddDays(1);
        var next=SeasonDefinition.FromCalendarDays("next-event-season",DateOnly.FromDateTime(p.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),GameConfigCatalog.Current.Version,"season-equipment-v1");
        await p.Seasons.PublishAsync(next,GameConfigCatalog.Current.ContentHash,Ct);await p.Seasons.EnsurePlayerAsync(p.Player,next.ContextFor(0),Ct);
        await p.Seasons.ApplyAsync(p.Player,next.ContextFor(0),0,7,0,"test.new-season-fragments","new-season",FantasyCard.Server.Seasons.SeasonWalletPurpose.General,Ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_wallets SET archived_at=$1 WHERE player_id=$2 AND season_id=$3",p.Clock.Now,p.Player,p.Season.SeasonId);
        foreach(var reward in new[]{fragment.Reward,soul.Reward,hero.Reward})await p.Activities.ClaimAsync(p.Player,reward.RewardId,"late-"+reward.RewardId.ToString("N"),Ct);
        var wallet=await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct);Assert.Equal(20,wallet!.EquipmentFragments);Assert.NotNull(wallet.ArchivedAt);
        Assert.Equal(7,(await p.Seasons.GetWalletAsync(p.Player,next.ContextFor(0),Ct))!.EquipmentFragments);
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(6,await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(2,await db.ScalarAsync<long>("SELECT priest_soul FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(3,await db.ScalarAsync<long>("SELECT count(*) FROM season_activity_reward_ledger WHERE player_id=$1 AND season_id=$2",p.Player,p.Season.SeasonId));
        Assert.Equal(2,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='activity.claim' AND season_id=$2 AND currency IN ('WarriorSoul','PriestSoul')",p.Player,p.Season.SeasonId));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task RedeemAndClaimReplayAreDurableAcrossRestartAndDifferentClaimKeysCannotDuplicate()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p,1);var e=await ActivityTestInputs.First(p);
        var request=ActivityTestInputs.Request(p,e,"event-fragments");var result=await p.Activities.ExchangeAsync(p.Player,e.EventId,"same-reservation",request,Ct);
        var restarted=new SeasonActivityRepository(db.DataSource,p.Clock,new PublishedConfigCatalogs(GameConfigCatalog.Current));
        Assert.Equal(result,await restarted.ExchangeAsync(p.Player,e.EventId,"same-reservation",request,Ct));
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>restarted.ExchangeAsync(p.Player,e.EventId,"same-reservation",request with {Quantity=2},Ct));
        var claimed=await Task.WhenAll(Enumerable.Range(0,4).Select(i=>restarted.ClaimAsync(p.Player,result.Reward.RewardId,"claim-key-"+i,Ct)));
        Assert.All(claimed,c=>Assert.Equal(claimed[0],c));Assert.Equal(10,(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!.EquipmentFragments);
        Assert.Equal(1,await db.ScalarAsync<long>("SELECT count(*) FROM season_activity_reward_ledger WHERE player_id=$1",p.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task UnknownRedAndCurrencyChoicesAndForeignClaimsNeverConsumeTokensOrMintAnything()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p,1);var e=await ActivityTestInputs.First(p);
        foreach(var kind in new[]{"red-material","red-equipment","gold","diamonds"})
            await Assert.ThrowsAsync<DomainValidationException>(()=>p.Activities.ExchangeAsync(p.Player,e.EventId,"invalid-"+kind,ActivityTestInputs.Request(p,e,kind),Ct));
        Assert.Equal(4,(await ActivityTestInputs.First(p)).Available);Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM red_equipment_weekly_quotas"));
        var held=await p.Activities.ExchangeAsync(p.Player,e.EventId,"held-own",ActivityTestInputs.Request(p,e,"event-fragments"),Ct);
        var other=await CraftingTestInputs.PlayerAsync(db,p.Clock);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Activities.ClaimAsync(other,held.Reward.RewardId,"wrong-owner",Ct));
        Assert.Equal("Pending",(await ActivityTestInputs.First(p)).Rewards.Single().State);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task AlteredCompletionTimeCannotAwardAndTheOriginalCheckpointStillRecovers()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);var done=await ActivityTestInputs.Extract(db,p);
        var altered=done with {Snapshot=done.Snapshot with {Players=done.Snapshot.Players.Select(v=>v with {ExtractionCompletedAt=v.ExtractionCompletedAt!.Value.AddSeconds(-1)}).ToArray()}};
        await Assert.ThrowsAsync<InvalidDataException>(()=>ActivityTestInputs.Observe(db,p,altered));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",done.Match));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_activity_token_ledger WHERE player_id=$1",p.Player));
        await ActivityTestInputs.Observe(db,p,done);Assert.Equal(4,(await ActivityTestInputs.First(p)).Earned);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task RecoveryAfterTheWindowUsesTheOriginalCompletionInstantRatherThanTheRecoveryClock()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);
        var window=GameConfigCatalog.Current.SeasonActivity!.Windows(p.Season)[0];var done=await ActivityTestInputs.Extract(db,p,window.EndsAt.AddSeconds(-1));
        p.Clock.Now=window.EndsAt.AddDays(2);await ActivityTestInputs.Observe(db,p,done);
        var e=await ActivityTestInputs.First(p);Assert.Equal("Ended",e.State);Assert.Equal(4,e.Earned);Assert.True(e.CanExchange);
        var held=await p.Activities.ExchangeAsync(p.Player,e.EventId,"late-original-pool",ActivityTestInputs.Request(p,e,"event-fragments"),Ct);
        await p.Activities.ClaimAsync(p.Player,held.Reward.RewardId,"late-original-claim",Ct);
        Assert.Equal(10,(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!.EquipmentFragments);
        Assert.Equal(0,(await p.Activities.GetAsync(p.Player,Ct,p.Season.SeasonId)).Events.Single(v=>v.EventId!=e.EventId).Earned);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ClaimCommitFailurePreservesTheSamePendingEntitlementWithoutPartialCurrencyCredit()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p,1);var e=await ActivityTestInputs.First(p);
        var held=await p.Activities.ExchangeAsync(p.Player,e.EventId,"hold-before-fault",ActivityTestInputs.Request(p,e,"event-fragments"),Ct);
        await db.ExecuteAsync("CREATE FUNCTION fail_activity_claim() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated activity claim fault'; END $$; CREATE TRIGGER activity_claim_fault BEFORE INSERT ON season_activity_reward_ledger FOR EACH ROW EXECUTE FUNCTION fail_activity_claim();");
        await Assert.ThrowsAsync<PostgresException>(()=>p.Activities.ClaimAsync(p.Player,held.Reward.RewardId,"same-fault-claim",Ct));
        Assert.Equal(0,(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!.EquipmentFragments);
        e=await ActivityTestInputs.First(p);Assert.Equal(1,e.Available);Assert.Equal("Pending",Assert.Single(e.Rewards).State);
        await db.ExecuteAsync("DROP TRIGGER activity_claim_fault ON season_activity_reward_ledger;");
        await p.Activities.ClaimAsync(p.Player,held.Reward.RewardId,"same-fault-claim",Ct);
        Assert.Equal(10,(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!.EquipmentFragments);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_activity_accounts SET spent=0 WHERE player_id=$1",p.Player);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).ActivityBudgetMismatchCount>0);
    }
}
