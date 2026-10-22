using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Server.Tests.Persistence;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Bootstrap_projection_real_HTTP_preserves_auth_scope_pending_errors_and_full_legacy_response()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        var ct = timeout.Token;
        var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}") };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using (var unauthorized = await client.GetAsync("/api/v1/bootstrap?settlementMatchId=invalid", ct))
        {
            Assert.Equal(HttpStatusCode.Unauthorized, unauthorized.StatusCode);
            Assert.Equal(401, Wire.HttpError.Parser.ParseFrom(await unauthorized.Content.ReadAsByteArrayAsync(ct)).Status);
        }
        using var loginResponse = await client.PostAsync("/api/v1/auth/local", PbContent(new Wire.LocalSignInRequest
        { DeviceId = Guid.NewGuid().ToString(), DisplayName = "ProjAPI " + Guid.NewGuid().ToString("N")[..10] }), ct);
        loginResponse.EnsureSuccessStatusCode();
        var login = Wire.LocalSignInResponse.Parser.ParseFrom(await loginResponse.Content.ReadAsByteArrayAsync(ct));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login.AccessToken);
        var player = Guid.Parse(login.Player.UserId);
        var match = Guid.NewGuid(); var receipt = Guid.NewGuid(); var hold = Guid.NewGuid();
        await ProjectionSqlAsync(database, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',7,'projection-api','Completed',now())", ct, match, Guid.NewGuid());
        await ProjectionSqlAsync(database, "INSERT INTO match_settlements(settlement_id,match_id,player_id,result,details_json,created_at) VALUES($1,$2,$3,'Dead','{\"revision\":789}'::jsonb,now())", ct, receipt, match, player);
        var path = "/api/v1/bootstrap?settlementMatchId=" + match;
        using (var response = await client.GetAsync(path, ct))
        {
            response.EnsureSuccessStatusCode();
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType!.MediaType);
            Assert.True(response.Headers.CacheControl!.NoStore);
            Assert.False(response.Headers.Contains("X-Mail-Next-Offset"));
            Assert.False(response.Headers.Contains("X-Market-Next-Offset"));
            var bytes = await response.Content.ReadAsByteArrayAsync(ct);
            var projection = Wire.BootstrapResponse.Parser.ParseFrom(bytes);
            Assert.Equal(receipt.ToString(), projection.UnfinishedSettlement.SettlementId);
            Assert.Equal(match.ToString(), projection.UnfinishedSettlement.MatchId);
            Assert.Equal(player.ToString(), projection.UnfinishedSettlement.PlayerId);
            Assert.Null(projection.Player);
            Assert.Null(projection.Wallet);
            Assert.Empty(projection.Cards);
            Assert.Empty(projection.Decks);
            Assert.True(bytes.Length < 512);
        }
        using (var missing = await client.GetAsync("/api/v1/bootstrap?settlementMatchId=" + Guid.NewGuid(), ct))
        {
            missing.EnsureSuccessStatusCode();
            Assert.Null(Wire.BootstrapResponse.Parser.ParseFrom(await missing.Content.ReadAsByteArrayAsync(ct)).UnfinishedSettlement);
        }
        foreach (var query in new[] { "", "invalid", Guid.Empty.ToString(), match + "&settlementMatchId=" + match })
        {
            using var invalid = await client.GetAsync("/api/v1/bootstrap?settlementMatchId=" + query, ct);
            Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode);
            Assert.Equal(400, Wire.HttpError.Parser.ParseFrom(await invalid.Content.ReadAsByteArrayAsync(ct)).Status);
        }
        using var other = new HttpClient { BaseAddress = client.BaseAddress };
        other.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        using var otherLoginResponse = await other.PostAsync("/api/v1/auth/local", PbContent(new Wire.LocalSignInRequest
        { DeviceId = Guid.NewGuid().ToString(), DisplayName = "ProjOther " + Guid.NewGuid().ToString("N")[..10] }), ct);
        otherLoginResponse.EnsureSuccessStatusCode();
        var otherLogin = Wire.LocalSignInResponse.Parser.ParseFrom(await otherLoginResponse.Content.ReadAsByteArrayAsync(ct));
        other.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", otherLogin.AccessToken);
        using (var foreign = await other.GetAsync(path, ct))
        {
            foreign.EnsureSuccessStatusCode();
            Assert.Null(Wire.BootstrapResponse.Parser.ParseFrom(await foreign.Content.ReadAsByteArrayAsync(ct)).UnfinishedSettlement);
        }
        await ProjectionSqlAsync(database, "INSERT INTO settlement_asset_holds(hold_id,settlement_id,player_id,asset_kind,asset_ref,asset_snapshot,state,created_at) VALUES($1,$2,$3,'Gold','projection-api-gold','{}','Pending',now())", ct, hold, receipt, player);
        using (var pending = await client.GetAsync(path, ct))
        {
            pending.EnsureSuccessStatusCode();
            Assert.Null(Wire.BootstrapResponse.Parser.ParseFrom(await pending.Content.ReadAsByteArrayAsync(ct)).UnfinishedSettlement);
        }
        using (var full = await client.GetAsync("/api/v1/bootstrap", ct))
        {
            full.EnsureSuccessStatusCode();
            var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await full.Content.ReadAsByteArrayAsync(ct));
            Assert.Equal(player.ToString(), bootstrap.Player.UserId);
            Assert.NotEmpty(bootstrap.Cards);
            Assert.Null(bootstrap.UnfinishedSettlement);
        }
        await ProjectionSqlAsync(database, "UPDATE settlement_asset_holds SET state='Committed' WHERE hold_id=$1", ct, hold);
        using (var ready = await client.GetAsync(path, ct))
        {
            ready.EnsureSuccessStatusCode();
            Assert.Equal(receipt.ToString(), Wire.BootstrapResponse.Parser.ParseFrom(await ready.Content.ReadAsByteArrayAsync(ct)).UnfinishedSettlement.SettlementId);
        }
        await ProjectionSqlAsync(database, "UPDATE match_settlements SET acknowledged_at=now() WHERE settlement_id=$1", ct, receipt);
        using (var acknowledged = await client.GetAsync(path, ct))
        {
            acknowledged.EnsureSuccessStatusCode();
            Assert.Null(Wire.BootstrapResponse.Parser.ParseFrom(await acknowledged.Content.ReadAsByteArrayAsync(ct)).UnfinishedSettlement);
        }
        using var legacyRequest = new HttpRequestMessage(HttpMethod.Get, "/api/v1/bootstrap");
        legacyRequest.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        using var legacy = await client.SendAsync(legacyRequest, ct);
        legacy.EnsureSuccessStatusCode();
        Assert.Equal("application/json", legacy.Content.Headers.ContentType!.MediaType);
        var legacyData = System.Text.Json.JsonDocument.Parse(await legacy.Content.ReadAsByteArrayAsync(ct));
        using (legacyData)
        {
            Assert.Equal(player.ToString(), legacyData.RootElement.GetProperty("player").GetProperty("userId").GetString());
            Assert.True(legacyData.RootElement.GetProperty("cards").GetArrayLength() > 0);
        }
    }

    private static async Task ProjectionSqlAsync(PostgresTestSchema database, string sql, CancellationToken ct, params object[] values)
    {
        await using var command = database.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(ct);
    }
}
