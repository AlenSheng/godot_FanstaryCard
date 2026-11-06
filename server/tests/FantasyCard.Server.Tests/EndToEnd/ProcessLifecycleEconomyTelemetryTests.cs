using System.Globalization;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Server.Tests.Persistence;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Fact(Skip="Requires an owned local PostgreSQL database.",SkipUnless=nameof(HasPrivateDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"admin-report-HTTP");await db.MigrateAsync();
        using var deadline=Deadline(45);var ct=deadline.Token;var port=ReservePort();var key=Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        await using var host=FullHost.Start(db.ConnectionString,port,"d04-admin-report",adminApiKey:key);
        using var client=Client(port);client.DefaultRequestHeaders.Accept.Clear();client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        await host.WaitForHealthAsync(client,"/health/ready",HttpStatusCode.OK,ct);
        client.DefaultRequestHeaders.Add("X-Forwarded-Proto","https");
        using(var missing=await client.GetAsync("/api/admin/telemetry/economy",ct))Assert.Equal(HttpStatusCode.Unauthorized,missing.StatusCode);
        client.DefaultRequestHeaders.Add("X-Admin-Key",key);client.DefaultRequestHeaders.Remove("X-Forwarded-Proto");
        using(var insecure=await client.GetAsync("/api/admin/telemetry/economy",ct))Assert.Equal(HttpStatusCode.Forbidden,insecure.StatusCode);
        client.DefaultRequestHeaders.Add("X-Forwarded-Proto","https");
        using(var response=await client.GetAsync("/api/admin/telemetry/economy",ct))
        {
            Assert.Equal(HttpStatusCode.OK,response.StatusCode);Assert.Equal("application/json",response.Content.Headers.ContentType!.MediaType);
            Assert.True(response.Headers.CacheControl!.Private);Assert.True(response.Headers.CacheControl.NoStore);
            using var body=JsonDocument.Parse(await response.Content.ReadAsByteArrayAsync(ct));Assert.Empty(body.RootElement.GetProperty("totals").EnumerateArray());
            Assert.False(body.RootElement.GetProperty("perAttemptPlaytimeRatesAvailable").GetBoolean());
            PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-admin-HTTP",host.ProcessId,loopbackJSON=true,realTLSHandshakeClaimed=false,
                missingKeyStatus=401,insecureStatus=403,privateNoStore=true,report=body.RootElement.Clone()});
        }
        var end=DateTimeOffset.UtcNow;var uri="/api/admin/telemetry/economy?from="+Uri.EscapeDataString(end.AddDays(-8).ToString("O",CultureInfo.InvariantCulture))+"&to="+Uri.EscapeDataString(end.ToString("O",CultureInfo.InvariantCulture));
        using(var invalid=await client.GetAsync(uri,ct))Assert.Equal(HttpStatusCode.BadRequest,invalid.StatusCode);
        using(var minimum=await client.GetAsync("/api/admin/telemetry/economy?to=0001-01-01T00%3A00%3A00Z",ct))Assert.Equal(HttpStatusCode.BadRequest,minimum.StatusCode);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM reward_refresh_operations"));
    }
}
