using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class SeasonJourneyCompletionTests
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};

    [Theory]
    [InlineData(ChaosMapLayer.Outer,"O1",false)]
    [InlineData(ChaosMapLayer.Middle,"M1",false)]
    [InlineData(ChaosMapLayer.Core,"E1",false)]
    [InlineData(ChaosMapLayer.Core,"BOSS",true)]
    public void ActualFinalCardCreatesOneOriginalTimedClearAndRecoveryKeepsIt(ChaosMapLayer layer,string group,bool boss)
    {
        var (room,id)=Room(layer,group,boss);var player=room.GetPlayer(id);var battle=player.Pve!.BattleId;
        var now=new DateTimeOffset(2026,11,20,12,0,0,TimeSpan.FromHours(8));
        foreach(var monster in player.Pve.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp+monster.Shield-1);SeasonFenxianTests.SetHand(player,"C01");
            room.PlayCards(id,battle,monster.MonsterId,[player.Combat.Deck.Hand[0].InstanceId],room.Revision,now,room.NewCombatActionId(id));
            room.Advance(TimeSpan.FromMilliseconds(500),now);now=now.AddSeconds(1);
        }
        var snapshot=room.Capture();var source=Assert.Single(Assert.Single(snapshot.Players).JourneyCompletions!);
        Assert.Equal(battle,source.BattleId);Assert.Equal(group,source.MonsterGroupId);Assert.Equal(TimeSpan.Zero,source.CompletedAt.Offset);
        Assert.Contains(source.Position,Assert.Single(snapshot.Players).ClearedCells!);
        var restored=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(snapshot,Json),Json)!,CombatCardCatalog.Create(GameConfigCatalog.Current),73);
        Assert.Equal(source,Assert.Single(restored.Capture().Players[0].JourneyCompletions!));
        restored.Advance(TimeSpan.FromSeconds(5),now.AddDays(2));
        Assert.Equal(source,Assert.Single(restored.Capture().Players[0].JourneyCompletions!));
    }

    [Fact]
    public void SnapshotCannotDuplicateOrRenameAnOriginalClear()
    {
        var (room,id)=Room(ChaosMapLayer.Outer,"O1",false);var player=room.GetPlayer(id);var snapshot=room.Capture();
        var position=player.Position!.Value;
        var completion=new SeasonCellCompletionSnapshot(position,"O1",player.Pve!.BattleId,DateTimeOffset.UtcNow);
        snapshot=snapshot with {Players=[snapshot.Players[0] with {ClearedCells=[position],JourneyCompletions=[completion,completion]}]};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73));
        snapshot=snapshot with {Players=[snapshot.Players[0] with {JourneyCompletions=[completion with {MonsterGroupId="BOSS"}]}]};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73));
    }

    [Fact]
    public void APreviousClearedCellWithoutAnOriginalTimeIsNeverRetrofittedFromRecoveryClock()
    {
        var (room,id)=Room(ChaosMapLayer.Outer,"O1",false);var snapshot=room.Capture();var position=room.GetPlayer(id).Position!.Value;
        snapshot=snapshot with {Players=[snapshot.Players[0] with {ClearedCells=[position],JourneyCompletions=null}]};
        var restored=BattleRoom.Restore(snapshot,CombatCardCatalog.Create(GameConfigCatalog.Current),73);
        Assert.Null(restored.Capture().Players[0].JourneyCompletions);
        var serialized=JsonSerializer.Serialize(restored.Capture(),Json);
        Assert.DoesNotContain("journeyCompletions",serialized,StringComparison.Ordinal);
    }

    private static (BattleRoom Room,Guid Player) Room(ChaosMapLayer layer,string group,bool boss)
    {
        var config=GameConfigCatalog.Current;var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,
            season:new("journey-checkpoint",0,"season-v1",config.Version,"season-equipment-v1"));var id=Guid.NewGuid();
        room.AddPlayer(new(id,HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),null));
        var map=ChaosMapGenerator.Generate(73,1).Capture();var start=map.SpawnPositions[0];
        map=map with {Cells=map.Cells.Select(c=>c.Position==start?c with {Layer=layer,MonsterGroupId=group,IsBoss=boss}:c).ToArray()};
        room.InitializeMap(ChaosMapState.Restore(map));return(room,id);
    }
}
