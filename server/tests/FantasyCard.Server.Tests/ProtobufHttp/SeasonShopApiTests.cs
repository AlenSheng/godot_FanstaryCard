using System.Net;
using System.Net.Http.Headers;
using FantasyCard.Contracts.Http;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task SeasonShop_RealBinaryHttpKeepsScopedPricesCopiesAndFrozenReplayReceipts()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);timeout.CancelAfter(TimeSpan.FromSeconds(150));var ct=timeout.Token;
        var port=ReserveLoopbackPort();await using var server=StartServer(db.ConnectionString,port,legacy:false);
        using var client=new HttpClient{BaseAddress=new Uri($"http://127.0.0.1:{port}"),Timeout=TimeSpan.FromSeconds(15)};
        await server.WaitUntilReadyAsync(client,ct);client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        string? token=null;
        async Task<byte[]> Call(string method,string path,IMessage? body=null,string? key=null,HttpStatusCode status=HttpStatusCode.OK)
        {
            using var request=new HttpRequestMessage(new HttpMethod(method),path);
            if(token is not null)request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
            if(method!="GET")request.Content=PbContent(body??new Wire.Empty());if(key is not null)request.Headers.Add("Idempotency-Key",key);
            using var response=await client.SendAsync(request,ct);var bytes=await response.Content.ReadAsByteArrayAsync(ct);
            Assert.True(response.StatusCode==status,$"{path}: expected {status}, got {response.StatusCode}");
            Assert.Equal(HttpProtocolRegistry.MediaType,response.Content.Headers.ContentType?.MediaType);return bytes;
        }
        var login=Wire.LocalSignInResponse.Parser.ParseFrom(await Call("POST","/api/v1/auth/local",new Wire.LocalSignInRequest{DeviceId=Guid.NewGuid().ToString(),DisplayName="Shop-"+Guid.NewGuid().ToString("N")[..6]}));
        token=login.AccessToken;var player=Guid.Parse(login.Player.UserId);var config=GameConfigCatalog.Current;
        var today=DateOnly.FromDateTime(DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).DateTime);
        var season=SeasonDefinition.FromCalendarDays("shop-api",today,config.Version,"season-equipment-v1");
        var seasons=new SeasonRepository(db.DataSource,TimeProvider.System);await seasons.PublishAsync(season,config.ContentHash,ct);
        await seasons.EnsurePlayerAsync(player,season.ContextFor(0),ct);await seasons.ApplyAsync(player,season.ContextFor(0),5000,0,0,"test.api.fund","fund",SeasonWalletPurpose.General,ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_cards SET unlocked=true,copy_count=1 WHERE player_id=$1",player);
        var cardsBytes=await Call("GET","/api/v1/cards");var cards=Wire.CardListResponse.Parser.ParseFrom(cardsBytes);Assert.All(cards.Items,c=>Assert.True(c.PermanentCopies));
        var shopBytes=await Call("GET","/api/v1/shop");var shop=Wire.ShopResponse.Parser.ParseFrom(shopBytes);
        Assert.Equal("Active",shop.Policy.State);Assert.Equal(season.SeasonId,shop.Policy.SeasonId);Assert.Equal(5000,shop.Policy.Wallet.Gold);
        Wire.PurchaseShopRequest Intent(string id)=>new(){ProductId=id,Quantity=1,SeasonId=shop.Policy.SeasonId,ResetKey=shop.ResetKey,RotationKey=shop.RotationKey,
            ExpectedPriceGold=shop.Products.Single(p=>p.ProductId==id).PriceGold,CatalogVersion=shop.Policy.CatalogVersion};
        await Call("POST","/api/v1/shop/purchases",new Wire.PurchaseShopRequest{ProductId="equipment_fragments"},"missing-scope",HttpStatusCode.Conflict);
        var fragmentBytes=await Call("POST","/api/v1/shop/purchases",Intent("equipment_fragments"),"fragments");
        Assert.Equal(fragmentBytes,await Call("POST","/api/v1/shop/purchases",Intent("equipment_fragments"),"fragments"));
        var fragments=Wire.ShopPurchaseResponse.Parser.ParseFrom(fragmentBytes);Assert.Equal(4880,fragments.GoldAfter);Assert.Equal(20,Assert.Single(fragments.Grants).Amount);
        var packBytes=await Call("POST","/api/v1/shop/purchases",Intent("card_pack"),"pack-copies");var pack=Wire.ShopPurchaseResponse.Parser.ParseFrom(packBytes);
        Assert.Equal(4630,pack.GoldAfter);Assert.Equal(3,pack.Grants.Sum(g=>g.Amount));Assert.All(pack.Grants,g=>{Assert.False(g.NewlyUnlocked);Assert.True(g.CopiesAfter>=2);});
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_SHOP_INTEROP_DIR");
        if(!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);await File.WriteAllBytesAsync(Path.Combine(directory,"shop.bin"),shopBytes,ct);
            await File.WriteAllBytesAsync(Path.Combine(directory,"fragments.bin"),fragmentBytes,ct);
            await File.WriteAllBytesAsync(Path.Combine(directory,"pack.bin"),packBytes,ct);await File.WriteAllBytesAsync(Path.Combine(directory,"cards.bin"),cardsBytes,ct);
        }
    }
}
