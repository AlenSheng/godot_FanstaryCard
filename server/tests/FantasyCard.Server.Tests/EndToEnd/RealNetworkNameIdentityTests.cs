using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Identity;
using FantasyCard.Contracts.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Tests.Persistence;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_http_switching_names_registers_distinct_uids_and_relogin_restores_the_original_account()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        var ct = timeout.Token;
        var now = DateTimeOffset.UtcNow;
        await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInExternalAsync(
            "steam", "verified-platform-id", "Reserved", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}") };
        await server.WaitUntilReadyAsync(client, ct);

        async Task<LocalSignInResponse> LoginAsync(string name)
        {
            using var response = await client.PostAsJsonAsync("/api/v1/auth/local", new LocalSignInRequest("same-device-id", name), WebJson, ct);
            response.EnsureSuccessStatusCode();
            return (await response.Content.ReadFromJsonAsync<LocalSignInResponse>(WebJson, ct))!;
        }

        var first = await LoginAsync("旅人甲");
        var second = await LoginAsync("旅人乙");
        var returning = await LoginAsync("  旅人甲  ");
        Assert.NotEqual(first.Player.UserId, second.Player.UserId);
        Assert.Equal(first.Player.UserId, returning.Player.UserId);
        Assert.NotEqual(first.AccessToken, returning.AccessToken);
        foreach (var signIn in new[] { first, second, returning })
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/bootstrap");
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", signIn.AccessToken);
            using var response = await client.SendAsync(request, ct);
            response.EnsureSuccessStatusCode();
            var bootstrap = (await response.Content.ReadFromJsonAsync<BootstrapResponse>(WebJson, ct))!;
            Assert.Equal(signIn.Player.UserId, bootstrap.Player.UserId);
            Assert.Equal(signIn.Player.DisplayName, bootstrap.Player.DisplayName);
        }

        using var reserved = await client.PostAsJsonAsync("/api/v1/auth/local", new LocalSignInRequest("same-device-id", "reserved"), WebJson, ct);
        Assert.Equal(HttpStatusCode.Conflict, reserved.StatusCode);
        using var blank = await client.PostAsJsonAsync("/api/v1/auth/local", new LocalSignInRequest("same-device-id", "   "), WebJson, ct);
        Assert.Equal(HttpStatusCode.BadRequest, blank.StatusCode);
        using var rename = new HttpRequestMessage(HttpMethod.Put, "/api/v1/players/me");
        rename.Headers.Authorization = new AuthenticationHeaderValue("Bearer", second.AccessToken);
        rename.Headers.Add("Idempotency-Key", "rename-account");
        rename.Content = JsonContent.Create(new UpdatePlayerProfileRequest("旅人丙", null, second.Player.Version), options: WebJson);
        using var renameResponse = await client.SendAsync(rename, ct);
        Assert.Equal(HttpStatusCode.Conflict, renameResponse.StatusCode);
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
    }
}
