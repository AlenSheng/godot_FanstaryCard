using System.Net;
using System.Text;
using FantasyCard.Server.Identity;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Tests.Identity;

public sealed class SteamTicketVerifierTests
{
    [Fact]
    public async Task Valid_ticket_uses_official_parameters_and_returns_verified_steam_id()
    {
        Uri? requestedUri = null;
        using var httpClient = new HttpClient(new StubHandler(request =>
        {
            requestedUri = request.RequestUri;
            return Json(HttpStatusCode.OK, """{"response":{"params":{"result":"OK","steamid":"76561198000000000"}}}""");
        }));
        using var verifier = new SteamTicketVerifier(httpClient, Options.Create(EnabledOptions()));

        var steamId = await verifier.VerifyAsync("A0B1", TestContext.Current.CancellationToken);

        Assert.Equal("76561198000000000", steamId);
        Assert.NotNull(requestedUri);
        Assert.Contains("appid=480", requestedUri.Query, StringComparison.Ordinal);
        Assert.Contains("ticket=A0B1", requestedUri.Query, StringComparison.Ordinal);
        Assert.Contains("identity=fantasycard", requestedUri.Query, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("ABC")]
    [InlineData("ZZ")]
    public async Task Invalid_ticket_is_rejected_without_calling_steam(string? ticket)
    {
        var calls = 0;
        using var httpClient = new HttpClient(new StubHandler(_ =>
        {
            calls++;
            return Json(HttpStatusCode.OK, "{}");
        }));
        using var verifier = new SteamTicketVerifier(httpClient, Options.Create(EnabledOptions()));

        Assert.Null(await verifier.VerifyAsync(ticket, TestContext.Current.CancellationToken));
        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task Steam_error_payload_is_not_accepted()
    {
        using var httpClient = new HttpClient(new StubHandler(_ =>
            Json(HttpStatusCode.OK, """{"response":{"error":{"errorcode":101}}}""")));
        using var verifier = new SteamTicketVerifier(httpClient, Options.Create(EnabledOptions()));

        Assert.Null(await verifier.VerifyAsync("A0", TestContext.Current.CancellationToken));
    }

    [Fact]
    public async Task Disabled_verifier_never_calls_external_service()
    {
        var calls = 0;
        using var httpClient = new HttpClient(new StubHandler(_ =>
        {
            calls++;
            return Json(HttpStatusCode.OK, "{}");
        }));
        using var verifier = new SteamTicketVerifier(httpClient, Options.Create(new SteamAuthOptions()));

        Assert.Null(await verifier.VerifyAsync("A0", TestContext.Current.CancellationToken));
        Assert.Equal(0, calls);
    }

    private static SteamAuthOptions EnabledOptions() => new()
    {
        Enabled = true,
        AppId = 480,
        PublisherKey = "secret-key",
        Identity = "fantasycard"
    };

    private static HttpResponseMessage Json(HttpStatusCode statusCode, string json) => new(statusCode)
    {
        Content = new StringContent(json, Encoding.UTF8, "application/json")
    };

    private sealed class StubHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) => Task.FromResult(respond(request));
    }
}
