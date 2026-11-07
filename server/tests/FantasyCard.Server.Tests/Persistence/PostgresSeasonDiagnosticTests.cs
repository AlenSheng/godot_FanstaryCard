using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonDiagnosticTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private static SeasonTelemetryDiagnosticsRepository Repository(PostgresTestSchema db,TimeProvider clock)=>new(db.DataSource,clock,new(db.DataSource));
    private static DiagnosticSlice One(SeasonTelemetryDiagnosticsReport r,string kind)=>Assert.Single(r.Rows,e=>e.Kind==kind);
    private static async Task<PostgresTestSchema> Open(string label)
    {
        var db=await PostgresTestSchema.CreateAsync(false);try{PostgresSeasonMarketTests.RecordTelemetrySchema(db,label);await db.MigrateAsync();return db;}catch{await db.DisposeAsync();throw;}
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task MarketMaturitySeparatesYoungAndSeasonShortenedListingsAndKeepsOriginalTradeTemplates()
    {
        await using var db=await Open("diagnostic-market");var p=await CraftingTestInputs.CreateAsync(db);var now=DateTimeOffset.UtcNow;p.Clock.Now=now.AddHours(-49);
        var buyer=await CraftingTestInputs.PlayerAsync(db,p.Clock);await p.Seasons.EnsurePlayerAsync(buyer,p.Season.ContextFor(0),Ct);
        await p.Seasons.ApplyAsync(buyer,p.Season.ContextFor(0),1000,0,0,"test.diagnostic.capital","fund",SeasonWalletPurpose.General,Ct);
        using var market=new EconomyRepository(db.DataSource,p.Clock);var ids=new List<Guid>();
        async Task<FantasyCard.Contracts.Progression.MarketListingResponse> List(string key)
        {
            var id=await CraftingTestInputs.ItemAsync(db,p);ids.Add(id);return await market.ListAsync(p.Player,key,new(id,100,"Gold",100,p.Season.SeasonId,1),Ct);
        }
        var oldSold=await List("old-sold");await List("old-unsold");p.Clock.Now=now.AddHours(-2);
        await market.PurchaseMarketAsync(buyer,"buy-old",oldSold.ListingId,oldSold.Version,Ct,new("Gold",100,p.Season.SeasonId));
        var youngSold=await List("young-sold");await market.PurchaseMarketAsync(buyer,"buy-young",youngSold.ListingId,youngSold.Version,Ct,new("Gold",100,p.Season.SeasonId));
        await List("young-active");var shortened=await List("season-shortened");
        // Declared historical-boundary fixtures: shorten exposure and mutate today's item, never the transaction receipt.
        await CraftingTestInputs.SqlAsync(db,"UPDATE market_listings SET season_ends_at=created_at+interval '24 hours' WHERE listing_id=$1",shortened.ListingId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET level=2,recipe_extracted=true WHERE instance_id=$1",ids[0]);p.Clock.Now=now;
        var fingerprint=await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db);var report=await Repository(db,p.Clock).ReadAsync(now.AddDays(-3),now.AddMinutes(1),Ct);
        var cohort=One(report,"Listing48HourCohort");Assert.Equal("5",cohort.Measures["listings"]);Assert.Equal("2",cohort.Measures["matureFull48Hours"]);
        Assert.Equal("1",cohort.Measures["matureSoldWithin48"]);Assert.Equal("3",cohort.Measures["rightCensoredOrShortened"]);Assert.Equal("1",cohort.Measures["youngSoldWithin48"]);Assert.Equal("1",cohort.Measures["seasonShortened"]);
        var trade=One(report,"EquipmentMaterialTrades");Assert.Equal("0",trade.Dimensions["level"]);Assert.Equal("false",trade.Dimensions["recipeExtracted"]);
        Assert.Equal("2",trade.Measures["transactions"]);Assert.Equal("200",trade.Measures["priceSum"]);Assert.Equal("0",trade.Measures["missingTemplateReceipt"]);
        Assert.Equal("2",One(report,"MarketDepth").Measures["activeListings"]);Assert.Empty(report.TruncatedSources);Assert.Equal(fingerprint,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-diagnostic-market",report,readOnlyFingerprintUnchanged=true,declaredExposureAndCurrentItemMutation=true,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ActualActivityClaimsAndShopReceiptsKeepSharedBudgetTotalSpendAndFrozenRunCohorts()
    {
        await using var db=await Open("diagnostic-activity-shop");var p=await ActivityTestInputs.Create(db);await ActivityTestInputs.Earn(db,p,1);
        var activity=await ActivityTestInputs.First(p);var exchange=await p.Activities.ExchangeAsync(p.Player,activity.EventId,"diagnostic-exchange",ActivityTestInputs.Request(p,activity,"event-fragments"),Ct);
        await p.Activities.ClaimAsync(p.Player,exchange.Reward.RewardId,"diagnostic-claim",Ct);
        await p.Seasons.ApplyAsync(p.Player,p.Season.ContextFor(0),250,0,0,"test.diagnostic.shop","fund",SeasonWalletPurpose.General,Ct);
        using var market=new EconomyRepository(db.DataSource,p.Clock);var shop=await market.GetShopAsync(p.Player,Ct);var offer=shop.Products.Single(o=>o.ProductId=="equipment_fragments");
        await market.PurchaseAsync(p.Player,"diagnostic-purchase",new(offer.ProductId,2,p.Season.SeasonId,shop.ResetKey,shop.RotationKey,offer.PriceGold,shop.Policy!.CatalogVersion),Ct);
        var fingerprint=await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db);var report=await Repository(db,p.Clock).ReadAsync(p.Clock.Now.AddDays(-1),p.Clock.Now.AddMinutes(1),Ct);
        var spend=One(report,"ShopSpendAndActivityOverlap");Assert.Equal("2",spend.Measures["units"]);Assert.Equal("240",spend.Measures["goldSpent"]);
        Assert.Equal("1",spend.Measures["postPurchaseBalanceBelow100"]);Assert.Equal("0",spend.Measures["missingPostPurchaseBalance"]);Assert.Equal("1",spend.Measures["buyersWithActivityClaimsSameShanghaiDay"]);
        var issued=One(report,"ActivityBudgetAndPeak");Assert.Equal("bound_fragments",issued.Dimensions["rewardKind"]);Assert.Equal("10",issued.Measures["actualRewardAmount"]);Assert.Equal("3",issued.Measures["tokensSpent"]);Assert.Equal("1",issued.Measures["peakDailyClaims"]);
        var account=Assert.Single(report.Rows,e=>e.Kind=="ActivityAccountsAsOfQuery"&&e.Measures["accounts"]=="1");Assert.Equal("1",account.Measures["remainingEarnedTokens"]);Assert.Equal("8",account.Measures["maximumUnissuedTokensForKnownAccounts"]);
        var run=One(report,"RunCohorts");Assert.Equal("AccountAgeAtMost7Days",run.Dimensions["cohort"]);Assert.Equal("Mage",run.Dimensions["class"]);Assert.Equal("0",run.Dimensions["entryEffectiveMaxLevel"]);Assert.Equal("1",run.Measures["extracted"]);
        Assert.Equal("0",One(report,"ZeroBalancesAsOfQuery").Measures["zeroGold"]);Assert.Equal(fingerprint,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-diagnostic-activity-shop",report,readOnlyFingerprintUnchanged=true,declaredTerminalCheckpoint=true,skillOrCausalInference=false,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ExactCommittedHoldCountsFirstExtractionAndDeathRecoveryOnceWithoutBorrowingOtherItemReceipt()
    {
        await using var db=await Open("diagnostic-extraction");var p=await CraftingTestInputs.CreateAsync(db);p.Clock.Now=DateTimeOffset.UtcNow;var start=p.Clock.Now;
        var item=await CraftingTestInputs.ItemAsync(db,p);var other=await CraftingTestInputs.ItemAsync(db,p);await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='InMatchBackpack' WHERE instance_id=$1",item);
        using var metrics=new ServerMetrics();var settlements=new SettlementRepository(db.DataSource,p.Clock,metrics);using var details=JsonDocument.Parse("{}");
        async Task<Guid> Settle(string outcome,string destination)
        {
            var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version) VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)",match,Guid.NewGuid(),p.Season.ConfigVersion,p.Clock.Now,p.Season.SeasonId,p.Season.StatsVersion);
            await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,p.Player);
            var receipt=await settlements.SettleAsync(match,p.Player,outcome,details.RootElement,[new("Equipment",item.ToString("D"),false,Destination:destination)],Ct,p.Season.ContextFor(0),p.Season.ConfigVersion);
            Assert.Equal(1,await settlements.CommitHoldsAsync(receipt.SettlementId,Ct));return receipt.SettlementId;
        }
        await Settle("Dead","RelicPile");var receipt=await Settle("Extracted","Inventory");
        var hold=await db.ScalarAsync<Guid>("SELECT hold_id FROM settlement_asset_holds WHERE settlement_id=$1",receipt);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at) VALUES(gen_random_uuid(),$1,$2,'RelicPile','Inventory','settlement.extract',$3,CURRENT_TIMESTAMP)",p.Player,other,hold.ToString("D"));
        p.Clock.Now=p.Clock.Now.AddMinutes(1);var fingerprint=await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db);var report=await Repository(db,p.Clock).ReadAsync(start.AddSeconds(-1),p.Clock.Now,Ct);
        Assert.Equal("1",One(report,"FirstCommittedEquipmentExtraction").Measures["firstCommittedExtractions"]);var recovery=One(report,"DeathEquipmentRecovery");Assert.Equal("1",recovery.Measures["committedRecoveryObserved"]);Assert.Equal("1",recovery.Measures["sameActorRecovery"]);Assert.Equal("0",recovery.Measures["notRecoveredYetRightCensored"]);
        Assert.Equal(fingerprint,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-diagnostic-extraction",report,readOnlyFingerprintUnchanged=true,declaredSettlementBoundary=true,unrelatedItemCannotBorrowHold=true,completedGameplayCampaigns=0});
    }
}
