using System.Net;
using System.Net.Http.Headers;
using Google.Protobuf;
using FantasyCard.Server.Common;
using FantasyCard.Server.Tests.Persistence;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Fact(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_default_single_IP_auth_limit_is_separate_from_capacity()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(60); var ct = deadline.Token; var port = ReservePort();
        using var client = Client(port, ""); await using var host = FullHost.Start(db.ConnectionString, port, "default-auth-limit");
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        var statuses = new List<int>(); var retryAfter = false;
        for (var i = 0; i < 13; i++)
        {
            using var request = LimitRequest(HttpMethod.Post, "/api/v1/auth/local", new Wire.LocalSignInRequest
                { DeviceId = "owned-limit-" + Guid.NewGuid().ToString("N"), DisplayName = "OwnedLimit" + i });
            using var response = await client.SendAsync(request, ct);
            statuses.Add((int)response.StatusCode); retryAfter |= response.Headers.RetryAfter is not null;
        }
        Assert.Equal(Enumerable.Repeat(200, 10).Concat(Enumerable.Repeat(429, 3)), statuses);
        Assert.True(retryAfter); Assert.Equal(10L, await db.ScalarAsync<long>("SELECT count(*) FROM players"));
        Assert.Equal(10, new RequestLimitOptions().AuthPermitLimit);
        Record("actual-default-auth-limit", new { statuses, permitLimit = 10, retryAfter, originalCapacityAcceptance = false,
            scope = "actual loopback full Program, same IP, unchanged fixed window; no capacity workload" });
    }

    [Fact(Skip = "Requires an owned local PostgreSQL database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_prelogged_account_still_observes_default_economy_write_limit()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(60); var ct = deadline.Token; var port = ReservePort();
        using var client = Client(port, ""); await using var host = FullHost.Start(db.ConnectionString, port, "default-economy-limit");
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        using (var request = LimitRequest(HttpMethod.Post, "/api/v1/auth/local", new Wire.LocalSignInRequest
               { DeviceId = "prelogged-limit-" + Guid.NewGuid().ToString("N"), DisplayName = "PreloggedLimit" }))
        using (var response = await client.SendAsync(request, ct))
        {
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var session = Wire.LocalSignInResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct));
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", session.AccessToken);
        }
        var goldBefore = await db.ScalarAsync<long>("SELECT gold FROM player_wallets");
        var statuses = new List<int>(); var retryAfter = false;
        for (var i = 0; i < 32; i++)
        {
            // Authenticated requests use real endpoint/business validation. A
            // nonexistent owned preparation cannot alter any asset or ledger.
            using var request = LimitRequest(HttpMethod.Delete, "/api/v1/preparations/" + Guid.NewGuid().ToString("D"), new Wire.Empty());
            using var response = await client.SendAsync(request, ct);
            statuses.Add((int)response.StatusCode); retryAfter |= response.Headers.RetryAfter is not null;
        }
        Assert.All(statuses.Take(30), code => Assert.Equal(404, code));
        Assert.All(statuses.Skip(30), code => Assert.Equal(429, code)); Assert.True(retryAfter);
        Assert.Equal(goldBefore, await db.ScalarAsync<long>("SELECT gold FROM player_wallets"));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger"));
        Assert.Equal(30, new RequestLimitOptions().EconomyWritePermitLimit);
        Record("actual-default-economy-limit", new { statuses, permitLimit = 30, retryAfter, assetsUnchanged = true,
            originalCapacityAcceptance = false, scope = "actual PB login then authenticated same-IP writes, unchanged limits; invalid business target is explicit" });
    }

    private static HttpRequestMessage LimitRequest(HttpMethod method, string path, IMessage body)
    {
        var request = new HttpRequestMessage(method, path) { Content = new ByteArrayContent(body.ToByteArray()) };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/protobuf");
        request.Headers.Add("Idempotency-Key", Guid.NewGuid().ToString("N"));
        return request;
    }
}
