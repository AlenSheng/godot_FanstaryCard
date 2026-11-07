using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonActivityEncodingTests
{
    [Fact]
    public void ExchangeKeepsOriginalScopeAndAccountVersionAndCannotAcceptAnAmountFromTheClient()
    {
        var request=new ActivityExchangeRequest("old-season","event-class",9007199254740993L,2,"Priest");
        Assert.Equal(request,Assert.IsType<ActivityExchangeRequest>(HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.ActivityExchangeRequest.Descriptor,request),typeof(ActivityExchangeRequest))));
        Assert.DoesNotContain(Wire.ActivityExchangeRequest.Descriptor.Fields.InFieldNumberOrder(),field=>field.Name is "earned" or "reward_amount" or "token_cost");
    }
    [Fact]
    public void HeldClaimCarriesOriginalEventAndSeasonAndPreservesExactIntegerBalance()
    {
        var reward=new ActivityRewardResponse(Guid.NewGuid(),"old","first","event-fragments","bound_fragments",40,null,12,4,"Claimed",DateTimeOffset.UnixEpoch,DateTimeOffset.UnixEpoch.AddDays(42),false,"frozen");
        var response=new ActivityClaimResponse(reward,9007199254740993L);
        Assert.Equal(response,Assert.IsType<ActivityClaimResponse>(HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.ActivityClaimResponse.Descriptor,response),typeof(ActivityClaimResponse))));
    }
}
