using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Seasons;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Progression;
using Npgsql;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonArchiveReadEncodingTests
{
    [Fact]
    public void ArchiveRoutesUseNamedMessagesAndKeepUnknownLegacyMetadataNull()
    {
        var source=new SeasonArchiveSummaryResponse("legacy-gdd-0.70","legacy",null,null,null,null,null,DateTimeOffset.UnixEpoch,
            "Legacy",null,new("legacy-gdd-0.70",0,456,77,1,DateTimeOffset.UnixEpoch,false),1,0,0,0);
        var contract=HttpProtocolRegistry.Find("GET","/api/v1/season-archives")!;
        var wire=Wire.SeasonArchivesResponse.Parser.ParseFrom(HttpDtoMapper.EncodeResponse(contract,new SeasonArchivesResponse([source],null)));
        Assert.False(wire.HasNextOffset);var row=Assert.Single(wire.Items);
        Assert.False(row.HasConfigVersion);Assert.False(row.HasConfigSha256);Assert.False(row.HasStatsVersion);Assert.False(row.HasStartsAt);Assert.False(row.HasEndsAt);
        Assert.Equal(source,Assert.Single(Assert.IsType<SeasonArchivesResponse>(HttpDtoMapper.ToDto(wire,typeof(SeasonArchivesResponse))).Items));
        Assert.Equal(Wire.SeasonArchiveSectionResponse.Descriptor,HttpProtocolRegistry.Find("GET","/api/v1/season-archives/old/equipment?limit=20")!.ResponseDescriptor);
    }
    [Fact]
    public void OriginalVersionAndOpaqueWalletsPhysicalIdentityAndReadOnlyFlagSurviveTypedEncoding()
    {
        var source=new SeasonArchiveSummaryResponse("old","season-v1","season-v1-config-15",new string('a',64),"season-equipment-v1",
            DateTimeOffset.UnixEpoch,DateTimeOffset.UnixEpoch.AddDays(42),null,"WaitingAssets","WaitingAssets",
            new("old",9007199254740993,123,77,9,null,true,4,14),7,8,9,3);
        var item=new EquipmentResponse(Guid.NewGuid(),"Head","Orange",5,true,"MarketReturnPending",9007199254740993,"Water","Piercing","DrawInterval","old","old","ArchivedSeason","season-equipment-v1","NaturalDrop",true);
        var response=new SeasonArchiveSectionResponse(source,"equipment",true,[item],[],[],[],20);
        var contract=HttpProtocolRegistry.Find("GET","/api/v1/season-archives/old/equipment")!;
        var bytes=HttpDtoMapper.EncodeResponse(contract,response);var wire=Wire.SeasonArchiveSectionResponse.Parser.ParseFrom(bytes);
        Assert.True(wire.ReadOnly);Assert.Equal("season-v1-config-15",wire.Season.ConfigVersion);Assert.Equal(9007199254740993,wire.Season.Wallet.Gold);
        var decoded=Assert.IsType<SeasonArchiveSectionResponse>(HttpDtoMapper.ToDto(wire,typeof(SeasonArchiveSectionResponse)));
        Assert.Equal(source,decoded.Season);Assert.Equal(item,Assert.Single(decoded.Equipments));Assert.Equal(20,decoded.NextOffset);
    }
    [Theory]
    [InlineData(0,0)][InlineData(51,0)][InlineData(20,-1)][InlineData(20,1000001)]
    public async Task InvalidPageBoundsAreRejectedBeforeOpeningAConnection(int limit,int offset)
    {
        await using var source=NpgsqlDataSource.Create("Host=invalid;Database=not-used;Username=not-used");var repository=new ProgressionRepository(source);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.GetSeasonArchivesAsync(Guid.NewGuid(),limit,offset,TestContext.Current.CancellationToken));
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.GetSeasonArchiveSectionAsync(Guid.NewGuid(),"old","equipment",limit,offset,TestContext.Current.CancellationToken));
    }
}
