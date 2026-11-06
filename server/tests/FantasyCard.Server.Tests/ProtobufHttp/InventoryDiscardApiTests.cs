using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task InventoryDiscard_binary_http_authenticates_versions_replays_and_projects_the_committed_inventory()
    {
        await using var database = await PostgresTestSchema.CreateAsync(false);
        var evidence = Environment.GetEnvironmentVariable("FANTASYCARD_DISCARD_SCHEMA_EVIDENCE");
        if (evidence is not null) File.AppendAllText(evidence, JsonSerializer.Serialize(new
        {
            kind = "inventory-discard-api-schema", schema = new NpgsqlConnectionStringBuilder(database.ConnectionString).SearchPath,
            created_at_utc = DateTimeOffset.UtcNow
        }) + Environment.NewLine);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(120)); var ct = timeout.Token; var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port, legacy: false);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(12) };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        async Task<byte[]> Call(string path, IMessage body, string? key, HttpStatusCode expected)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, path) { Content = PbContent(body) };
            if (key is not null) request.Headers.Add("Idempotency-Key", key);
            using var response = await client.SendAsync(request, ct); var bytes = await response.Content.ReadAsByteArrayAsync(ct);
            Assert.Equal(expected, response.StatusCode);
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType?.MediaType);
            if (expected != HttpStatusCode.OK) Assert.Equal((int)expected, Wire.HttpError.Parser.ParseFrom(bytes).Status);
            return bytes;
        }
        var empty = new Wire.DiscardEquipmentRequest();
        await Call("/api/v1/inventory/discard", empty, "anonymous", HttpStatusCode.Unauthorized);
        var owner = Wire.LocalSignInResponse.Parser.ParseFrom(await Call("/api/v1/auth/local",
            new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "Discard-" + Guid.NewGuid().ToString("N")[..8] }, null, HttpStatusCode.OK));
        var peer = Wire.LocalSignInResponse.Parser.ParseFrom(await Call("/api/v1/auth/local",
            new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "Peer-" + Guid.NewGuid().ToString("N")[..8] }, null, HttpStatusCode.OK));
        var day = DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow, TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime);
        var config = GameConfigCatalog.Current;
        var definition = SeasonDefinition.FromCalendarDays("discard-api", day, config.Version, "season-equipment-v1");
        var seasons = new SeasonRepository(database.DataSource, TimeProvider.System);
        await seasons.PublishAsync(definition, config.ContentHash, ct); var player = Guid.Parse(owner.Player.UserId);
        await seasons.EnsurePlayerAsync(player, definition.ContextFor(0), ct);
        var inputs = new CraftingPlayer(player, definition, new CraftingClock(DateTimeOffset.UtcNow), seasons, new(database.DataSource));
        var a = await CraftingTestInputs.ItemAsync(database, inputs, "Blue", effect: null);
        var b = await CraftingTestInputs.ItemAsync(database, inputs, "Green", "Head", effect: null, bound: true);
        var batch = new Wire.DiscardEquipmentRequest { SeasonId = definition.SeasonId };
        batch.Items.Add(new Wire.DiscardEquipmentItemRequest { EquipmentId = a.ToString("D"), ExpectedVersion = 1 });
        batch.Items.Add(new Wire.DiscardEquipmentItemRequest { EquipmentId = b.ToString("D"), ExpectedVersion = 1 });
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", peer.AccessToken);
        await Call("/api/v1/inventory/discard", batch, "foreign", HttpStatusCode.BadRequest);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", owner.AccessToken);
        await Call("/api/v1/inventory/discard", batch, null, HttpStatusCode.BadRequest);
        var wrong = batch.Clone(); wrong.SeasonId = "old-season";
        await Call("/api/v1/inventory/discard", wrong, "wrong-season", HttpStatusCode.BadRequest);
        var first = await Call("/api/v1/inventory/discard", batch, "discard-http", HttpStatusCode.OK);
        var result = Wire.DiscardEquipmentResponse.Parser.ParseFrom(first);
        Assert.Equal(2, result.Items.Count); Assert.All(result.Items, item => { Assert.Equal("Recycled", item.Location); Assert.Equal(2, item.Version); });
        Assert.Equal(first, await Call("/api/v1/inventory/discard", batch, "discard-http", HttpStatusCode.OK));
        var changed = batch.Clone(); changed.Items[0].ExpectedVersion++;
        await Call("/api/v1/inventory/discard", changed, "discard-http", HttpStatusCode.Conflict);
        await Call("/api/v1/inventory/discard", batch, "second-key", HttpStatusCode.BadRequest);
        using var inventory = await client.GetAsync("/api/v1/inventory", ct); Assert.Equal(HttpStatusCode.OK, inventory.StatusCode);
        var projected = Wire.InventoryResponse.Parser.ParseFrom(await inventory.Content.ReadAsByteArrayAsync(ct));
        Assert.Empty(projected.Equipments); Assert.Equal(50, projected.Summary.FreeSlots);
        Assert.Equal(1, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
        Assert.Equal(2, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.discard'"));
        Assert.Equal(0, await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1", player));
    }
}
