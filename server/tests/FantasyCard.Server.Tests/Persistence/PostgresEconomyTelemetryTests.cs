using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Telemetry;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresEconomyTelemetryTests
{
    public static bool HasTestDatabase=>PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualReserveRefundAndAppliedReplayHaveDistinctImmutableObservationTimesAndSupplyEffects()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"refresh-time-and-account-flow");await db.MigrateAsync();
        var f=await Create(db);using var economy=new EconomyRepository(db.DataSource,f.Clock);var at=f.Clock.Now;
        await economy.ReserveRewardRefreshAsync(f.Player,f.Match,f.Room,0,7,"applied",Ct);
        var held=await Report(db,f,at.AddSeconds(-1),at.AddSeconds(1));Assert.Equal("0",Assert.Single(held.Totals).SystemBurn);
        f.Clock.Now=at.AddSeconds(1);var receipt=new RewardRefreshReceiptSnapshot("applied",new(ChaosMapLayer.Outer,[],1),1);
        await economy.MarkRewardRefreshAppliedAsync(f.Player,"applied",receipt,Ct);
        var original=await db.ScalarAsync<DateTime>("SELECT applied_at FROM reward_refresh_operations WHERE player_id=$1 AND request_id='applied'",f.Player);
        Assert.Equal(DateTimeKind.Utc,original.Kind);Assert.Equal(at.AddSeconds(1).UtcTicks/10*10,original.Ticks); // PostgreSQL stores whole microseconds.
        f.Clock.Now=at.AddSeconds(10);await economy.MarkRewardRefreshAppliedAsync(f.Player,"applied",receipt,Ct);
        Assert.Equal(original,await db.ScalarAsync<DateTime>("SELECT applied_at FROM reward_refresh_operations WHERE player_id=$1 AND request_id='applied'",f.Player));
        var applied=await Report(db,f,at.AddSeconds(-1),at.AddSeconds(2));var total=Assert.Single(applied.Totals);
        Assert.Equal("7",total.SystemBurn);Assert.Equal("7",total.EscrowReserved);Assert.Equal("7",total.EscrowConsumed);Assert.Equal("-7",total.LedgerDelta);Assert.Equal("0",total.ReconciliationDifference);
        Assert.True(applied.RecognizedCurrencyCoverageComplete);
        var replayWindow=await Report(db,f,at.AddSeconds(9),at.AddSeconds(11));Assert.Empty(replayWindow.Totals);
        f.Clock.Now=at.AddSeconds(12);await economy.ReserveRewardRefreshAsync(f.Player,f.Match,f.Room,0,5,"refunded",Ct);
        f.Clock.Now=at.AddSeconds(13);Assert.True(await economy.RefundReservedRewardRefreshAsync(f.Player,"refunded",Ct));
        var refunded=await Report(db,f,at.AddSeconds(11),at.AddSeconds(14));var returned=Assert.Single(refunded.Totals);
        Assert.Equal("0",returned.SystemMint);Assert.Equal("0",returned.SystemBurn);Assert.Equal("5",returned.EscrowReserved);Assert.Equal("5",returned.EscrowReturned);Assert.Equal("0",returned.LedgerDelta);
        Assert.Equal(93L,await db.ScalarAsync<long>("SELECT gold FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",f.Player,f.Season.SeasonId));
        var fingerprint=await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db);await Report(db,f,at.AddSeconds(-1),at.AddSeconds(14));Assert.Equal(fingerprint,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="immutable-applied-time",original,applied,refunded,emptyReplayWindow=replayWindow.Totals.Count==0,readOnlyFingerprintUnchanged=true});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task HistoricalAppliedTimeIsNotInventedOnReplayAndUnknownCurrenciesRemainVisible()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"unknown-history");await db.MigrateAsync();
        var f=await Create(db);using var economy=new EconomyRepository(db.DataSource,f.Clock);var at=f.Clock.Now;
        await economy.ReserveRewardRefreshAsync(f.Player,f.Match,f.Room,0,3,"historical",Ct);
        var receipt=new RewardRefreshReceiptSnapshot("historical",new(ChaosMapLayer.Outer,[],1),1);
        await Sql(db,"UPDATE reward_refresh_operations SET state='Applied',response_json=$1::jsonb WHERE player_id=$2 AND request_id='historical'",JsonSerializer.Serialize(new{requestId="historical",choice=receipt.Choice,roomRevision=1}),f.Player);
        f.Clock.Now=at.AddSeconds(1);await economy.MarkRewardRefreshAppliedAsync(f.Player,"historical",receipt,Ct);
        Assert.True(await db.ScalarAsync<bool>("SELECT applied_at IS NULL FROM reward_refresh_operations WHERE player_id=$1 AND request_id='historical'",f.Player));
        await Sql(db,"INSERT INTO economy_ledger(ledger_id,player_id,currency,delta,balance_after,reason,created_at) VALUES($1,$2,'ClassSoul',4,4,'mail.claim',$3)",Guid.NewGuid(),f.Player,at);
        var before=await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db);var report=await Report(db,f,at.AddSeconds(-1),at.AddSeconds(2));
        Assert.Equal(1,report.AppliedRefreshesWithoutOriginalTime);Assert.False(report.RecognizedCurrencyCoverageComplete);
        Assert.Equal("4",report.Totals.Single(t=>t.Currency=="ClassSoul").UnclassifiedMagnitude);Assert.Equal("0",report.Totals.Single(t=>t.Currency=="ClassSoul").SystemMint);
        Assert.Equal(before,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="historical-gaps-retained",report,noHistoricalBackfill=true,readOnlyFingerprintUnchanged=true});
    }

    private static Task<EconomyFlowReport> Report(PostgresTestSchema db,Fixture f,DateTimeOffset from,DateTimeOffset to)=>new EconomyTelemetryRepository(db.DataSource,f.Clock).ReadAsync(from,to,Ct);
    private sealed record Fixture(Guid Player,Guid Match,Guid Room,SeasonDefinition Season,TelemetryClock Clock);
    private sealed class TelemetryClock(DateTimeOffset now):TimeProvider {public DateTimeOffset Now{get;set;}=now;public override DateTimeOffset GetUtcNow()=>Now;}
    private static async Task<Fixture> Create(PostgresTestSchema db)
    {
        var clock=new TelemetryClock(DateTimeOffset.UtcNow);var config=GameConfigCatalog.Current;
        var season=SeasonDefinition.FromCalendarDays("report-season",DateOnly.FromDateTime(clock.Now.DateTime).AddDays(-1),config.Version,"season-equipment-v1");
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,config.ContentHash,Ct);
        var profile=await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(Guid.NewGuid().ToString("N"),"Telemetry report",new byte[32],clock.Now,clock.Now.AddHours(1),Ct);
        await seasons.EnsurePlayerAsync(profile.UserId,season.ContextFor(0),Ct);await Sql(db,"UPDATE player_season_wallets SET gold=100 WHERE player_id=$1 AND season_id=$2",profile.UserId,season.SeasonId);
        var match=Guid.NewGuid();var room=Guid.NewGuid();
        await Sql(db,"INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version) VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1','season-equipment-v1')",match,room,config.Version,clock.Now,season.SeasonId);
        await Sql(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,profile.UserId);
        return new(profile.UserId,match,room,season,clock);
    }
    private static async Task Sql(PostgresTestSchema db,string sql,params object[] parameters)
    {await using var q=db.DataSource.CreateCommand(sql);foreach(var p in parameters)q.Parameters.AddWithValue(p);await q.ExecuteNonQueryAsync(Ct);}
}
