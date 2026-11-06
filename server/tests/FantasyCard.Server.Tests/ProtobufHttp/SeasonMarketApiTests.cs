using System.Net;
using System.Net.Http.Headers;
using System.Net.WebSockets;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task SeasonMarket_binary_http_and_authenticated_websockets_keep_currency_escrow_and_private_balances()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);timeout.CancelAfter(TimeSpan.FromSeconds(150));var ct=timeout.Token;
        var port=ReserveLoopbackPort();await using var server=StartServer(db.ConnectionString,port,legacy:false);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(15)};
        await server.WaitUntilReadyAsync(client,ct);client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        async Task<byte[]> Call(string method,string path,string? token=null,IMessage? body=null,string? key=null,HttpStatusCode status=HttpStatusCode.OK)
        {
            using var request=new HttpRequestMessage(new HttpMethod(method),path);
            if(token is not null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
            if(method!="GET")request.Content=PbContent(body??new Wire.Empty());
            if(key is not null)request.Headers.Add("Idempotency-Key",key);
            using var response=await client.SendAsync(request,ct);var bytes=await response.Content.ReadAsByteArrayAsync(ct);
            var detail=response.StatusCode==status?"":Wire.HttpError.Parser.ParseFrom(bytes).Detail;
            Assert.True(response.StatusCode==status,$"{method} {path}: expected {status}, got {response.StatusCode}; {detail}");
            if(status==HttpStatusCode.NoContent)Assert.Empty(bytes);
            else Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);
            return bytes;
        }
        await Call("GET","/api/v1/market/returns",status:HttpStatusCode.Unauthorized);
        var seller=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",body:new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="MarketSeller-"+Guid.NewGuid().ToString("N")[..6]}));
        var buyer=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",body:new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="MarketBuyer-"+Guid.NewGuid().ToString("N")[..6]}));
        var owner=Guid.Parse(seller.Player.UserId);var customer=Guid.Parse(buyer.Player.UserId);
        var config=GameConfigCatalog.Current;var day=DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow,TimeZoneInfo.FindSystemTimeZoneById(SeasonDefinition.TimeZoneId)).DateTime);
        var season=SeasonDefinition.FromCalendarDays("market-api",day,config.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var seasons=new SeasonRepository(db.DataSource,TimeProvider.System);await seasons.PublishAsync(season,config.ContentHash,ct);
        foreach(var id in new[]{owner,customer})
        {
            await seasons.EnsurePlayerAsync(id,season.ContextFor(0),ct);
            await seasons.ApplyAsync(id,season.ContextFor(0),150000,0,0,"test.api.gold","fund",SeasonWalletPurpose.General,ct);
        }
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_wallets SET gold=77,diamond=100 WHERE player_id=$1",owner);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_wallets SET gold=88,diamond=3000 WHERE player_id=$1",customer);
        async Task<Guid> Item()
        {
            var id=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
                INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait,
                    origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
                VALUES($1,$2,'Head','Orange',0,false,'Inventory',1,CURRENT_TIMESTAMP,'Fire','Piercing','DrawInterval',$3,$3,'ActiveSeason','season-equipment-v1','NaturalDrop',2)
                """,id,owner,season.SeasonId);return id;
        }
        using var sellerSocket=new ClientWebSocket();using var buyerSocket=new ClientWebSocket();
        sellerSocket.Options.SetRequestHeader("Authorization","Bearer "+seller.AccessToken);buyerSocket.Options.SetRequestHeader("Authorization","Bearer "+buyer.AccessToken);
        var socketUri=new Uri($"ws://127.0.0.1:{port}/ws/v1/session");
        await sellerSocket.ConnectAsync(socketUri,ct);await buyerSocket.ConnectAsync(socketUri,ct);
        Assert.Equal("session.connected",RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(sellerSocket,ct)).Type);
        Assert.Equal("session.connected",RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(buyerSocket,ct)).Type);
        var queues=new Dictionary<ClientWebSocket,List<(InventoryChangedEventPayload Payload,byte[] Raw)>>{{sellerSocket,[]},{buyerSocket,[]}};
        async Task<(InventoryChangedEventPayload Payload,byte[] Raw)> Event(ClientWebSocket socket,string action,Guid listingId)
        {
            while(true)
            {
                var index=queues[socket].FindIndex(row=>row.Payload.Action==action && row.Payload.Listing?.ListingId==listingId);
                if(index>=0){var result=queues[socket][index];queues[socket].RemoveAt(index);return result;}
                var raw=await ReceiveBinaryAsync(socket,ct);var message=RealtimeProtobufCodec.DecodeServer(raw);
                if(message.Payload is InventoryChangedEventPayload payload)queues[socket].Add((payload,raw));
            }
        }
        var item=await Item();var listingRequest=new Wire.CreateMarketListingRequest{EquipmentId=item.ToString("D"),PriceGold=0,Currency="Diamond",Price=2000,SeasonId=season.SeasonId,ExpectedEquipmentVersion=1};
        var listing=Wire.MarketListingResponse.Parser.ParseFrom(await Call("POST","/api/v1/market/listings",seller.AccessToken,listingRequest,"market-list",HttpStatusCode.Created));
        var listingId=Guid.Parse(listing.ListingId);Assert.Equal("Diamond",listing.Currency);Assert.Equal(2000,listing.Price);Assert.Equal(0,listing.PriceGold);
        var listedSeller=await Event(sellerSocket,"market.listed",listingId);var listedBuyer=await Event(buyerSocket,"market.listed",listingId);
        Assert.Null(listedSeller.Payload.SellerGoldAfter);Assert.Null(listedBuyer.Payload.SellerGoldAfter);
        Assert.Equal("NaturalDrop",listedBuyer.Payload.Listing!.Equipment!.SourceKind);Assert.False(listedBuyer.Payload.Listing.Equipment.RecipeExtracted);
        var context=Wire.MarketInventoryContextResponse.Parser.ParseFrom(await Call("GET","/api/v1/market/context?currency=Diamond",seller.AccessToken));
        Assert.Equal(2,context.Policy.Currencies.Count);Assert.Single(context.OwnListings);Assert.Equal(150000,context.Policy.Wallet.Gold);Assert.Equal(100,context.Policy.Wallet.Diamond);
        Assert.Single(context.Listings);Assert.Equal(item.ToString("D"),context.Listings[0].Equipment.InstanceId);
        var emptyGold=Wire.MarketListResponse.Parser.ParseFrom(await Call("GET","/api/v1/market?currency=Gold",buyer.AccessToken));Assert.Empty(emptyGold.Items);
        await Call("POST",$"/api/v1/market/{listing.ListingId}/purchase?expectedVersion={listing.Version}",buyer.AccessToken,key:"no-confirmation",status:HttpStatusCode.Conflict);
        var purchasePath=$"/api/v1/market/{listing.ListingId}/purchase?expectedVersion={listing.Version}&currency=Diamond&expectedPrice=2000&seasonId={season.SeasonId}";
        var purchaseBytes=await Call("POST",purchasePath,buyer.AccessToken,key:"market-buy");
        var purchase=Wire.MarketPurchaseResponse.Parser.ParseFrom(purchaseBytes);Assert.Equal(1000,purchase.Wallet.Diamond);Assert.Equal(150000,purchase.Wallet.Gold);
        var soldSeller=await Event(sellerSocket,"market.sold",listingId);var soldBuyer=await Event(buyerSocket,"market.sold",listingId);
        Assert.True(soldSeller.Payload.SellerWalletChanged);Assert.False(soldBuyer.Payload.SellerWalletChanged);
        Assert.Null(soldSeller.Payload.SellerGoldAfter);Assert.Null(soldBuyer.Payload.SellerGoldAfter);
        Assert.Equal(purchaseBytes,await Call("POST",purchasePath,buyer.AccessToken,key:"market-buy"));
        var second=await Item();var secondListing=Wire.MarketListingResponse.Parser.ParseFrom(await Call("POST","/api/v1/market/listings",seller.AccessToken,
            new Wire.CreateMarketListingRequest{EquipmentId=second.ToString("D"),PriceGold=100,Currency="Gold",Price=100,SeasonId=season.SeasonId,ExpectedEquipmentVersion=1},"second-list",HttpStatusCode.Created));
        var changed=Wire.MarketListingResponse.Parser.ParseFrom(await Call("POST",$"/api/v1/market/listings/{secondListing.ListingId}/relist",seller.AccessToken,
            new Wire.RelistMarketListingRequest{Currency="Diamond",Price=500,SeasonId=season.SeasonId,ExpectedVersion=secondListing.Version},"change-currency"));
        Assert.NotEqual(secondListing.ListingId,changed.ListingId);Assert.Equal(secondListing.EquipmentId,changed.EquipmentId);
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            SELECT gen_random_uuid(),$1,'Chest','Blue',0,false,'Inventory',1,CURRENT_TIMESTAMP,'Fire','DrawInterval',
                $2,$2,'ActiveSeason','season-equipment-v1','NaturalDrop',0 FROM generate_series(1,50)
            """,owner,season.SeasonId);
        await Call("DELETE",$"/api/v1/market/listings/{changed.ListingId}",seller.AccessToken,key:"return-to-full",status:HttpStatusCode.NoContent);
        var returns=Wire.MarketReturnsResponse.Parser.ParseFrom(await Call("GET","/api/v1/market/returns?limit=1",seller.AccessToken));
        var hold=Assert.Single(returns.Items);Assert.False(hold.CanClaim);Assert.Equal(second.ToString("D"),hold.Equipment.InstanceId);Assert.Equal("MarketReturnPending",hold.Equipment.Location);
        var claim=new Wire.ClaimMarketReturnRequest{ExpectedEquipmentVersion=hold.Equipment.Version,SeasonId=season.SeasonId};
        await Call("POST",$"/api/v1/market/returns/{hold.ReturnId}/claim",buyer.AccessToken,claim,"foreign-claim",HttpStatusCode.Conflict);
        await Call("POST",$"/api/v1/market/returns/{hold.ReturnId}/claim",seller.AccessToken,claim,"full-claim",HttpStatusCode.Conflict);
        var excess=await db.ScalarAsync<Guid>("SELECT instance_id FROM equipments WHERE owner_id=$1 AND location='Inventory' LIMIT 1",owner);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='Recycled' WHERE instance_id=$1",excess);
        var claimedBytes=await Call("POST",$"/api/v1/market/returns/{hold.ReturnId}/claim",seller.AccessToken,claim,"claim-original");
        Assert.Equal(second.ToString("D"),Wire.EquipmentResponse.Parser.ParseFrom(claimedBytes).InstanceId);
        Assert.Equal(claimedBytes,await Call("POST",$"/api/v1/market/returns/{hold.ReturnId}/claim",seller.AccessToken,claim,"claim-original"));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM market_transactions"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(ct)).IsHealthy);
        var evidence=Environment.GetEnvironmentVariable("FANTASYCARD_MARKET_INTEROP_DIR");
        if(!string.IsNullOrWhiteSpace(evidence))
        {
            Assert.True(Path.IsPathFullyQualified(evidence));Directory.CreateDirectory(evidence);
            await File.WriteAllBytesAsync(Path.Combine(evidence,"listed.bin"),listedBuyer.Raw,ct);
            await File.WriteAllBytesAsync(Path.Combine(evidence,"sold-seller.bin"),soldSeller.Raw,ct);
            await File.WriteAllBytesAsync(Path.Combine(evidence,"sold-buyer.bin"),soldBuyer.Raw,ct);
            await File.WriteAllBytesAsync(Path.Combine(evidence,"context.bin"),context.ToByteArray(),ct);
            await File.WriteAllBytesAsync(Path.Combine(evidence,"returns.bin"),returns.ToByteArray(),ct);
            await File.WriteAllBytesAsync(Path.Combine(evidence,"purchase.bin"),purchaseBytes,ct);
        }
        sellerSocket.Abort();buyerSocket.Abort();
    }
}
