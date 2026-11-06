using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresJourneyRewardClaimTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    // High-level claim/storage fixtures seed declared earned aggregates. They
    // do not stand for completed level-30 routes or real-player capacity.
    private static async Task<JourneyPlayer> Earned(PostgresTestSchema db,int days=42)
    {
        var p=await JourneyTestInputs.Create(db,days);await PostgresJourneyRewardEntitlementTests.SeedExperience(db,p,p.Config.SeasonJourney!.Threshold(30,days));
        await PostgresJourneyRewardEntitlementTests.Unlock(db,p,_=>0);return p;
    }
    private static async Task<JourneyRewardResponse> Reward(JourneyPlayer p,int level)=>
        (await p.Journey.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct)).Rewards.Single(r=>r.Level==level);
    private static Task<JourneyClaimResponse> Claim(JourneyPlayer p,JourneyRewardResponse reward,string? hero=null,string? key=null)=>
        p.Journey.ClaimRewardAsync(p.Player,reward.RewardId!.Value,key??Guid.NewGuid().ToString("N"),new(p.Season.SeasonId,hero),Ct);

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task MissingEarnedEntitlementIsUnavailableAndReadingCannotManufactureTheAbsentSource()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        await PostgresJourneyRewardEntitlementTests.SeedExperience(db,p,1150);
        var read=await p.Journey.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct);Assert.Equal("Unavailable",read.State);
        Assert.Equal(5,read.Rewards.Count(r=>r.State=="Unavailable"));Assert.All(read.Rewards,row=>Assert.False(row.CanClaim));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements"));
    }

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData(30)][InlineData(42)][InlineData(60)]
    public async Task TwentyMainRewardsCreditExactOriginalBudgetAndTwelveCopiesOnceAcrossConcurrentRetries(int days)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db,days);
        var fragments=await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,p.Season.SeasonId);
        var warrior=await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",p.Player);
        var priest=await db.ScalarAsync<long>("SELECT priest_soul FROM player_materials WHERE player_id=$1",p.Player);
        var mage=await db.ScalarAsync<long>("SELECT mage_soul FROM player_materials WHERE player_id=$1",p.Player);
        var guardian=await db.ScalarAsync<long>("SELECT guardian_soul FROM player_materials WHERE player_id=$1",p.Player);
        var main=(await p.Journey.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct)).Rewards.Where(r=>r.Level<=20).ToArray();
        foreach(var reward in main)
        {
            var key="main-"+reward.Level;var hero=reward.RequiresClassChoice?"Priest":null;
            var replies=await Task.WhenAll(Enumerable.Range(0,3).Select(_=>Claim(p,reward,hero,key)));
            Assert.All(replies,r=>Assert.Equivalent(replies[0],r,strict:true));
            var second=await Claim(p,reward,hero,"another-"+reward.Level);Assert.Equivalent(replies[0],second,strict:true);
        }
        Assert.Equal(fragments+80,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,p.Season.SeasonId));
        Assert.Equal(warrior+24,await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(priest+8,await db.ScalarAsync<long>("SELECT priest_soul FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(mage,await db.ScalarAsync<long>("SELECT mage_soul FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(guardian,await db.ScalarAsync<long>("SELECT guardian_soul FROM player_materials WHERE player_id=$1",p.Player));
        Assert.Equal(12,await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM card_copy_ledger WHERE player_id=$1 AND reason='journey.claim'",p.Player));
        Assert.Equal(20,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_grant_ledger WHERE player_id=$1",p.Player));
        Assert.Equal(20,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements WHERE player_id=$1 AND state='Claimed'",p.Player));
        Assert.Equal(0,(await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).CardCopyLedgerMismatchCount);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task FailureAfterCardCreditRollsBackAllAssetsAndRetryUsesThePreviouslyFrozenPack()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db);var reward=await Reward(p,5);
        var frozen=await db.ScalarAsync<string>("SELECT pack_card_ids::text FROM season_journey_reward_entitlements WHERE reward_id=$1",reward.RewardId!.Value);
        var before=await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE reason='journey.claim'");
        await CraftingTestInputs.SqlAsync(db,"""
            CREATE FUNCTION reject_journey_grant() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'declared journey claim fault'; END;$$;
            CREATE TRIGGER reject_journey_grant BEFORE INSERT ON season_journey_grant_ledger FOR EACH ROW EXECUTE FUNCTION reject_journey_grant();
            """);
        await Assert.ThrowsAsync<PostgresException>(()=>Claim(p,reward,key:"faulted-pack"));
        Assert.Equal(before,await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE reason='journey.claim'"));
        Assert.Equal("Pending",await db.ScalarAsync<string>("SELECT state FROM season_journey_reward_entitlements WHERE reward_id=$1",reward.RewardId.Value));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM idempotency_records WHERE scope='journey.reward.claim' AND request_id='faulted-pack'"));
        await CraftingTestInputs.SqlAsync(db,"DROP TRIGGER reject_journey_grant ON season_journey_grant_ledger; DROP FUNCTION reject_journey_grant();");
        var result=await Claim(p,reward,key:"faulted-pack");Assert.Equal(3,result.Grants.Sum(g=>g.Amount));
        using var cards=JsonDocument.Parse(frozen);Assert.Equal(cards.RootElement[0].GetString(),Assert.Single(result.Grants).CardId);
        Assert.Equal(frozen,await db.ScalarAsync<string>("SELECT pack_card_ids::text FROM season_journey_reward_entitlements WHERE reward_id=$1",reward.RewardId.Value));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task LateClaimCreditsOnlyItsOriginalArchivedWalletAndPermanentSoulKeepsOriginalLedgerContext()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db);var fragment=await Reward(p,1);var soul=await Reward(p,2);
        p.Clock.Now=p.Season.EndsAtUtc.AddDays(1);var next=SeasonDefinition.FromCalendarDays("journey-claim-next",DateOnly.FromDateTime(p.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),p.Config.Version,p.Season.StatsVersion);
        await p.Seasons.PublishAsync(next,p.Config.ContentHash,Ct);await p.Seasons.EnsurePlayerAsync(p.Player,next.ContextFor(0),Ct);
        var nextBefore=await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,next.SeasonId);
        var oldBefore=await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,p.Season.SeasonId);
        await Claim(p,fragment);await Claim(p,soul);
        Assert.Equal(oldBefore+10,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,p.Season.SeasonId));
        Assert.Equal(nextBefore,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,next.SeasonId));
        Assert.Equal(1,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='journey.claim' AND currency='WarriorSoul' AND source_kind='SeasonJourney' AND season_id=$2 AND config_version=$3 AND stats_version=$4",p.Player,p.Season.SeasonId,p.Config.Version,p.Season.StatsVersion));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task TenPermanentCosmeticsHaveRealOwnershipAndSelectionRejectsWrongSlotUnownedAndStaleVersions()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db);
        foreach(var reward in (await p.Journey.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct)).Rewards.Where(r=>r.Level>20))
            Assert.True((await Claim(p,reward)).CosmeticNewlyOwned);
        var inventory=await p.Journey.GetCosmeticsAsync(p.Player,Ct);Assert.Equal(10,inventory.Owned.Count);Assert.Null(inventory.Selection.AvatarFrameId);
        var frame=await p.Journey.SelectCosmeticAsync(p.Player,"select-frame",new("AvatarFrame","trail-seeker",inventory.Selection.Version),Ct);
        var back=await p.Journey.SelectCosmeticAsync(p.Player,"select-back",new("CardBack","waymark-seal",frame.Version),Ct);
        var title=await p.Journey.SelectCosmeticAsync(p.Player,"select-title",new("Title","relic-seeker",back.Version),Ct);
        Assert.Equal("trail-seeker",title.AvatarFrameId);Assert.Equal("waymark-seal",title.CardBackId);Assert.Equal("relic-seeker",title.TitleId);
        Assert.Equal(title,await p.Journey.SelectCosmeticAsync(p.Player,"select-title",new("Title","relic-seeker",back.Version),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Journey.SelectCosmeticAsync(p.Player,"unowned",new("Title","not-owned",title.Version),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Journey.SelectCosmeticAsync(p.Player,"wrong-slot",new("Title","first-threshold",title.Version),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Journey.SelectCosmeticAsync(p.Player,"stale",new("Title",null,back.Version),Ct));
        var restarted=new SeasonJourneyRepository(db.DataSource,p.Clock,p.Configurations);
        Assert.Equivalent(await p.Journey.GetCosmeticsAsync(p.Player,Ct),await restarted.GetCosmeticsAsync(p.Player,Ct),strict:true);
        var clear=await restarted.SelectCosmeticAsync(p.Player,"unequip",new("Title",null,title.Version),Ct);Assert.Null(clear.TitleId);
    }

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData(null)][InlineData("NotAClass")][InlineData("mage")]
    public async Task ClassSoulRequiresOneExactClassAndBadRequestsDoNotConsumeTheEntitlement(string? choice)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db);var reward=await Reward(p,3);
        await Assert.ThrowsAsync<DomainValidationException>(()=>Claim(p,reward,choice,"class-choice"));
        Assert.Equal("Pending",await db.ScalarAsync<string>("SELECT state FROM season_journey_reward_entitlements WHERE reward_id=$1",reward.RewardId!.Value));
        var response=await Claim(p,reward,"Mage","class-choice");Assert.Equal("MageSoul",Assert.Single(response.Grants).Kind);
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>Claim(p,reward,"Priest","class-choice"));
        await Assert.ThrowsAsync<DomainValidationException>(()=>Claim(p,reward,"Priest","new-class-choice"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ActualEarnedCheckpointClaimsRemainHealthyAndUnearnedOrForeignRewardsCannotBeClaimed()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p,"Elite","Boss"));
        var rewards=await p.Journey.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct);Assert.Equal(2,rewards.Rewards.Count(r=>r.CanClaim));
        Assert.Null(rewards.Rewards.Single(r=>r.Level==3).RewardId);Assert.Equal("Locked",rewards.Rewards.Single(r=>r.Level==3).State);
        foreach(var reward in rewards.Rewards.Where(r=>r.CanClaim))await Claim(p,reward);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Journey.ClaimRewardAsync(p.Player,Guid.NewGuid(),"unearned",new(p.Season.SeasonId),Ct));
        var foreign=await CraftingTestInputs.PlayerAsync(db,p.Clock);var id=rewards.Rewards[0].RewardId!.Value;
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Journey.ClaimRewardAsync(foreign,id,"foreign",new(p.Season.SeasonId),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Journey.ClaimRewardAsync(p.Player,id,"wrong-season",new("not-original"),Ct));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task MissingOriginalDisablesPendingClaimsButAlreadyCommittedResponsesStillReplayWithoutMinting()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db);var pack=await Reward(p,5);
        var original=await Claim(p,pack,key:"original-pack");
        var old=GameConfigCatalog.Load(File.ReadAllBytes(Path.Combine(Config.PublishedConfigTestInputs.FindRoot(),"server/config/archive/season-v1-config-13/fantasycard.config.bytes")));
        var missing=new SeasonJourneyRepository(db.DataSource,p.Clock,new PublishedConfigCatalogs(old));
        var read=await missing.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct);Assert.Equal("Unavailable",read.State);Assert.Equal(30,read.Rewards.Count);Assert.All(read.Rewards,row=>Assert.False(row.CanClaim));
        var fragment=read.Rewards.Single(r=>r.Level==1);
        await Assert.ThrowsAsync<DomainValidationException>(()=>missing.ClaimRewardAsync(p.Player,fragment.RewardId!.Value,"missing-source",new(p.Season.SeasonId),Ct));
        Assert.Equivalent(original,await missing.ClaimRewardAsync(p.Player,pack.RewardId!.Value,"original-pack",new(p.Season.SeasonId),Ct),strict:true);
        Assert.Equivalent(original,await missing.ClaimRewardAsync(p.Player,pack.RewardId!.Value,"new-replay-key",new(p.Season.SeasonId),Ct),strict:true);
        Assert.Equal(1,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_grant_ledger"));
        Assert.Equal(3,await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM card_copy_ledger WHERE reason='journey.claim'"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task NextSeasonDuplicateCosmeticsKeepFirstOwnershipAndSelectionWithoutCurrencyCompensation()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await Earned(db);
        foreach(var reward in (await p.Journey.GetRewardsAsync(p.Player,p.Season.SeasonId,Ct)).Rewards.Where(r=>r.Level>20))await Claim(p,reward);
        var inventory=await p.Journey.GetCosmeticsAsync(p.Player,Ct);
        var selected=await p.Journey.SelectCosmeticAsync(p.Player,"original-frame",new("AvatarFrame","trail-seeker",inventory.Selection.Version),Ct);
        p.Clock.Now=p.Season.EndsAtUtc.AddDays(1);
        var next=SeasonDefinition.FromCalendarDays("cosmetic-next",DateOnly.FromDateTime(p.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),p.Config.Version,p.Season.StatsVersion);
        var second=await JourneyTestInputs.Existing(db,p.Player,next,p.Clock,p.Config,p.Configurations);
        await PostgresJourneyRewardEntitlementTests.SeedExperience(db,second,12525);await PostgresJourneyRewardEntitlementTests.Unlock(db,second,_=>0);
        foreach(var reward in (await second.Journey.GetRewardsAsync(second.Player,next.SeasonId,Ct)).Rewards.Where(r=>r.Level>20))
            Assert.False((await Claim(second,reward)).CosmeticNewlyOwned);
        var after=await second.Journey.GetCosmeticsAsync(second.Player,Ct);Assert.Equal(10,after.Owned.Count);Assert.Equal(selected,after.Selection);
        Assert.All(after.Owned,row=>Assert.Equal(p.Season.SeasonId,row.SourceSeasonId));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='journey.claim'"));
        Assert.Equal(10,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_grant_ledger WHERE season_id=$1 AND NOT cosmetic_newly_owned",next.SeasonId));
    }
}
