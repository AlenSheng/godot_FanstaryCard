using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.ProtobufHttp;

public sealed class LootPreferenceEncodingTests
{
    private static readonly JsonSerializerOptions Json=CreateJson();
    private static JsonSerializerOptions CreateJson()
    {
        var options=new JsonSerializerOptions(JsonSerializerDefaults.Web);options.Converters.Add(new JsonStringEnumConverter());return options;
    }
    [Fact]
    public void NewPreferenceUsesAdditiveOptionalFieldsAndOldMessagesKeepItAbsent()
    {
        var request=new CreatePreparationRequest(HeroClassDto.Mage,7,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D0","s",LootPreferenceElement:"Water");
        var encoded=Assert.IsType<Wire.CreatePreparationRequest>(HttpDtoMapper.FromDto(Wire.CreatePreparationRequest.Descriptor,request));
        Assert.True(encoded.HasLootPreferenceElement);Assert.Equal("Water",encoded.LootPreferenceElement);
        Assert.Equivalent(request,Assert.IsType<CreatePreparationRequest>(HttpDtoMapper.ToDto(encoded,typeof(CreatePreparationRequest))),strict:true);
        var old=Wire.CreatePreparationRequest.Parser.ParseFrom(new Wire.CreatePreparationRequest {HeroClass="Mage",DeckVersion=7,BackpackTier="Free"}.ToByteArray());
        Assert.False(old.HasLootPreferenceElement);
        Assert.Null(Assert.IsType<CreatePreparationRequest>(HttpDtoMapper.ToDto(old,typeof(CreatePreparationRequest))).LootPreferenceElement);
        var snapshot=new PreparationSnapshotResponse(HeroClassDto.Mage,70,[],[],0,BackpackTierDto.Free,20,[],0,"D0","config",LootPreferenceElement:"Metal");
        var projected=Assert.IsType<Wire.PreparationSnapshotResponse>(HttpDtoMapper.FromDto(Wire.PreparationSnapshotResponse.Descriptor,snapshot));
        Assert.True(projected.HasLootPreferenceElement);Assert.Equal("Metal",projected.LootPreferenceElement);
    }

    [Fact]
    public void NullPreferenceDoesNotChangeTheHistoricalPreparationRequestJsonHashInput()
    {
        var request=new CreatePreparationRequest(HeroClassDto.Mage,7,[null,null,null,null,null],BackpackTierDto.Free,[],0,"Standard");
        const string original="{\"heroClass\":\"Mage\",\"deckVersion\":7,\"equipmentIds\":[null,null,null,null,null],\"backpackTier\":\"Free\",\"safeSlotIndexes\":[],\"potionCount\":0,\"difficulty\":\"Standard\"}";
        Assert.Equal(original,JsonSerializer.Serialize(request,Json));
        Assert.Contains("\"lootPreferenceElement\":\"Water\"",JsonSerializer.Serialize(request with {LootPreferenceElement="Water"},Json),StringComparison.Ordinal);
    }
}
