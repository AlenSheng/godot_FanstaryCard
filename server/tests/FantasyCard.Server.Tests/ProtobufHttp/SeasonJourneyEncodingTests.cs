using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonJourneyEncodingTests
{
    [Fact]
    public void OriginalSeasonNestedContractsAndExactInt64VersionSurviveBinaryMapping()
    {
        var levels=Enumerable.Range(1,30).Select(level=>new JourneyLevelResponse(level,200+15*(level-1),
            Enumerable.Range(0,level).Sum(i=>200+15*i),level<=20?"Main":"Collection",false)).ToArray();
        var response=new SeasonJourneyResponse("Active","original","frozen",DateTimeOffset.UnixEpoch,DateTimeOffset.UnixEpoch.AddDays(42),
            42,21,48,0,48,200,12525,20,6850,2,true,9007199254740997L,
            [new("weekly-elite",1,"Elite",5,2,300,0,DateTimeOffset.UnixEpoch,null,"Open")],levels,
            [new("original","Active","frozen",DateTimeOffset.UnixEpoch,DateTimeOffset.UnixEpoch.AddDays(42))],50);
        var decoded=Assert.IsType<SeasonJourneyResponse>(HttpDtoMapper.ToDto(HttpDtoMapper.FromDto(Wire.SeasonJourneyResponse.Descriptor,response),typeof(SeasonJourneyResponse)));
        Assert.Equivalent(response,decoded,strict:true);Assert.Equal(9007199254740997L,decoded.Version);
    }

    [Fact]
    public void AnAbsentOriginalSourceKeepsItsOptionalIdentityAndCursorAbsent()
    {
        var response=new SeasonJourneyResponse("None",null,null,null,null,0,0,0,0,0,0,0,0,0,0,false,0,[],[],[]);
        var wire=Assert.IsType<Wire.SeasonJourneyResponse>(HttpDtoMapper.FromDto(Wire.SeasonJourneyResponse.Descriptor,response));
        Assert.False(wire.HasSeasonId);Assert.False(wire.HasConfigVersion);Assert.False(wire.HasNextOffset);
        Assert.Equivalent(response,HttpDtoMapper.ToDto(wire,typeof(SeasonJourneyResponse)),strict:true);
    }
}
