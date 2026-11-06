using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonMarketTests
{
    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    [InlineData("Gold","White",1,1)] [InlineData("Diamond","Orange",2000,200)]
    public async Task ActualMarketReportSeparatesTransferAndTaxWithoutDoubleCountingOrMutation(string currency,string quality,long price,long fee)
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);RecordTelemetrySchema(db,"market-"+currency);await db.MigrateAsync();
        var f=await Create(db);f.Owner.Clock.Now=f.Owner.Clock.Now.AddMinutes(1); // Declared fixture capital precedes the measured transaction window.
        var item=await Item(db,f,quality);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        var listing=await market.ListAsync(f.Owner.Player,"telemetry-list",Request(item,currency,price,f),Ct);
        await market.PurchaseMarketAsync(f.Buyer,"telemetry-buy",listing.ListingId,listing.Version,Ct,new MarketPurchaseExpectation(currency,price,f.Owner.Season.SeasonId));
        var before=await TelemetryFinancialFingerprint(db);var report=await new EconomyTelemetryRepository(db.DataSource,f.Owner.Clock).ReadAsync(f.Owner.Clock.Now.AddSeconds(-1),f.Owner.Clock.Now.AddSeconds(1),Ct);
        var total=Assert.Single(report.Totals,t=>t.Currency==currency);Assert.Equal("0",total.SystemMint);Assert.Equal(fee.ToString(System.Globalization.CultureInfo.InvariantCulture),total.SystemBurn);
        Assert.Equal((price-fee).ToString(System.Globalization.CultureInfo.InvariantCulture),total.Transfer);Assert.Equal((-fee).ToString(System.Globalization.CultureInfo.InvariantCulture),total.LedgerDelta);
        Assert.Equal("0",total.ReconciliationDifference);Assert.True(report.RecognizedCurrencyCoverageComplete);Assert.Equal(0,report.UnmatchedMarketTransactions);
        Assert.False(report.PerAttemptPlaytimeRatesAvailable);Assert.Equal(before,await TelemetryFinancialFingerprint(db));
        var again=await new EconomyTelemetryRepository(db.DataSource,f.Owner.Clock).ReadAsync(report.FromUtc,report.ToUtc,Ct);Assert.Equal(report.Totals,again.Totals);
        WriteTelemetryProof(new{kind="actual-market-report",currency,price,fee,report,readOnlyFingerprintUnchanged=true,queryReplayDoesNotMint=true});
    }

    internal static async Task<string> TelemetryFinancialFingerprint(PostgresTestSchema db)=>await db.ScalarAsync<string>("""
        SELECT jsonb_build_object('wallet',(SELECT jsonb_agg(to_jsonb(w) ORDER BY player_id) FROM player_wallets w),
          'materials',(SELECT jsonb_agg(to_jsonb(m) ORDER BY player_id) FROM player_materials m),
          'season',(SELECT jsonb_agg(to_jsonb(s) ORDER BY player_id,season_id) FROM player_season_wallets s),
          'ledger',(SELECT jsonb_agg(to_jsonb(l) ORDER BY ledger_id) FROM economy_ledger l),
          'market',(SELECT jsonb_agg(to_jsonb(t) ORDER BY transaction_id) FROM market_transactions t),
          'refresh',(SELECT jsonb_agg(to_jsonb(r) ORDER BY player_id,request_id) FROM reward_refresh_operations r))::text
        """);

    internal static void RecordTelemetrySchema(PostgresTestSchema db,string kind)
    {
        var output=Environment.GetEnvironmentVariable("FANTASYCARD_D04_SCHEMA_EVIDENCE");
        if(output is not null)File.AppendAllText(output,System.Text.Json.JsonSerializer.Serialize(new{schema=new Npgsql.NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath,kind})+Environment.NewLine);
    }
    internal static void WriteTelemetryProof<T>(T proof)
    {
        var output=Environment.GetEnvironmentVariable("FANTASYCARD_D04_REPORT_EVIDENCE");
        if(output is not null)File.AppendAllText(output,System.Text.Json.JsonSerializer.Serialize(proof)+Environment.NewLine);
    }
}
