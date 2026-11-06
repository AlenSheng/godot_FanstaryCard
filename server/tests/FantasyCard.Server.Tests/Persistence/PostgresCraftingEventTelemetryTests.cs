using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresCraftingEventTelemetryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task DurablePityFactsSurviveReplayAndLaterWishChangesWhileHistoricalMissingFactsStayUnknown()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"crafting-pity-events");
        var p=await CraftingTestInputs.CreateAsync(db,_=>0);await CraftingTestInputs.FundAsync(db,p,16,0);
        CraftEquipmentRequest? first=null;
        for(var i=0;i<3;i++)
        {
            var wallet=(await p.Progression.GetSeasonCraftingAsync(p.Player,Ct)).Wallet!;
            var request=new CraftEquipmentRequest(p.Season.SeasonId,"Purple","Head","Fire","Vitality",wallet.Version);first??=request;
            var responses=await Task.WhenAll(Enumerable.Range(0,2).Select(_=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"event-"+i,request,Ct)));
            Assert.Equal(responses[0],responses[1]);
        }
        var repository=new CraftingEventTelemetryRepository(db.DataSource);var from=p.Clock.Now.AddSeconds(-1);var to=p.Clock.Now.AddSeconds(1);
        var report=await repository.ReadAsync(from,to,Ct);
        Assert.True(report.CraftingSourceComplete);Assert.Equal(4,report.Events.Count);Assert.Equal(4,report.Events.Select(e=>e.EventId).Distinct().Count());
        var pity=Assert.Single(report.Events,e=>e.EventName=="pity_triggered");Assert.True(pity.Observation.PityTriggered);
        Assert.Equal(2,pity.Observation.WishFailuresBefore);Assert.Equal(0,pity.Observation.WishFailuresAfter);
        Assert.All(report.Events,e=>{Assert.Null(e.Observation.Dimensions.DifficultyId);Assert.Null(e.Observation.Dimensions.HeroClass);Assert.Null(e.Observation.Dimensions.BuildType);Assert.Null(e.Observation.Dimensions.GrowthStage);Assert.Equal("Unknown",e.Observation.Dimensions.PlayerKind);Assert.Equal("Lobby",e.Observation.Dimensions.CellType);Assert.Equal("Mint",e.Observation.PhysicalFlow);});
        var original=JsonSerializer.Serialize(report);
        await new ProgressionRepository(db.DataSource,p.Clock).CraftSeasonEquipmentAsync(p.Player,"event-0",first!,Ct);
        Assert.Equal(original,JsonSerializer.Serialize(await repository.ReadAsync(from,to,Ct)));
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_crafting_wishes SET failures=1");
        Assert.Equal(original,JsonSerializer.Serialize(await repository.ReadAsync(from,to,Ct)));
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO season_equipment_actions(action_id,player_id,season_id,action_kind,request_id,request_hash,before_item,after_item,response_json,created_at)
            SELECT gen_random_uuid(),player_id,season_id,action_kind,'historical-missing',request_hash,before_item,after_item,response_json,created_at
            FROM season_equipment_actions WHERE request_id='event-0'
            """);
        var fingerprint=await FingerprintAsync(db);var incomplete=await repository.ReadAsync(from,to,Ct);
        Assert.Equal(1,incomplete.MissingHistoricalActions);Assert.False(incomplete.CraftingSourceComplete);Assert.Equal(4,incomplete.Events.Count);
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-crafting-pity-events",report,incomplete,replayStable=true,currentWishNotUsed=true,readOnlyFingerprintUnchanged=true});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task KnownRecipeDoesNotEmitAnotherLearningAndReforgeObservesOneRetainedBodyInsteadOfMintOrDestruction()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"recipe-reforge-events");
        var p=await CraftingTestInputs.CreateAsync(db);var a=await CraftingTestInputs.ItemAsync(db,p);var b=await CraftingTestInputs.ItemAsync(db,p);
        var learned=await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn-first",new(p.Season.SeasonId,a,1),Ct);
        var known=await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn-known",new(p.Season.SeasonId,b,1),Ct);
        Assert.True(known.AlreadyLearned);Assert.False(known.Equipment.RecipeExtracted);
        var quote=await p.Progression.GetReforgeQuoteAsync(p.Player,p.Season.SeasonId,learned.Recipe.RecipeId,b,Ct);
        var request=new ReforgeEquipmentRequest(p.Season.SeasonId,learned.Recipe.RecipeId,b,1,quote.ExpectedWalletVersion);
        var reforged=await p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"event-reforge",request,Ct);
        Assert.Equal(b,reforged.Equipment.InstanceId);
        Assert.Equal(reforged,await new ProgressionRepository(db.DataSource,p.Clock).ReforgeSeasonEquipmentAsync(p.Player,"event-reforge",request,Ct));
        var repository=new CraftingEventTelemetryRepository(db.DataSource);var fingerprint=await FingerprintAsync(db);
        var report=await repository.ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct);
        Assert.True(report.CraftingSourceComplete);Assert.Equal(1,report.ObservedNoEventActions);Assert.Equal(2,report.Events.Count);
        var learn=Assert.Single(report.Events,e=>e.EventName=="recipe_learned");Assert.Equal(a,learn.Observation.ItemId);Assert.Equal("RetainedSample",learn.Observation.PhysicalFlow);
        var craft=Assert.Single(report.Events,e=>e.EventName=="craft_completed");Assert.Equal(b,craft.Observation.ItemId);Assert.Equal("Mutation",craft.Observation.PhysicalFlow);Assert.Equal(quote.FragmentCost,craft.Observation.FragmentsSpent);
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1",p.Player));
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        // A malformed historical observation is visible as a gap, never a crash or guessed event.
        await CraftingTestInputs.SqlAsync(db,"UPDATE season_equipment_actions SET telemetry_json='{}'::jsonb WHERE request_id='learn-known'");
        var malformed=await repository.ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct);
        Assert.Equal(1,malformed.InvalidObservations);Assert.False(malformed.CraftingSourceComplete);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-recipe-reforge-events",report,malformed,bodyIdentityRetained=true,readOnlyFingerprintUnchanged=true});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ObservationInsertFailureRollsBackPaymentItemWishAndActionAndOriginalKeyCanRetryOnce()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"crafting-observation-rollback");
        var p=await CraftingTestInputs.CreateAsync(db,_=>0);var wallet=await CraftingTestInputs.FundAsync(db,p,4,0);
        var request=new CraftEquipmentRequest(p.Season.SeasonId,"Purple","Head","Fire","Vitality",wallet.Version);
        var fingerprint=await FingerprintAsync(db);
        await CraftingTestInputs.SqlAsync(db,"""
            CREATE FUNCTION reject_crafting_observation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.telemetry_json IS NOT NULL THEN RAISE EXCEPTION 'owned observation failure'; END IF; RETURN NEW; END $$;
            CREATE TRIGGER fail_observation BEFORE INSERT ON season_equipment_actions FOR EACH ROW EXECUTE FUNCTION reject_crafting_observation();
            """);
        await Assert.ThrowsAsync<Npgsql.PostgresException>(()=>p.Progression.CraftSeasonEquipmentAsync(p.Player,"rollback-event",request,Ct));
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        await CraftingTestInputs.SqlAsync(db,"DROP TRIGGER fail_observation ON season_equipment_actions; DROP FUNCTION reject_crafting_observation()");
        var paid=await p.Progression.CraftSeasonEquipmentAsync(p.Player,"rollback-event",request,Ct);
        Assert.Equal(0,paid.Wallet.BlueprintMarks);Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM season_equipment_actions"));
        var report=await new CraftingEventTelemetryRepository(db.DataSource).ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct);
        Assert.Equal("craft_completed",Assert.Single(report.Events).EventName);Assert.True(report.CraftingSourceComplete);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-crafting-event-rollback",report,failedAttemptRolledBack=true,originalKeyRetryExactlyOnce=true});
    }

    private static Task<string> FingerprintAsync(PostgresTestSchema db)=>db.ScalarAsync<string>("""
        SELECT md5(concat_ws('|',
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id)::text,'[]') FROM player_season_wallets x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY instance_id)::text,'[]') FROM equipments x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id,quality,slot,element,wished_effect)::text,'[]') FROM player_crafting_wishes x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY action_id)::text,'[]') FROM season_equipment_actions x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY ledger_id)::text,'[]') FROM economy_ledger x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY movement_id)::text,'[]') FROM inventory_movements x)))
        """);
}
