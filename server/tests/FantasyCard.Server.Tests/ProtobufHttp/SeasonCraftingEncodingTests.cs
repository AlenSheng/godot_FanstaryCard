using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Seasons;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class SeasonCraftingEncodingTests
{
    [Fact]
    public void TypedBlueprintWalletsUseAdditiveFieldsAndDoNotRenameOpaqueLegacyMarks()
    {
        var wallet=new SeasonWalletResponse("s",10,20,77,3,null,true,4,14);
        var wire=Assert.IsType<Wire.SeasonWalletResponse>(HttpDtoMapper.FromDto(Wire.SeasonWalletResponse.Descriptor,wallet));
        Assert.Equal(77,wire.ChallengeMarks);Assert.Equal(4,wire.BlueprintMarks);Assert.Equal(14,wire.OrangeBlueprintMarks);
        Assert.Equal(wallet,Assert.IsType<SeasonWalletResponse>(HttpDtoMapper.ToDto(wire,typeof(SeasonWalletResponse))));
        var old=Wire.SeasonWalletResponse.Parser.ParseFrom(new Wire.SeasonWalletResponse{SeasonId="s",ChallengeMarks=77}.ToByteArray());
        Assert.Equal(0,old.BlueprintMarks);Assert.Equal(0,old.OrangeBlueprintMarks);
    }

    [Fact]
    public void CraftAndReforgeRequestsKeepTheOriginalSeasonAndExactVersionFields()
    {
        var craft=new CraftEquipmentRequest("s","Orange","Feet","Water","Vitality",9_007_199_254_740_993L);
        var encoded=HttpDtoMapper.FromDto(Wire.CraftEquipmentRequest.Descriptor,craft);
        Assert.Equal(craft,Assert.IsType<CraftEquipmentRequest>(HttpDtoMapper.ToDto(encoded,typeof(CraftEquipmentRequest))));
        var reforge=new ReforgeEquipmentRequest("s",Guid.NewGuid(),Guid.NewGuid(),8,9);
        var body=HttpDtoMapper.FromDto(Wire.ReforgeEquipmentRequest.Descriptor,reforge);
        Assert.Equal(reforge,Assert.IsType<ReforgeEquipmentRequest>(HttpDtoMapper.ToDto(body,typeof(ReforgeEquipmentRequest))));
    }

    [Fact]
    public void ARealUnaffixedPurpleRecipeIsNotDecodedAsAnInventedEffect()
    {
        var recipe=new SeasonRecipeResponse(Guid.NewGuid(),"s","Purple","Feet","Fire",null,"ForcedEscape","season-equipment-v1",Guid.NewGuid());
        var encoded=HttpDtoMapper.FromDto(Wire.SeasonRecipeResponse.Descriptor,recipe);
        Assert.False(Assert.IsType<Wire.SeasonRecipeResponse>(encoded).HasEffectAffix);
        Assert.Equal(recipe,Assert.IsType<SeasonRecipeResponse>(HttpDtoMapper.ToDto(encoded,typeof(SeasonRecipeResponse))));
    }
}
