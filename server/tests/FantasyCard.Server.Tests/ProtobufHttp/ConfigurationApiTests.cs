using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using FantasyCard.Server.Tests.Config;
using FantasyCard.Server.Tests.Persistence;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task Configuration_real_HTTP_authenticates_and_serves_exact_current_or_archived_binary()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:false);
        using var archive = new ConfigArchiveDirectory();
        var old = PublishedConfigTestInputs.Create("http-old");
        PublishedConfigTestInputs.Store(archive.Root,old.Catalog.Version,old.Bytes,old.Hash);
        var port = ReserveLoopbackPort();
        await using var server = StartServer(db.ConnectionString,port,archive.Root,legacy:false);
        using var client = new HttpClient {BaseAddress=new Uri($"http://127.0.0.1:{port}")};
        var ct = TestContext.Current.CancellationToken;
        await server.WaitUntilReadyAsync(client,ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using (var denied = await client.GetAsync("/api/v1/config/"+old.Catalog.Version,ct))
        {
            Assert.Equal(HttpStatusCode.Unauthorized,denied.StatusCode);
            Assert.Equal(401,Wire.HttpError.Parser.ParseFrom(await denied.Content.ReadAsByteArrayAsync(ct)).Status);
        }
        using var signedIn = await client.PostAsync("/api/v1/auth/local",PbContent(new Wire.LocalSignInRequest
            {DeviceId="config-"+Guid.NewGuid().ToString("N"),DisplayName="Config Player"}),ct);
        signedIn.EnsureSuccessStatusCode();
        var login = Wire.LocalSignInResponse.Parser.ParseFrom(await signedIn.Content.ReadAsByteArrayAsync(ct));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer",login.AccessToken);
        foreach (var configuration in new[] {GameConfigCatalog.Current,old.Catalog})
        {
            using var response = await client.GetAsync("/api/v1/config/"+configuration.Version,ct);
            response.EnsureSuccessStatusCode();
            Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType!.MediaType);
            var payload = Wire.PublishedConfigurationResponse.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct));
            Assert.Equal(configuration.Version,payload.ConfigVersion);
            Assert.Equal(configuration.ContentHash,payload.ContentHash);
            Assert.Equal(configuration.ExportPublishedBytes(),payload.Bundle.ToByteArray());
        }
        using var missing = await client.GetAsync("/api/v1/config/missing-old",ct);
        Assert.Equal(HttpStatusCode.NotFound,missing.StatusCode);
        Assert.Equal(404,Wire.HttpError.Parser.ParseFrom(await missing.Content.ReadAsByteArrayAsync(ct)).Status);
        client.DefaultRequestHeaders.Accept.Clear();
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        using var json = await client.GetAsync("/api/v1/config/"+old.Catalog.Version,ct);
        Assert.Equal(HttpStatusCode.NotAcceptable,json.StatusCode);
    }
}
