using System.Net;
using System.Net.Http.Headers;
using System.Text;
using FantasyCard.Contracts.Http;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Server.Realtime;
using Google.Protobuf;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresGoogleBranchTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Requires an owned PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Google_binary_login_and_account_deletion_complete_through_actual_http_and_database()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        var ct = timeout.Token;
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = "Development" });
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Identity:Google:Enabled"] = "true",
            ["Identity:Google:WebClientId"] = "branch-public-audience",
            ["ProtobufHttp:AllowLegacyJson"] = "false"
        });
        builder.Services.AddSingleton(database.DataSource);
        builder.Services.AddSingleton(TimeProvider.System);
        builder.Services.AddSingleton<ServerMetrics>();
        builder.Services.AddSingleton<ClientSettingsRepository>();
        builder.Services.AddSingleton<RealtimeTicketStore>();
        builder.Services.AddFantasyCardRequestLimits(builder.Configuration);
        builder.Services.AddProtobufHttp(builder.Configuration);
        builder.Services.AddIdentityModule(builder.Configuration);
        builder.Services.AddHttpClient<GoogleIdTokenVerifier>().ConfigurePrimaryHttpMessageHandler(() => new GoogleProviderFixture());
        await using var app = builder.Build();
        app.UseRouting();
        app.UseRateLimiter();
        app.UseMiddleware<ProtobufHttpMiddleware>();
        app.MapIdentityEndpoints();
        app.MapAccountDeletionEndpoints();
        await app.StartAsync(ct);
        using var client = new HttpClient
        {
            BaseAddress = new Uri(app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single())
        };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));

        async Task<HttpResponseMessage> SendAsync(HttpMethod method, string path, IMessage? body = null)
        {
            using var request = new HttpRequestMessage(method, path);
            if (body is not null)
            {
                request.Content = new ByteArrayContent(body.ToByteArray());
                request.Content.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
            }
            return await client.SendAsync(request, ct);
        }

        using var signIn = await SendAsync(HttpMethod.Post, "/api/v1/auth/google", new Wire.GoogleSignInRequest { IdToken = "owned-provider-fixture", DisplayName = "Google branch" });
        Assert.Equal(HttpStatusCode.OK, signIn.StatusCode);
        Assert.Equal(HttpProtocolRegistry.MediaType, signIn.Content.Headers.ContentType!.MediaType);
        var identity = Wire.LocalSignInResponse.Parser.ParseFrom(await signIn.Content.ReadAsByteArrayAsync(ct));
        Assert.True(Guid.TryParse(identity.Player.UserId, out var playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM external_identities WHERE player_id=$1 AND provider='google'", playerId));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", identity.AccessToken);
        await using (var quota = database.DataSource.CreateCommand("INSERT INTO red_equipment_weekly_quotas(week_key,red_dropped_this_week,source,player_id,equipment_id,claimed_at) VALUES (CURRENT_DATE,1,'ChaosBoss',$1,$2,CURRENT_TIMESTAMP)"))
        {
            quota.Parameters.AddWithValue(playerId);
            quota.Parameters.AddWithValue(Guid.NewGuid());
            await quota.ExecuteNonQueryAsync(ct);
        }

        using var ticketResponse = await SendAsync(HttpMethod.Post, "/api/v1/auth/ws-ticket", new Wire.Empty());
        Assert.Equal(HttpStatusCode.OK, ticketResponse.StatusCode);
        var ticket = Wire.RealtimeTicketResponse.Parser.ParseFrom(await ticketResponse.Content.ReadAsByteArrayAsync(ct));
        var tickets = app.Services.GetRequiredService<RealtimeTicketStore>();
        var consumed = Assert.IsType<TicketSession>(tickets.Consume(ticket.Ticket));
        Assert.Equal(playerId, consumed.PlayerId);
        Assert.Equal(SessionToken.Hash(identity.AccessToken), consumed.SessionHash);
        Assert.Null(tickets.Consume(ticket.Ticket));

        using var first = await SendAsync(HttpMethod.Post, "/api/v1/account-deletion", new Wire.Empty());
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        var initial = Wire.AccountDeletionStatus.Parser.ParseFrom(await first.Content.ReadAsByteArrayAsync(ct));
        using var replay = await SendAsync(HttpMethod.Post, "/api/v1/account-deletion", new Wire.Empty());
        Assert.Equal(HttpStatusCode.OK, replay.StatusCode);
        Assert.Equal(initial.RequestId, Wire.AccountDeletionStatus.Parser.ParseFrom(await replay.Content.ReadAsByteArrayAsync(ct)).RequestId);
        using var cancel = await SendAsync(HttpMethod.Delete, "/api/v1/account-deletion");
        Assert.Equal(HttpStatusCode.NoContent, cancel.StatusCode);
        Assert.Empty(await cancel.Content.ReadAsByteArrayAsync(ct));
        using var current = await SendAsync(HttpMethod.Get, "/api/v1/account-deletion");
        Assert.Equal("Cancelled", Wire.AccountDeletionStatus.Parser.ParseFrom(await current.Content.ReadAsByteArrayAsync(ct)).Status);

        using var pending = await SendAsync(HttpMethod.Post, "/api/v1/account-deletion", new Wire.Empty());
        Assert.Equal(HttpStatusCode.OK, pending.StatusCode);
        var requested = Wire.AccountDeletionStatus.Parser.ParseFrom(await pending.Content.ReadAsByteArrayAsync(ct));
        Assert.NotEqual(initial.RequestId, requested.RequestId);
        Assert.Equal(1, await new AccountDeletionRepository(database.DataSource).CompleteDueAsync(DateTimeOffset.UtcNow.AddDays(8), ct));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM players WHERE user_id=$1", playerId));
        Assert.Equal("Completed", await database.ScalarAsync<string>("SELECT status FROM account_deletion_requests WHERE request_id=$1", Guid.Parse(requested.RequestId)));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM red_equipment_weekly_quotas WHERE red_dropped_this_week=1 AND player_id=$1", Guid.Empty));
        using var expiredIdentity = await SendAsync(HttpMethod.Get, "/api/v1/account-deletion");
        Assert.Equal(HttpStatusCode.Unauthorized, expiredIdentity.StatusCode);

        using var json = new StringContent("{}", Encoding.UTF8, "application/json");
        using var jsonResponse = await client.PostAsync("/api/v1/auth/google", json, ct);
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, jsonResponse.StatusCode);
        Assert.Equal(415, Wire.HttpError.Parser.ParseFrom(await jsonResponse.Content.ReadAsByteArrayAsync(ct)).Status);
        await app.StopAsync(ct);
    }

    private sealed class GoogleProviderFixture : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("""{"iss":"https://accounts.google.com","aud":"branch-public-audience","sub":"branch-google-subject","exp":"4102444800","email_verified":"true"}""", Encoding.UTF8, "application/json")
            });
    }
}
