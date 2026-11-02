using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using Google.Protobuf;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Config;

public sealed class BorrowedDeckTransportTests
{
    private static readonly JsonSerializerOptions Serializer = CreateSerializer();

    private static JsonSerializerOptions CreateSerializer()
    {
        var options=new JsonSerializerOptions(JsonSerializerDefaults.Web);
        options.Converters.Add(new JsonStringEnumConverter());
        return options;
    }

    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void TypedHttpRequestPreservesBorrowedChoiceWithoutChangingDefaultOwnedRequest(bool borrowed)
    {
        var request=new CreatePreparationRequest(HeroClassDto.Mage,7,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D2","s",borrowed);
        var wire=Assert.IsType<Wire.CreatePreparationRequest>(HttpDtoMapper.FromDto(Wire.CreatePreparationRequest.Descriptor,request));
        Assert.Equal(borrowed,wire.UseBorrowedDeck);
        var contract=HttpProtocolRegistry.Find("POST","/api/v1/preparations")!;
        var decoded=Assert.IsType<CreatePreparationRequest>(HttpDtoMapper.DecodeRequest(contract,wire.ToByteArray(),typeof(CreatePreparationRequest)));
        Assert.Equal(borrowed,decoded.UseBorrowedDeck);Assert.Equal(request.DeckVersion,decoded.DeckVersion);Assert.Equal(request.SeasonId,decoded.SeasonId);
        var json=JsonSerializer.Serialize(request,Serializer);
        Assert.Equal(borrowed,json.Contains("useBorrowedDeck",StringComparison.Ordinal));
        if(!borrowed)Assert.Equal("{\"heroClass\":\"Mage\",\"deckVersion\":7,\"equipmentIds\":[null,null,null,null,null],\"backpackTier\":\"Free\",\"safeSlotIndexes\":[],\"potionCount\":0,\"difficulty\":\"D2\",\"seasonId\":\"s\"}",json);
    }

    [Fact]
    public void BorrowedSourceAndEffectiveLevelsRoundTripPublicRealtimeAndHttpSnapshots()
    {
        var config=GameConfigCatalog.Current;var template=config.BorrowedDeck(HeroClass.Priest);
        var context=new SeasonContext("loans",4,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,season:context);
        var id=Guid.NewGuid();room.AddPlayer(new(id,HeroClass.Priest,template.CardIds,null,WeaponLevel:4,CardLevels:Enumerable.Repeat(4,20).ToArray(),BorrowedTemplateId:template.TemplateId));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1));
        var payload=RoomSnapshotProjection.Build(new GetRoomClientStateCommand(id).Execute(room),id,Guid.NewGuid(),DateTimeOffset.UnixEpoch);
        var envelope=new ServerEvent("room.snapshot","loan-test",payload,Guid.NewGuid().ToString("D"),1,DateTimeOffset.UnixEpoch);
        var decoded=Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(envelope)).Payload);
        Assert.Equal(template.TemplateId,decoded.Player.BorrowedTemplateId);
        Assert.Equal(80,decoded.Player.Combat.MaximumHp);
        Assert.Equal(4,decoded.Player.WeaponLevel);
        Assert.All(decoded.Player.Hand,card=>Assert.Equal(4,card.Level));
        var preparation=new PreparationSnapshotResponse(HeroClassDto.Priest,80,template.CardIds,[null,null,null,null,null],4,BackpackTierDto.Free,24,[],0,"D4",config.Version,CardLevels:Enumerable.Repeat(4,20).ToArray(),ActualCardLevels:Enumerable.Repeat(0,20).ToArray(),ActualClassWeaponLevel:1,BorrowedTemplateId:template.TemplateId);
        var typed=HttpDtoMapper.FromDto(Wire.PreparationSnapshotResponse.Descriptor,preparation);
        var roundTrip=Assert.IsType<PreparationSnapshotResponse>(HttpDtoMapper.ToDto(typed,typeof(PreparationSnapshotResponse)));
        Assert.Equal(template.TemplateId,roundTrip.BorrowedTemplateId);
        Assert.Equal(preparation.CardLevels,roundTrip.CardLevels);Assert.Equal(preparation.ActualCardLevels,roundTrip.ActualCardLevels);Assert.Equal(1,roundTrip.ActualClassWeaponLevel);
    }
}
