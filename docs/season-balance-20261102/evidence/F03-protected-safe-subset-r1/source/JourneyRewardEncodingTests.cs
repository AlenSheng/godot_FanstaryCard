using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class JourneyRewardEncodingTests
{
    [Fact]
    public void LockedRewardKeepsItsPhysicalIdentityAndChoiceAbsent()
    {
        var reward=new JourneyRewardResponse(null,"old","original",3,645,"ClassSoul",2,"PermanentBound",true,null,"Locked",false);
        var response=new JourneyRewardsResponse("Active","old","original",[reward]);
        var wire=Assert.IsType<Wire.JourneyRewardsResponse>(HttpDtoMapper.FromDto(Wire.JourneyRewardsResponse.Descriptor,response));
        Assert.False(wire.Rewards[0].HasRewardId);Assert.False(wire.Rewards[0].HasHeroClass);Assert.False(wire.Rewards[0].HasEarnedAt);
        Assert.Equivalent(response,HttpDtoMapper.ToDto(wire,typeof(JourneyRewardsResponse)),strict:true);
    }

    [Fact]
    public void ActualGroupedCopiesAndOriginalClaimMetadataSurviveEncoding()
    {
        var reward=new JourneyRewardResponse(Guid.NewGuid(),"old","original",5,1150,"CardPack",1,"PermanentBound",false,null,"Claimed",false,null,DateTimeOffset.UnixEpoch,DateTimeOffset.UnixEpoch.AddDays(2));
        var response=new JourneyClaimResponse(reward,[new("Cards",3,"C01",false,6,9007199254740997L)]);
        var wire=Assert.IsType<Wire.JourneyClaimResponse>(HttpDtoMapper.FromDto(Wire.JourneyClaimResponse.Descriptor,response));
        Assert.False(wire.HasBalanceAfter);Assert.Equal(3,wire.Grants[0].Amount);Assert.Equal(9007199254740997L,wire.Grants[0].Version);
        Assert.Equivalent(response,HttpDtoMapper.ToDto(wire,typeof(JourneyClaimResponse)),strict:true);
    }

    [Fact]
    public void PermanentCosmeticSourcesAndSelectionVersionsRemainTyped()
    {
        var response=new CosmeticsResponse([new("trail-seeker","AvatarFrame","name","description","old","original",DateTimeOffset.UnixEpoch)],
            new("trail-seeker",null,null,9007199254740997L));
        var wire=Assert.IsType<Wire.CosmeticsResponse>(HttpDtoMapper.FromDto(Wire.CosmeticsResponse.Descriptor,response));
        Assert.False(wire.Selection.HasCardBackId);Assert.False(wire.Selection.HasTitleId);
        Assert.Equivalent(response,HttpDtoMapper.ToDto(wire,typeof(CosmeticsResponse)),strict:true);
        var request=new CosmeticSelectionRequest("Title",null,9007199254740997L);
        Assert.Equivalent(request,HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.CosmeticSelectionRequest.Descriptor,request),typeof(CosmeticSelectionRequest)),strict:true);
        var claim=new JourneyClaimRequest("old","Mage");
        Assert.Equivalent(claim,HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.JourneyClaimRequest.Descriptor,claim),typeof(JourneyClaimRequest)),strict:true);
    }

    [Theory]
    [InlineData("GET","/api/v1/season-journey/rewards","Empty","JourneyRewardsResponse")]
    [InlineData("POST","/api/v1/season-journey/rewards/00000000-0000-0000-0000-000000000001/claim","JourneyClaimRequest","JourneyClaimResponse")]
    [InlineData("GET","/api/v1/cosmetics","Empty","CosmeticsResponse")]
    [InlineData("PUT","/api/v1/cosmetics/selection","CosmeticSelectionRequest","CosmeticSelectionResponse")]
    public void RegisteredRoutesUseOnlyTheirDedicatedProtobufMessages(string method,string path,string request,string response)
    {
        var route=Assert.IsType<HttpEndpointContract>(HttpProtocolRegistry.Find(method,path));
        Assert.Equal(request,route.Request);Assert.Equal(response,route.Response);
    }
}
