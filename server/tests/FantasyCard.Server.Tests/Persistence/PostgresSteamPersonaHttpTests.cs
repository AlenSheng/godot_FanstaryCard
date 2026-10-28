using System.Net;
using System.Net.Http.Headers;
using System.Text;
using FantasyCard.Contracts.Http;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;
using Google.Protobuf;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSteamPersonaHttpTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Requires owned PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Binary_steam_login_assigns_a_server_suffix_and_preserves_it_on_relogin()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(45));
        var ct = timeout.Token;
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Identity:Steam:Enabled"] = "true", ["Identity:Steam:AppId"] = "480",
            ["Identity:Steam:PublisherKey"] = "owned-fixture-key", ["Identity:Steam:Identity"] = "owned-service",
            ["ProtobufHttp:AllowLegacyJson"] = "false"
        });
        builder.Services.AddSingleton(database.DataSource);
        builder.Services.AddSingleton(TimeProvider.System);
        builder.Services.AddSingleton<ServerMetrics>();
        builder.Services.AddSingleton<ClientSettingsRepository>();
        builder.Services.AddSingleton(new SteamDisplayNameGenerator(() => 1193));
        builder.Services.AddFantasyCardRequestLimits(builder.Configuration);
        builder.Services.AddProtobufHttp(builder.Configuration);
        builder.Services.AddIdentityModule(builder.Configuration);
        using var verifier = new SteamTicketVerifier(new HttpClient(new SteamFixture()), Options.Create(new SteamAuthOptions
        {
            Enabled = true, AppId = 480, PublisherKey = "owned-fixture-key", Identity = "owned-service"
        }));
        builder.Services.Replace(ServiceDescriptor.Singleton(verifier));
        await using var app = builder.Build();
        app.UseRouting();
        app.UseRateLimiter();
        app.UseMiddleware<ProtobufHttpMiddleware>();
        app.MapIdentityEndpoints();
        await app.StartAsync(ct);
        using var client = new HttpClient { BaseAddress = new Uri(app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single()) };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));

        async Task<Wire.LocalSignInResponse> LoginAsync(string persona)
        {
            using var body = new ByteArrayContent(new Wire.SteamSignInRequest { Ticket = "A0B1", DisplayName = persona }.ToByteArray());
            body.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
            using var response = await client.PostAsync("/api/v1/auth/steam", body, ct);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType!.MediaType);
            return Wire.LocalSignInResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct));
        }

        var first = await LoginAsync("Unity");
        Assert.Equal("Unity#1193", first.Player.DisplayName);
        var returning = await LoginAsync("Renamed Steam persona");
        Assert.Equal(first.Player.UserId, returning.Player.UserId);
        Assert.Equal(first.Player.DisplayName, returning.Player.DisplayName);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM external_identities WHERE provider='steam' AND external_subject='76561198000000000'"));
        await app.StopAsync(ct);
    }

    private sealed class SteamFixture : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("""{"response":{"params":{"result":"OK","steamid":"76561198000000000"}}}""", Encoding.UTF8, "application/json")
            });
    }
}
