using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonShopEncodingTests
{
    [Fact]
    public void OldPurchaseHashInputRemainsTwoFieldsAndNewIntentKeepsEveryConfirmationField()
    {
        Assert.Equal("{\"ProductId\":\"card_pack\",\"Quantity\":1}",JsonSerializer.Serialize(new PurchaseShopRequest("card_pack")));
        var request=new PurchaseShopRequest("card_pack",2,"season","2026-11-04","2026-11-04~2",250,"catalog");
        var round=HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.PurchaseShopRequest.Descriptor,request),typeof(PurchaseShopRequest));
        Assert.Equal(request,Assert.IsType<PurchaseShopRequest>(round));
    }

    [Fact]
    public void ShopPolicyAndActualCopyReceiptUseTypedFieldsAndKeepLargeIntegerBalancesExact()
    {
        const long gold=9007199254740993L;
        var policy=new ShopPolicyResponse("Active","s","active","frozen",DateTimeOffset.UnixEpoch.AddDays(42),DateTimeOffset.UnixEpoch,true,new(gold,11),true);
        var wire=Assert.IsType<Wire.ShopPolicyResponse>(HttpDtoMapper.FromDto(Wire.ShopPolicyResponse.Descriptor,policy));
        Assert.Equal(gold,wire.Wallet.Gold);Assert.Equal(policy,Assert.IsType<ShopPolicyResponse>(HttpDtoMapper.ToDto(wire,typeof(ShopPolicyResponse))));
        var grant=new ShopGrantResponse("Cards",3,"C01",false,4,17);
        Assert.Equal(grant,Assert.IsType<ShopGrantResponse>(HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.ShopGrantResponse.Descriptor,grant),typeof(ShopGrantResponse))));
    }
}
