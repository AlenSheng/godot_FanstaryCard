using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Config;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresJourneyRewardEntitlementTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ActualCheckpointCreditCreatesOriginalPendingRewardsOnceAcrossConcurrentSettlementRecovery()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        var done=await JourneyTestInputs.DeadAfterClears(db,p,"Elite","Boss");
        await Task.WhenAll(Enumerable.Range(0,6).Select(_=>JourneyTestInputs.Observe(db,p,done)));
        Assert.Equal(510,(await p.Journey.GetAsync(p.Player,Ct)).Experience);
        Assert.Equal(2,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements WHERE player_id=$1",p.Player));
        Assert.Equal(2,await db.ScalarAsync<long>("""
            SELECT count(*) FROM season_journey_reward_entitlements WHERE player_id=$1 AND season_id=$2
                AND config_version=$3 AND config_sha256=$4 AND state='Pending' AND experience_at_unlock=510
                AND ((reward_level=1 AND required_experience=200) OR (reward_level=2 AND required_experience=415))
            """,p.Player,p.Season.SeasonId,p.Config.Version,p.Config.ContentHash));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='journey.claim'"));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE reason='journey.claim'"));
        var before=await db.ScalarAsync<string>("SELECT jsonb_agg(to_jsonb(e) ORDER BY reward_level)::text FROM season_journey_reward_entitlements e");
        await JourneyTestInputs.Observe(db,p,done);
        Assert.Equal(before,await db.ScalarAsync<string>("SELECT jsonb_agg(to_jsonb(e) ORDER BY reward_level)::text FROM season_journey_reward_entitlements e"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    // These fixtures seed a declared high-level aggregate to test storage,
    // concurrency and pack freezing; they do not represent completed routes.
    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData(30,8959)][InlineData(42,12525)][InlineData(60,12525)]
    public async Task FullTrackFreezesTwelveActualDrawsOnceAndReloadNeverUsesAnotherRandomResult(int days,int maximum)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db,days);
        await SeedExperience(db,p,maximum);var rolls=0;
        await Task.WhenAll(Enumerable.Range(0,6).Select(iteration=>Unlock(db,p,upperBound=>{Interlocked.Increment(ref rolls);return 0;})));
        Assert.Equal(24,rolls);Assert.Equal(30,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements"));
        Assert.Equal(maximum,await db.ScalarAsync<int>("SELECT required_experience FROM season_journey_reward_entitlements WHERE reward_level=30"));
        Assert.Equal(12,await db.ScalarAsync<long>("SELECT sum(jsonb_array_length(pack_card_ids))::bigint FROM season_journey_reward_entitlements"));
        var frozen=await db.ScalarAsync<string>("SELECT jsonb_agg(pack_card_ids ORDER BY reward_level)::text FROM season_journey_reward_entitlements WHERE reward_kind='CardPack'");
        using(var packs=JsonDocument.Parse(frozen))
        {
            Assert.Equal(4,packs.RootElement.GetArrayLength());
            foreach(var pack in packs.RootElement.EnumerateArray())
            {
                Assert.Equal(3,pack.GetArrayLength());Assert.Single(pack.EnumerateArray().Select(c=>c.GetString()).Distinct());
            }
        }
        var reopened=GameConfigCatalog.Load(p.Config.ExportPublishedBytes());p.Clock.Now=p.Season.EndsAtUtc.AddDays(2);
        await Unlock(db,p,_=>throw new InvalidOperationException("A durable pack cannot be redrawn."),config:reopened);
        Assert.Equal(frozen,await db.ScalarAsync<string>("SELECT jsonb_agg(pack_card_ids ORDER BY reward_level)::text FROM season_journey_reward_entitlements WHERE reward_kind='CardPack'"));
        Assert.Equal(30,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements WHERE state='Pending' AND claimed_at IS NULL AND grant_json IS NULL"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task UnlockRollbackLeavesNoPartialEntitlementAndCommittedRetryIsStable()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        await SeedExperience(db,p,p.Config.SeasonJourney!.Threshold(5,p.Season.DurationDays));
        await Unlock(db,p,_=>0,commit:false);
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements"));
        await Unlock(db,p,_=>0);var frozen=await db.ScalarAsync<string>("SELECT pack_card_ids::text FROM season_journey_reward_entitlements WHERE reward_level=5");
        Assert.Equal(5,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements"));
        await Unlock(db,p,_=>throw new InvalidOperationException("Committed results must be reused."));
        Assert.Equal(frozen,await db.ScalarAsync<string>("SELECT pack_card_ids::text FROM season_journey_reward_entitlements WHERE reward_level=5"));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='journey.claim'"));
    }

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData("threshold")][InlineData("pack")]
    public async Task ChangedOriginalThresholdOrNonpackCardCannotBeSilentlyRepairedOrRedrawn(string corruption)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await JourneyTestInputs.Create(db);
        await SeedExperience(db,p,p.Config.SeasonJourney!.Threshold(5,p.Season.DurationDays));await Unlock(db,p,_=>0);
        if(corruption=="threshold")await CraftingTestInputs.SqlAsync(db,"UPDATE season_journey_reward_entitlements SET required_experience=required_experience-1 WHERE reward_level=5");
        else
        {
            var excluded=p.Config.Cards.First(card=>!SeasonShopConfig.PackEligible(card)).CardId;
            await CraftingTestInputs.SqlAsync(db,"UPDATE season_journey_reward_entitlements SET pack_card_ids=$1::jsonb WHERE reward_level=5",JsonSerializer.Serialize(new[]{excluded,excluded,excluded}));
        }
        var before=await db.ScalarAsync<string>("SELECT to_jsonb(e)::text FROM season_journey_reward_entitlements e WHERE reward_level=5");
        await Assert.ThrowsAsync<InvalidDataException>(()=>Unlock(db,p,_=>throw new InvalidOperationException("Invalid original rewards cannot reroll.")));
        Assert.Equal(before,await db.ScalarAsync<string>("SELECT to_jsonb(e)::text FROM season_journey_reward_entitlements e WHERE reward_level=5"));
        Assert.Equal(5,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task OriginalThirteenCheckpointStillCreditsExperienceWithoutManufacturingNewRewards()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var root=PublishedConfigTestInputs.FindRoot();
        var original=GameConfigCatalog.Load(File.ReadAllBytes(Path.Combine(root,"server/config/archive/season-v1-config-13/fantasycard.config.bytes")));
        var catalogs=new PublishedConfigCatalogs(GameConfigCatalog.Current,Path.Combine(root,"server/config/archive"));
        Assert.Equal(original.ContentHash,catalogs.Resolve(original.Version).ContentHash);
        var p=await JourneyTestInputs.Create(db,config:original,configurations:catalogs);await JourneyTestInputs.Observe(db,p,await JourneyTestInputs.DeadAfterClears(db,p,"Elite","Boss"));
        Assert.Equal(510,(await p.Journey.GetAsync(p.Player,Ct,p.Season.SeasonId)).Experience);
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_reward_entitlements"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    internal static Task SeedExperience(PostgresTestSchema db,JourneyPlayer p,int experience)=>CraftingTestInputs.SqlAsync(db,"""
        INSERT INTO player_season_journeys(player_id,season_id,config_version,experience,version) VALUES($1,$2,$3,$4,1)
        """,p.Player,p.Season.SeasonId,p.Config.Version,experience);

    internal static async Task Unlock(PostgresTestSchema db,JourneyPlayer p,Func<int,int> random,bool commit=true,GameConfigCatalog? config=null)
    {
        await using var c=await db.DataSource.OpenConnectionAsync(Ct);await using var t=await c.BeginTransactionAsync(Ct);
        await using(var q=new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE",c,t))
        {q.Parameters.AddWithValue(p.Player);Assert.NotNull(await q.ExecuteScalarAsync(Ct));}
        await SeasonJourneyRepository.EnsureRewardsWithinTransactionAsync(c,t,p.Player,p.Season,config??p.Config,p.Clock.Now,random,Ct);
        if(commit)await t.CommitAsync(Ct);else await t.RollbackAsync(Ct);
    }
}
