using System.Net;
using System.Text;
using Microsoft.Extensions.Options;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Tests.Identity;

public sealed class GoogleIdTokenVerifierTests
{
    [Fact]
    public async Task Valid_token_info_returns_only_the_stable_subject()
    {
        using var client = new HttpClient(new StubHandler("""{"iss":"https://accounts.google.com","aud":"web-client","sub":"google-sub","exp":"4102444800","iat":"1700000000","email_verified":"true","email":"private@example.com"}"""));
        var verifier = new GoogleIdTokenVerifier(client, Options.Create(new GoogleAuthOptions
        {
            Enabled = true,
            WebClientId = "web-client"
        }));

        var identity = await verifier.VerifyAsync("opaque-id-token", CancellationToken.None);

        Assert.Equal("google-sub", identity?.Subject);
    }

    [Theory]
    [InlineData("wrong-client", "google-sub")]
    [InlineData("web-client", "")]
    public async Task Audience_or_subject_mismatch_is_rejected(string audience, string subject)
    {
        using var client = new HttpClient(new StubHandler($"{{\"iss\":\"accounts.google.com\",\"aud\":\"{audience}\",\"sub\":\"{subject}\",\"exp\":\"4102444800\",\"email_verified\":\"true\"}}"));
        var verifier = new GoogleIdTokenVerifier(client, Options.Create(new GoogleAuthOptions
        {
            Enabled = true,
            WebClientId = "web-client"
        }));

        Assert.Null(await verifier.VerifyAsync("opaque-id-token", CancellationToken.None));
    }

    private sealed class StubHandler(string payload) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            });
    }
}
