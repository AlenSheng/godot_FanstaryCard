using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Http.V1;
using FantasyCard.Server.ProtobufHttp;
using Google.Protobuf;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class ServerApiBoundaryTests
{
    [Theory]
    [InlineData("application/protobuf;q=0.1, application/json;q=0.9", true, false)]
    [InlineData("application/protobuf;q=0, */*;q=1", false, null)]
    [InlineData("application/json", false, null)]
    [InlineData("application/protobuf", false, true)]
    public void Accept_negotiation_honors_quality_and_explicit_exclusion(string accept, bool legacy, bool? expected)
    {
        var context = new DefaultHttpContext();
        context.Request.Headers.Accept = accept;
        Assert.Equal(expected, ProtobufHttpMiddleware.SelectBinary(context, legacy));
    }

    [Fact]
    public async Task Real_http_binds_binary_and_preserves_int64_errors_and_empty_responses()
    {
        await using var app = CreateApp(false);
        await app.StartAsync(TestContext.Current.CancellationToken);
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using var request = new HttpRequestMessage(HttpMethod.Put, "/api/v1/players/me")
        {
            Content = Content(new UpdatePlayerProfileRequest { DisplayName = "Binary", ExpectedVersion = long.MaxValue })
        };
        using var response = await client.SendAsync(request, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType!.MediaType);
        Assert.Equal("nosniff", response.Headers.GetValues("X-Content-Type-Options").Single());
        var profile = PlayerProfileResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken));
        Assert.Equal(long.MaxValue, profile.Version);
        Assert.Equal("Binary", profile.DisplayName);
        using var malformed = new ByteArrayContent([255]);
        malformed.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
        using var bad = await client.PutAsync("/api/v1/players/me", malformed, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
        Assert.Equal(400, HttpError.Parser.ParseFrom(await bad.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken)).Status);
        using var limited = await client.GetAsync("/api/v1/bootstrap", TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
        Assert.Equal(12, HttpError.Parser.ParseFrom(await limited.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken)).RetryAfterSeconds);
        using var deleted = await client.DeleteAsync("/api/v1/matches/tickets/00000000-0000-0000-0000-000000000001", TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
        Assert.Empty(await deleted.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task Json_requires_explicit_compatibility_and_never_replays_a_bad_body()
    {
        await using var app = CreateApp(false);
        await app.StartAsync(TestContext.Current.CancellationToken);
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        using var json = new StringContent("{}", System.Text.Encoding.UTF8, "application/json");
        using var rejected = await client.PutAsync("/api/v1/players/me", json, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, rejected.StatusCode);
        Assert.Equal(415, HttpError.Parser.ParseFrom(await rejected.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken)).Status);
    }

    [Theory]
    [InlineData(401)]
    [InlineData(403)]
    [InlineData(409)]
    public async Task Error_statuses_are_typed_and_private(int status)
    {
        await using var app = CreateApp(false);
        await app.StartAsync(TestContext.Current.CancellationToken);
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        using var response = await client.GetAsync("/api/v1/players/me?status=" + status, TestContext.Current.CancellationToken);
        Assert.Equal(status, (int)response.StatusCode);
        Assert.Equal(status, HttpError.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(TestContext.Current.CancellationToken)).Status);
        Assert.True(response.Headers.CacheControl!.NoStore);
    }

    [Fact]
    public async Task Empty_contract_validates_supplied_body_before_mutation()
    {
        await using var app = CreateApp(false);
        await app.StartAsync(TestContext.Current.CancellationToken);
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        using var content = new ByteArrayContent([255]);
        content.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
        using var request = new HttpRequestMessage(HttpMethod.Delete, "/api/v1/matches/tickets/00000000-0000-0000-0000-000000000001") { Content = content };
        using var response = await client.SendAsync(request, TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    private static ByteArrayContent Content(IMessage message)
    {
        var content = new ByteArrayContent(message.ToByteArray());
        content.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
        return content;
    }

    private static WebApplication CreateApp(bool legacy)
    {
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?> { ["ProtobufHttp:AllowLegacyJson"] = legacy.ToString() });
        builder.Services.AddProtobufHttp(builder.Configuration);
        var app = builder.Build();
        app.UseMiddleware<ProtobufHttpMiddleware>();
        app.MapPut("/api/v1/players/me", (GameBody<FantasyCard.Contracts.Players.UpdatePlayerProfileRequest> body) =>
            Results.Ok(new PlayerProfileResponse { DisplayName = body.Value.DisplayName ?? "", Version = body.Value.ExpectedVersion }))
            .AddEndpointFilter<ProtobufHttpFilter>();
        app.MapGet("/api/v1/players/me", (int status) => Results.Problem(statusCode: status)).AddEndpointFilter<ProtobufHttpFilter>();
        app.MapGet("/api/v1/bootstrap", async (HttpContext context) =>
        {
            context.Response.StatusCode = 429;
            context.Response.Headers.RetryAfter = "12";
            await context.Response.WriteAsJsonAsync(new { title = "Too many requests", status = 429 }, context.RequestAborted);
        });
        app.MapDelete("/api/v1/matches/tickets/{ticketId:guid}", () => Results.NoContent()).AddEndpointFilter<ProtobufHttpFilter>();
        return app;
    }
}
