using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set isolated PostgreSQL database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Protobuf_real_database_login_bootstrap_profile_deck_and_cross_format_purchase()
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
        using var loginResponse = await client.PostAsync("/api/v1/auth/local", PbContent(new Wire.LocalSignInRequest
        { DeviceId = $"pb-{Guid.NewGuid():N}", DisplayName = "PB Player" }), ct);
        loginResponse.EnsureSuccessStatusCode();
        var login = Wire.LocalSignInResponse.Parser.ParseFrom(await loginResponse.Content.ReadAsByteArrayAsync(ct));
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", login.AccessToken);
        foreach (var route in new[] { "/api/v1/bootstrap", "/api/v1/players/me", "/api/v1/cards", "/api/v1/decks", "/api/v1/inventory", "/api/v1/shop", "/api/v1/economy/context", "/api/v1/market/context", "/api/v1/mail" })
        {
            using var response = await client.GetAsync(route, ct);
            Assert.True(response.IsSuccessStatusCode, route + " returned " + response.StatusCode);
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType!.MediaType);
            var message = HttpProtocolRegistry.Find("GET", route)!.ResponseDescriptor.Parser.ParseFrom(await response.Content.ReadAsByteArrayAsync(ct));
            Assert.NotNull(message);
        }
        using var bootstrapResponse = await client.GetAsync("/api/v1/bootstrap", ct);
        var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await bootstrapResponse.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal(login.Player.UserId, bootstrap.Player.UserId);
        Assert.NotEmpty(bootstrap.Cards);
        using var update = new HttpRequestMessage(HttpMethod.Put, "/api/v1/players/me")
        { Content = PbContent(new Wire.UpdatePlayerProfileRequest { SelectedClass = "Priest", ExpectedVersion = bootstrap.Player.Version }) };
        update.Headers.Add("Idempotency-Key", "pb-profile");
        using var updated = await client.SendAsync(update, ct);
        updated.EnsureSuccessStatusCode();
        var profile = Wire.PlayerProfileResponse.Parser.ParseFrom(await updated.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal("Priest", profile.SelectedClass);
        var deck = bootstrap.Decks[0];
        var saveDeck = new Wire.UpdateDeckRequest { ExpectedVersion = deck.Version };
        saveDeck.CardIds.Add(deck.CardIds);
        using var deckRequest = new HttpRequestMessage(HttpMethod.Put, "/api/v1/decks/" + deck.HeroClass) { Content = PbContent(saveDeck) };
        deckRequest.Headers.Add("Idempotency-Key", "pb-deck-save");
        using var deckResponse = await client.SendAsync(deckRequest, ct);
        if (!deckResponse.IsSuccessStatusCode) Assert.Fail(Wire.HttpError.Parser.ParseFrom(await deckResponse.Content.ReadAsByteArrayAsync(ct)).ToString());
        await using (var gold = database.DataSource.CreateCommand("UPDATE player_wallets SET gold=10000 WHERE player_id=$1"))
        { gold.Parameters.AddWithValue(Guid.Parse(login.Player.UserId)); Assert.Equal(1, await gold.ExecuteNonQueryAsync(ct)); }
        using var purchaseRequest = new HttpRequestMessage(HttpMethod.Post, "/api/v1/shop/purchases")
        { Content = PbContent(new Wire.PurchaseShopRequest { ProductId = "warrior_soul", Quantity = 1 }) };
        purchaseRequest.Headers.Add("Idempotency-Key", "pb-cross-format-purchase");
        using var purchaseResponse = await client.SendAsync(purchaseRequest, ct);
        purchaseResponse.EnsureSuccessStatusCode();
        var first = Wire.ShopPurchaseResponse.Parser.ParseFrom(await purchaseResponse.Content.ReadAsByteArrayAsync(ct));
        using var replayRequest = new HttpRequestMessage(HttpMethod.Post, "/api/v1/shop/purchases")
        { Content = JsonContent.Create(new FantasyCard.Contracts.Progression.PurchaseShopRequest("warrior_soul", 1), options: WebJson) };
        replayRequest.Headers.Add("Idempotency-Key", "pb-cross-format-purchase");
        using var replayResponse = await client.SendAsync(replayRequest, ct);
        replayResponse.EnsureSuccessStatusCode();
        var replay = Wire.ShopPurchaseResponse.Parser.ParseFrom(await replayResponse.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal(first.GoldAfter, replay.GoldAfter);
        Assert.Equal(first.GoldAfter, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", Guid.Parse(login.Player.UserId)));
        foreach (var sql in """
            INSERT INTO mail_messages(mail_id,player_id,title,body,sent_at)
            SELECT gen_random_uuid(),$1,'page','body',now() FROM generate_series(1,205);
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at)
            SELECT gen_random_uuid(),$1,'Head','Blue',0,false,'MarketListed',1,now() FROM generate_series(1,205);
            INSERT INTO market_listings(listing_id,seller_id,equipment_id,price_gold,status,version,created_at,expires_at)
            SELECT gen_random_uuid(),$1,instance_id,10,'Active',1,now(),now()+interval '1 day' FROM equipments WHERE owner_id=$1 AND location='MarketListed';
            """.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            await using var seed = database.DataSource.CreateCommand(sql);
            seed.Parameters.AddWithValue(Guid.Parse(login.Player.UserId)); await seed.ExecuteNonQueryAsync(ct);
        }
        using var mailPage = await client.GetAsync("/api/v1/mail", ct);
        Assert.Equal("200", mailPage.Headers.GetValues("X-Mail-Next-Offset").Single());
        var mail = Wire.MailListResponse.Parser.ParseFrom(await mailPage.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal(200, mail.Items.Count); Assert.Equal(205, mail.UnreadCount);
        using var lastMailPage = await client.GetAsync("/api/v1/mail?offset=200", ct);
        var lastMail = Wire.MailListResponse.Parser.ParseFrom(await lastMailPage.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal(5, lastMail.Items.Count); Assert.Equal(205, lastMail.UnreadCount);
        Assert.False(lastMailPage.Headers.Contains("X-Mail-Next-Offset"));
        Assert.Empty(mail.Items.Select(i => i.Id).Intersect(lastMail.Items.Select(i => i.Id)));
        using var marketPage = await client.GetAsync("/api/v1/market", ct);
        Assert.Equal("200", marketPage.Headers.GetValues("X-Market-Next-Offset").Single());
        var market = Wire.MarketListResponse.Parser.ParseFrom(await marketPage.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal(200, market.Items.Count);
        using var lastMarketPage = await client.GetAsync("/api/v1/market?offset=200", ct);
        var lastMarket = Wire.MarketListResponse.Parser.ParseFrom(await lastMarketPage.Content.ReadAsByteArrayAsync(ct));
        Assert.Equal(5, lastMarket.Items.Count);
        Assert.Empty(market.Items.Select(i => i.ListingId).Intersect(lastMarket.Items.Select(i => i.ListingId)));
        using var pagedBootstrap = await client.GetAsync("/api/v1/bootstrap", ct);
        Assert.True(pagedBootstrap.Headers.Contains("X-Market-Next-Offset"));
        Assert.True(pagedBootstrap.Headers.Contains("X-Mail-Next-Offset"));
        using var invalidPage = await client.GetAsync("/api/v1/market?limit=201", ct);
        Assert.Equal(HttpStatusCode.BadRequest, invalidPage.StatusCode);
        using var malformedContent = new ByteArrayContent([255]);
        malformedContent.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
        using var malformed = await client.PutAsync("/api/v1/players/me", malformedContent, ct);
        Assert.Equal(HttpStatusCode.BadRequest, malformed.StatusCode);
        Assert.Equal(400, Wire.HttpError.Parser.ParseFrom(await malformed.Content.ReadAsByteArrayAsync(ct)).Status);
        var playerId = Guid.Parse(login.Player.UserId);
        var goldBeforeRejectedClaims = await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId);
        foreach (var scenario in new[] { "count", "bytes", "attachments" })
        {
            await using (var clear = database.DataSource.CreateCommand("DELETE FROM mail_messages WHERE player_id=$1"))
            { clear.Parameters.AddWithValue(playerId); await clear.ExecuteNonQueryAsync(ct); }
            var seedSql = scenario switch
            {
                "count" => "INSERT INTO mail_messages(mail_id,player_id,title,body,sent_at,attachments_json) SELECT gen_random_uuid(),$1,'limit','body',now(),'[{\"kind\":\"Gold\",\"amount\":1}]'::jsonb FROM generate_series(1,4097)",
                "bytes" => "INSERT INTO mail_messages(mail_id,player_id,title,body,sent_at,attachments_json) SELECT gen_random_uuid(),$1,'limit','body',now(),jsonb_build_array(jsonb_build_object('kind','Gold','amount',1,'itemId',repeat('x',600))) FROM generate_series(1,4000)",
                _ => "INSERT INTO mail_messages(mail_id,player_id,title,body,sent_at,attachments_json) SELECT gen_random_uuid(),$1,'limit','body',now(),(SELECT jsonb_agg(jsonb_build_object('kind','Gold','amount',1)) FROM generate_series(1,4097))"
            };
            await using (var seed = database.DataSource.CreateCommand(seedSql))
            { seed.Parameters.AddWithValue(playerId); await seed.ExecuteNonQueryAsync(ct); }
            using var claim = new HttpRequestMessage(HttpMethod.Post, "/api/v1/mail/claim-all");
            claim.Headers.Add("Idempotency-Key", "oversize-" + scenario);
            using var rejected = await client.SendAsync(claim, ct);
            Assert.Equal(HttpStatusCode.RequestEntityTooLarge, rejected.StatusCode);
            Assert.Equal(413, Wire.HttpError.Parser.ParseFrom(await rejected.Content.ReadAsByteArrayAsync(ct)).Status);
            Assert.Equal(goldBeforeRejectedClaims, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM mail_messages WHERE player_id=$1 AND (claimed_at IS NOT NULL OR read_at IS NOT NULL)", playerId));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM idempotency_records WHERE player_id=$1 AND scope='mail.claim-all'", playerId));
            if (scenario == "attachments")
            {
                var mailId = await database.ScalarAsync<Guid>("SELECT mail_id FROM mail_messages WHERE player_id=$1", playerId);
                using var single = new HttpRequestMessage(HttpMethod.Post, "/api/v1/mail/" + mailId + "/claim");
                single.Headers.Add("Idempotency-Key", "oversize-single");
                using var singleRejected = await client.SendAsync(single, ct);
                Assert.Equal(HttpStatusCode.RequestEntityTooLarge, singleRejected.StatusCode);
                Assert.Equal(goldBeforeRejectedClaims, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
                Assert.Equal(0L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM idempotency_records WHERE player_id=$1 AND scope='mail.claim'", playerId));
            }
        }



    }
    private static ByteArrayContent PbContent(IMessage message)
    {
        var content = new ByteArrayContent(message.ToByteArray());
        content.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
        return content;
    }
}
