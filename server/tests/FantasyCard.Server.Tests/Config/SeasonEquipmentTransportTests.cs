using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using Wire=FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonEquipmentTransportTests
{
    private static readonly string[] RedChoiceActions=["choice.read","choice.pick"];
    [Theory]
    [InlineData(RoomPlayerPhase.Choice)] [InlineData(RoomPlayerPhase.Pvp)]
    [InlineData(RoomPlayerPhase.Dead)] [InlineData(RoomPlayerPhase.Extracted)]
    public void PendingRedOnlyReplacesChoicePermissionsAndNeverSuppressesAPlayersDuel(RoomPlayerPhase phase)
    {
        var config=GameConfigCatalog.Current;var id=Guid.NewGuid();var peer=Guid.NewGuid();
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,
            season:new("red-projection",2,"season-v1",config.Version,"season-equipment-v1"));
        foreach(var player in new[]{id,peer})room.AddPlayer(new(player,HeroClass.Mage,Enumerable.Range(1,20).Select(value=>$"C{value:D2}").ToArray(),null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,2));room.StartDuel(id,peer,DateTimeOffset.UnixEpoch);
        var state=new GetRoomClientStateCommand(id).Execute(room);
        var item=new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:SeasonRedConfig.Equipment(73,"season-equipment-v1","Fire",config.SeasonLootPreference),IsGenerated:false);
        // A projection-only control: actual mint/custody is covered by the
        // independent Domain and PostgreSQL tests, not by this authored snapshot.
        state=state with {Snapshot=state.Snapshot with {Players=state.Snapshot.Players.Select(value=>value.PlayerId==id
            ?value with {Phase=phase,PendingRedItem=item}:value).ToArray()}};
        var payload=RoomSnapshotProjection.Build(state,id,Guid.NewGuid(),DateTimeOffset.UnixEpoch);
        Assert.NotNull(payload.Player.PendingRedItem);
        if(phase==RoomPlayerPhase.Pvp)
        {
            Assert.Contains("battle.play_cards",payload.AllowedActions);Assert.DoesNotContain("choice.pick",payload.AllowedActions);
        }
        else if(phase==RoomPlayerPhase.Choice)Assert.Equal(RedChoiceActions,payload.AllowedActions);
        else Assert.Empty(payload.AllowedActions);
    }

    [Fact]
    public void HttpEquipmentAndPreparationKeepUniqueAffixAndOriginalStatsVersion()
    {
        var item=new EquipmentResponse(Guid.NewGuid(),"Head","Red",5,false,"Equipped",7,"Fire","Piercing","DrawInterval",
            StatsVersion:"season-equipment-v1",UniqueAffix:"Inferno",UniqueElement:"Fire");
        var wire=HttpDtoMapper.FromDto(Wire.EquipmentResponse.Descriptor,item);
        Assert.Equal(item,Assert.IsType<EquipmentResponse>(HttpDtoMapper.ToDto(wire,typeof(EquipmentResponse))));
        var preparation=new PreparationEquipmentSnapshotResponse(item.InstanceId,item.Slot,item.Quality,item.Level,"Fire",item.EffectAffix,item.SecondaryTrait,
            item.UniqueAffix,item.UniqueElement,item.StatsVersion);
        var snapshot=HttpDtoMapper.FromDto(Wire.PreparationEquipmentSnapshotResponse.Descriptor,preparation);
        Assert.Equal(preparation,Assert.IsType<PreparationEquipmentSnapshotResponse>(HttpDtoMapper.ToDto(snapshot,typeof(PreparationEquipmentSnapshotResponse))));
    }

    [Fact]
    public void PublicRoomProjectionAndRealBinaryCodecKeepRedDetailsAndPublishedNaturalFloor()
    {
        var config=GameConfigCatalog.Current;var id=Guid.NewGuid();var context=new SeasonContext("wire",5,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,season:context);
        ExplorationItem[] armor=[new(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Head","Red","Fire","Piercing","DrawInterval",5,UniqueAffix:"Inferno",UniqueElement:"Fire",StatsVersion:context.StatsVersion),IsGenerated:false)];
        room.AddPlayer(new(id,HeroClass.Mage,Enumerable.Range(1,20).Select(i=>$"C{i:D2}").ToArray(),null,WornArmor:armor));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1));
        var payload=RoomSnapshotProjection.Build(new GetRoomClientStateCommand(id).Execute(room),id,Guid.NewGuid(),DateTimeOffset.UnixEpoch);
        var frame=new ServerEvent("room.snapshot","equipment-wire",payload,Guid.NewGuid().ToString("D"),1,DateTimeOffset.UnixEpoch);
        var decoded=Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(frame)).Payload);
        var equipment=Assert.Single(decoded.Player.EquippedItems!).Equipment!;
        Assert.Equal("Inferno",equipment.UniqueAffix);Assert.Equal("Fire",equipment.UniqueElement);Assert.Equal(context.StatsVersion,equipment.StatsVersion);
        Assert.Equal(3.4,double.Parse(decoded.Player.BaseDrawIntervalSeconds!,System.Globalization.CultureInfo.InvariantCulture),8);
        Assert.Equal(70,decoded.Player.Combat.MaximumHp);
    }
}
