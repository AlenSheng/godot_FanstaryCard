using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task SeasonWallet_binary_quote_upgrade_ownership_and_legacy_contracts()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(100));
        var ct = timeout.Token;
        var port = ReserveLoopbackPort();
        var start = new ProcessStartInfo("dotnet")
        {
            WorkingDirectory = FindServerProjectDirectory(), UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true
        };
        start.ArgumentList.Add(typeof(FantasyCard.Server.Persistence.DatabaseMigrator).Assembly.Location);
        start.Environment["ASPNETCORE_ENVIRONMENT"] = "Development";
        start.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
        start.Environment["ConnectionStrings__Postgres"] = database.ConnectionString;
        start.Environment["Identity__EnableLocalAuth"] = "true";
        start.Environment["ProtobufHttp__AllowLegacyJson"] = "false";
        start.Environment.Remove("OTEL_EXPORTER_OTLP_ENDPOINT");
        await using var server = NetworkServerProcess.Start(start);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(12) };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));

        async Task<byte[]> Call(string method, string path, IMessage? body = null, string? key = null, HttpStatusCode expected = HttpStatusCode.OK)
        {
            using var request = new HttpRequestMessage(new HttpMethod(method), path);
            if (method != "GET") request.Content = PbContent(body ?? new Wire.Empty());
            if (key is not null) request.Headers.Add("Idempotency-Key", key);
            using var response = await client.SendAsync(request, ct);
            var bytes = await response.Content.ReadAsByteArrayAsync(ct);
            Assert.Equal(expected, response.StatusCode);
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType?.MediaType);
            return bytes;
        }

        var owner = Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST", "/api/v1/auth/local",
            new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "Season wallet owner" }));
        var peer = Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST", "/api/v1/auth/local",
            new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "Season wallet peer" }));
        var playerId = Guid.Parse(owner.Player.UserId);
        var localDay = DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow,
            TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime);
        var definition = SeasonDefinition.FromCalendarDays("api-season", localDay, "api-config", "season-equipment-v1");
        var seasons = new SeasonRepository(database.DataSource, TimeProvider.System);
        await seasons.PublishAsync(definition, new string('a', 64), ct);
        await seasons.EnsurePlayerAsync(playerId, definition.ContextFor(0), ct);
        await seasons.ApplyAsync(playerId, definition.ContextFor(0), 0, 100, 0, "test.reward", "fund", SeasonWalletPurpose.General, ct);
        await using (var seed = database.DataSource.CreateCommand("UPDATE player_materials SET equipment_fragments=1000 WHERE player_id=$1"))
        {
            seed.Parameters.AddWithValue(playerId); await seed.ExecuteNonQueryAsync(ct);
        }

        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", owner.AccessToken);
        var quote = Wire.EnhancementQuoteResponse.Parser.ParseFrom(await Call("GET",
            "/api/v1/class-weapons/Mage/enhancement-quote?fragmentSourceSeasonId=api-season"));
        Assert.Equal("api-season", quote.FragmentSourceSeasonId);
        Assert.Equal(100, quote.AvailableFragments);
        Assert.Equal(2, quote.FragmentWalletVersion);
        var upgrade = new Wire.EnhanceEquipmentRequest { ExpectedVersion = quote.ExpectedVersion, FragmentSourceSeasonId = "api-season" };
        var firstBytes = await Call("POST", "/api/v1/class-weapons/Mage/enhance", upgrade, "scoped-upgrade");
        var result = Wire.EnhanceResult.Parser.ParseFrom(firstBytes);
        Assert.Equal(1, result.Equipment.Level);
        Assert.Equal("api-season", result.FragmentSourceSeasonId);
        Assert.Equal(92, result.EquipmentFragments);
        Assert.Equal(3, result.FragmentWalletVersion);
        Assert.Equal(firstBytes, await Call("POST", "/api/v1/class-weapons/Mage/enhance", upgrade, "scoped-upgrade"));
        Assert.Equal(1000L, await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", playerId));
        var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await Call("GET", "/api/v1/bootstrap"));
        Assert.Equal("api-season", bootstrap.Season.SeasonId);
        Assert.Equal("Active", bootstrap.Season.State);
        Assert.Equal(92, bootstrap.Materials.EquipmentFragments);
        Assert.Equal(1000, bootstrap.Season.HistoricalEquipmentFragments);
        Assert.Equal("ActiveSeason", bootstrap.Inventory.Scope.State);

        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", peer.AccessToken);
        await Call("POST", "/api/v1/class-weapons/Mage/enhance", upgrade, "other-owner", HttpStatusCode.BadRequest);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", owner.AccessToken);
        await Call("POST", "/api/v1/class-weapons/Mage/enhance",
            new Wire.EnhanceEquipmentRequest { ExpectedVersion = 2, FragmentSourceSeasonId = "" }, "empty-wallet", HttpStatusCode.BadRequest);

        var historical = Wire.EnhancementQuoteResponse.Parser.ParseFrom(await Call("GET", "/api/v1/class-weapons/Priest/enhancement-quote"));
        Assert.Equal(1000, historical.AvailableFragments);
        Assert.False(historical.HasFragmentSourceSeasonId);
        var oldResult = Wire.EnhanceResult.Parser.ParseFrom(await Call("POST", "/api/v1/class-weapons/Priest/enhance",
            new Wire.EnhanceEquipmentRequest { ExpectedVersion = historical.ExpectedVersion }, "historical-upgrade"));
        Assert.Equal(992, oldResult.EquipmentFragments);
        Assert.False(oldResult.HasFragmentSourceSeasonId);
        Assert.False(oldResult.HasFragmentWalletVersion);
        Assert.Equal(92, (await seasons.GetWalletAsync(playerId, definition.ContextFor(0), ct))!.EquipmentFragments);
    }
}
