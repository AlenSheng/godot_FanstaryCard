using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Realtime;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonMarketEncodingTests
{
    private static readonly JsonSerializerOptions Json=new();
    [Fact]
    public void LegacyListingRequestKeepsItsExactOriginalHashInputWhenNewFieldsAreAbsent()
    {
        var id=Guid.Parse("00000000-0000-0000-0000-000000000001");var request=new CreateMarketListingRequest(id,100);
        Assert.Equal("{\"EquipmentId\":\"00000000-0000-0000-0000-000000000001\",\"PriceGold\":100}",JsonSerializer.Serialize(request,Json));
        var wire=HttpDtoMapper.FromDto(Wire.CreateMarketListingRequest.Descriptor,request);
        Assert.Equal(request,Assert.IsType<CreateMarketListingRequest>(HttpDtoMapper.ToDto(wire,typeof(CreateMarketListingRequest))));
    }

    [Fact]
    public void HttpKeepsDiamondPriceDistinctFromGoldAndPreservesTheFrozenItemSource()
    {
        var item=new EquipmentResponse(Guid.NewGuid(),"Head","Red",0,false,"MarketListed",9,"Fire","Piercing","DrawInterval",
            "s","s","ActiveSeason","season-equipment-v1","RedBoss",false,"Inferno","Fire");
        var listing=new MarketListingResponse(Guid.NewGuid(),Guid.NewGuid(),item.InstanceId,0,"Active",3,DateTimeOffset.UnixEpoch,
            DateTimeOffset.UnixEpoch.AddHours(48),item,"Diamond",8000,"s","candidate",DateTimeOffset.UnixEpoch.AddDays(42),800,7200);
        var wire=HttpDtoMapper.FromDto(Wire.MarketListingResponse.Descriptor,listing);
        Assert.Equal(listing,Assert.IsType<MarketListingResponse>(HttpDtoMapper.ToDto(wire,typeof(MarketListingResponse))));
        var request=new CreateMarketListingRequest(item.InstanceId,0,"Diamond",8000,"s",9);
        Assert.Equal(request,Assert.IsType<CreateMarketListingRequest>(HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.CreateMarketListingRequest.Descriptor,request),typeof(CreateMarketListingRequest))));
        var frame=new ServerEvent("inventory.changed","market-source",new InventoryChangedEventPayload("market.listed",listing.ListingId.ToString("D"),listing),Guid.NewGuid().ToString("D"),1,DateTimeOffset.UnixEpoch);
        var decoded=Assert.IsType<InventoryChangedEventPayload>(RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(frame)).Payload);
        Assert.Equal(listing,decoded.Listing);Assert.Null(decoded.SellerGoldAfter);
    }
}
