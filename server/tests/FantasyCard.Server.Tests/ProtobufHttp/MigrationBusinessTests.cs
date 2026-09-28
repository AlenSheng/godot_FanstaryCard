using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Migration_binary_business_equipment_cards_market_mail_matchmaking()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(100));
        var ct = timeout.Token;
        var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(12) };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        var covered = new List<string>();
        async Task<byte[]> Call(string method, string path, IMessage? body = null, HttpStatusCode? expected = null)
        {
            using var request = new HttpRequestMessage(new HttpMethod(method), path);
            if (method != "GET") request.Content = PbContent(body ?? new Wire.Empty());
            request.Headers.Add("Idempotency-Key", "qa-" + Guid.NewGuid().ToString("N"));
            using var response = await client.SendAsync(request, ct);
            var bytes = await response.Content.ReadAsByteArrayAsync(ct);
            Assert.True(expected.HasValue ? response.StatusCode == expected : response.IsSuccessStatusCode, method + " " + path + " => " + response.StatusCode + (bytes.Length > 0 && !response.IsSuccessStatusCode ? Wire.HttpError.Parser.ParseFrom(bytes).ToString() : ""));
            if (bytes.Length > 0) Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType?.MediaType);
            covered.Add(method + " " + path);
            return bytes;
        }
        var seller = Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST", "/api/v1/auth/local", new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "QA Seller" }));
        var buyer = Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST", "/api/v1/auth/local", new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString(), DisplayName = "QA Buyer" }));
        var player = Guid.Parse(seller.Player.UserId);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", seller.AccessToken);
        await database.ExecuteAsync("UPDATE player_wallets SET gold=100000; UPDATE player_materials SET equipment_fragments=100000,warrior_soul=100000,priest_soul=100000,mage_soul=100000,guardian_soul=100000");
        var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await Call("GET", "/api/v1/bootstrap"));
        var card = bootstrap.Cards.First(c => c.CardId == "GW08");
        var crafted = Wire.CardMutationResponse.Parser.ParseFrom(await Call("POST", "/api/v1/cards/GW08/craft", new Wire.CardMutationRequest { ExpectedVersion = card.Version }));
        var upgraded = Wire.CardMutationResponse.Parser.ParseFrom(await Call("POST", "/api/v1/cards/GW08/upgrade", new Wire.CardMutationRequest { ExpectedVersion = crafted.Card.Version }));
        await Call("POST", "/api/v1/cards/GW08/dismantle", new Wire.CardMutationRequest { ExpectedVersion = upgraded.Card.Version });
        await Call("GET", "/api/v1/class-weapons/Priest/enhancement-quote");
        await Call("POST", "/api/v1/class-weapons/Priest/enhance", new Wire.EnhanceEquipmentRequest { ExpectedVersion = bootstrap.ClassWeapons.First(w => w.HeroClass == "Priest").Version });
        var equipment = Guid.NewGuid();
        await using (var seed = database.DataSource.CreateCommand("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Chest','Blue',0,false,'Inventory',1,now())"))
        { seed.Parameters.AddWithValue(equipment); seed.Parameters.AddWithValue(player); await seed.ExecuteNonQueryAsync(ct); }
        await Call("GET", $"/api/v1/equipment/{equipment}/enhancement-quote");
        await Call("POST", $"/api/v1/equipment/{equipment}/enhance", new Wire.EnhanceEquipmentRequest { ExpectedVersion = 1 });
        var listing = Wire.MarketListingResponse.Parser.ParseFrom(await Call("POST", "/api/v1/market/listings", new Wire.CreateMarketListingRequest { EquipmentId = equipment.ToString(), PriceGold = 100 }));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", buyer.AccessToken);
        await Call("POST", $"/api/v1/market/{listing.ListingId}/purchase?expectedVersion={listing.Version}");
        Assert.Equal(Guid.Parse(buyer.Player.UserId), await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipment));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", seller.AccessToken);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", buyer.AccessToken);
        // Use a fresh item for cancellation. Relisting a sold item is a separately reproduced pre-existing schema defect (qa-report).
        var cancellationEquipment = Guid.NewGuid();
        await using (var seed = database.DataSource.CreateCommand("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Chest','Blue',0,false,'Inventory',1,now())"))
        { seed.Parameters.AddWithValue(cancellationEquipment); seed.Parameters.AddWithValue(Guid.Parse(buyer.Player.UserId)); await seed.ExecuteNonQueryAsync(ct); }
        var relisted = Wire.MarketListingResponse.Parser.ParseFrom(await Call("POST", "/api/v1/market/listings", new Wire.CreateMarketListingRequest { EquipmentId = cancellationEquipment.ToString(), PriceGold = 101 }));
        await Call("DELETE", $"/api/v1/market/listings/{relisted.ListingId}");
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", seller.AccessToken);
        var loadout = Wire.LoadoutResponse.Parser.ParseFrom(await Call("GET", "/api/v1/loadouts/Priest"));
        var save = new Wire.UpdateLoadoutRequest { ExpectedVersion = loadout.Version }; save.EquipmentIds.Add(loadout.EquipmentIds);
        await Call("PUT", "/api/v1/loadouts/Priest", save);
        var mailId = Guid.NewGuid();
        await using (var seed = database.DataSource.CreateCommand("INSERT INTO mail_messages(mail_id,player_id,title,body,sent_at,attachments_json) VALUES($1,$2,'QA','mail',now(),'[{\"kind\":\"Gold\",\"amount\":17}]'::jsonb)"))
        { seed.Parameters.AddWithValue(mailId); seed.Parameters.AddWithValue(player); await seed.ExecuteNonQueryAsync(ct); }
        await Call("GET", "/api/v1/mail");
        await Call("POST", $"/api/v1/mail/{mailId}/read");
        var goldBeforeMail = await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player);
        await Call("POST", $"/api/v1/mail/{mailId}/claim");
        var duplicateClaim = Wire.MailClaimResponse.Parser.ParseFrom(await Call("POST", $"/api/v1/mail/{mailId}/claim"));
        Assert.True(duplicateClaim.AlreadyClaimed);
        Assert.Equal(goldBeforeMail + 17, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player));
        await Call("POST", "/api/v1/mail/read-all");
        await Call("POST", "/api/v1/mail/claim-all");
        await Call("DELETE", $"/api/v1/mail/{mailId}");
        var deck = bootstrap.Decks.First(d => d.HeroClass == "Priest");
        var prep = new Wire.CreatePreparationRequest { HeroClass = "Priest", DeckVersion = deck.Version, BackpackTier = "Free", PotionCount = 0, Difficulty = "Standard" };
        prep.EquipmentIds.Add(loadout.EquipmentIds);
        var preparation = Wire.PreparationResponse.Parser.ParseFrom(await Call("POST", "/api/v1/preparations", prep));
        await Call("GET", "/api/v1/preparations");
        var ticket = Wire.MatchTicketResponse.Parser.ParseFrom(await Call("POST", "/api/v1/matches/enqueue", new Wire.EnqueueMatchRequest { PreparationId = preparation.PreparationId }));
        await Call("GET", $"/api/v1/matches/tickets/{ticket.TicketId}");
        await Call("DELETE", $"/api/v1/matches/tickets/{ticket.TicketId}");
        await Call("DELETE", $"/api/v1/preparations/{preparation.PreparationId}");
        await Call("DELETE", "/api/v1/mail/read");
        foreach (var route in new[] { "/api/v1/cards", "/api/v1/decks", "/api/v1/economy/context", "/api/v1/economy/wallet", "/api/v1/inventory", "/api/v1/market", "/api/v1/market/context", "/api/v1/players/me", "/api/v1/shop", "/api/v1/shop/context" })
            await Call("GET", route);
        await Call("POST", "/api/v1/shop/refresh");
        var matchId = Guid.NewGuid();
        var settlementId = Guid.NewGuid();
        await using (var seed = database.DataSource.CreateCommand("INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',1,'qa','Completed',now())"))
        { seed.Parameters.AddWithValue(matchId); seed.Parameters.AddWithValue(Guid.NewGuid()); await seed.ExecuteNonQueryAsync(ct); }
        await using (var seed = database.DataSource.CreateCommand("INSERT INTO match_settlements(settlement_id,match_id,player_id,result,details_json,created_at) VALUES($1,$2,$3,'Extracted','{}'::jsonb,now())"))
        { seed.Parameters.AddWithValue(settlementId); seed.Parameters.AddWithValue(matchId); seed.Parameters.AddWithValue(player); await seed.ExecuteNonQueryAsync(ct); }
        await Call("GET", $"/api/v1/settlements/{settlementId}");
        await Call("GET", $"/api/v1/matches/{matchId}/settlement");
        var acknowledged = Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await Call("POST", $"/api/v1/settlements/{settlementId}/acknowledge"));
        var acknowledgedAgain = Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await Call("POST", $"/api/v1/settlements/{settlementId}/acknowledge"));
        Assert.Equal(DateTimeOffset.Parse(acknowledged.AcknowledgedAt, System.Globalization.CultureInfo.InvariantCulture).UtcTicks / 10, DateTimeOffset.Parse(acknowledgedAgain.AcknowledgedAt, System.Globalization.CultureInfo.InvariantCulture).UtcTicks / 10);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", buyer.AccessToken);
        await Call("GET", $"/api/v1/settlements/{settlementId}", expected: HttpStatusCode.NotFound);
        var directory = Path.Combine(FindServerProjectDirectory(), "..", "..", ".artifacts", "qa-migration");
        Directory.CreateDirectory(directory);
        await File.WriteAllLinesAsync(Path.Combine(directory, "business-covered.txt"), covered, ct);
    }
}
