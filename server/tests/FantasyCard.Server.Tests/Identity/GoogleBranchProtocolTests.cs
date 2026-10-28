using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Identity;
using FantasyCard.Server.Identity;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Identity;

public sealed class GoogleBranchProtocolTests
{
    [Fact]
    public void Google_sign_in_uses_the_same_typed_binary_boundary()
    {
        var contract = Assert.IsType<HttpEndpointContract>(HttpProtocolRegistry.Find("POST", "/api/v1/auth/google"));
        var input = new Wire.GoogleSignInRequest { IdToken = "fixture-token", DisplayName = "Google traveller" };
        var decoded = Assert.IsType<GoogleSignInRequest>(HttpDtoMapper.DecodeRequest(contract, input.ToByteArray(), typeof(GoogleSignInRequest)));
        Assert.Equal(input.IdToken, decoded.IdToken);
        Assert.Equal(input.DisplayName, decoded.DisplayName);
        Assert.Equal("LocalSignInResponse", contract.Response);
    }

    [Fact]
    public void Account_deletion_preserves_nullable_dates_and_request_identity()
    {
        var contract = Assert.IsType<HttpEndpointContract>(HttpProtocolRegistry.Find("GET", "/api/v1/account-deletion"));
        var now = DateTimeOffset.UtcNow;
        var status = new AccountDeletionStatus(Guid.NewGuid(), "Requested", now, now.AddDays(7), null, null);
        var wire = Wire.AccountDeletionStatus.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract, status));
        Assert.Equal(status.RequestId.ToString(), wire.RequestId);
        Assert.Equal("Requested", wire.Status);
        Assert.False(wire.HasCompletedAt);
        Assert.False(wire.HasCancelledAt);
        Assert.Equal("Empty", HttpProtocolRegistry.Find("DELETE", "/api/v1/account-deletion")!.Response);
    }

    [Fact]
    public void Legacy_ticket_route_reuses_the_registered_ticket_response()
    {
        var current = HttpProtocolRegistry.Find("POST", "/api/v1/realtime/ticket")!;
        var legacy = HttpProtocolRegistry.Find("POST", "/api/v1/auth/ws-ticket")!;
        Assert.Equal(current.Request, legacy.Request);
        Assert.Equal(current.Response, legacy.Response);
        Assert.Equal(HttpProtocolRegistry.Endpoints.Count, HttpProtocolRegistry.Endpoints.Select(e => (e.Method, e.Path)).Distinct().Count());
    }
}
