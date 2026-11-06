using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RoomPlaytimeObservationTests
{
    private static readonly Guid First=Guid.Parse("11111111-1111-1111-1111-111111111111");
    private static readonly Guid Second=Guid.Parse("22222222-2222-2222-2222-222222222222");
    private static readonly DateTimeOffset Epoch=DateTimeOffset.UnixEpoch;
    private static CombatCardCatalog Catalog()=>CombatCardCatalog.CreatePrototype();
    private static BattleRoom Room(bool actionBar=true,bool secondIsBot=false)
    {
        var room=new BattleRoom(Guid.NewGuid(),"clock-fixture",Catalog(),73);
        var deck=Enumerable.Range(1,20).Select(i=>$"common-{i:D2}").ToArray();
        room.AddPlayer(new(First,HeroClass.Mage,deck,null));room.AddPlayer(new(Second,HeroClass.Priest,deck,null,IsBot:secondIsBot));
        room.InitializeMap(ChaosMapGenerator.Generate(73,2),Epoch);
        if(!actionBar)return room;
        var state=room.Capture();var evacuation=state.Map!.Cells.First(c=>c.HasEvacuation).Position;
        return BattleRoom.Restore(state with{Players=state.Players.Select(p=>p with{Phase=RoomPlayerPhase.ActionBar,Pve=null,BotPveRemaining=null,Position=evacuation,ClearedCells=[evacuation]}).ToArray()},Catalog(),73);
    }

    [Fact]
    public void DisconnectDeadlineIsRecordedOnceEvenWhenRoomContinuesAndTheStepOvershoots()
    {
        var room=Room();room.Advance(TimeSpan.FromSeconds(2),Epoch.AddSeconds(2));room.MarkPlayerDisconnected(First);
        room.Advance(TimeSpan.FromSeconds(60),Epoch.AddSeconds(62));
        Assert.Equal(TimeSpan.FromSeconds(17),room.GetPlayer(First).TerminalRoomElapsed);Assert.Null(room.GetPlayer(Second).TerminalRoomElapsed);
        room.Advance(TimeSpan.FromMinutes(5),Epoch.AddSeconds(362));
        var saved=room.Capture();var restored=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(saved))!,Catalog(),73);
        Assert.Equal(TimeSpan.FromSeconds(17),restored.GetPlayer(First).TerminalRoomElapsed);Assert.Equal(Epoch,restored.StartedAtUtc);
        Assert.Equal(saved.RandomStreams,restored.Capture().RandomStreams);Assert.Equal(saved.Elapsed,restored.Elapsed);
    }

    [Fact]
    public void ExtractionUsesItsLogicalCompletionRatherThanTheEndOfAnOversizedTick()
    {
        var room=Room();var duration=room.RequestExtraction(First);room.Advance(duration+TimeSpan.FromSeconds(4),Epoch+duration+TimeSpan.FromSeconds(4));
        var player=room.GetPlayer(First);Assert.Equal(RoomPlayerPhase.Extracted,player.Phase);Assert.Equal(duration,player.TerminalRoomElapsed);Assert.Equal(Epoch+duration,player.ExtractionCompletedAt);
        room.Advance(TimeSpan.FromSeconds(10),Epoch+duration+TimeSpan.FromSeconds(14));Assert.Equal(duration,player.TerminalRoomElapsed);
    }

    [Fact]
    public void AbandonAndDuelDisconnectDoNotBorrowTheOtherPlayersRoomLifetime()
    {
        var active=Room(false);active.AbandonBattle(First);Assert.Equal(TimeSpan.Zero,active.GetPlayer(First).TerminalRoomElapsed);
        var duelRoom=Room();var duel=duelRoom.StartDuel(First,Second,Epoch);Assert.Equal(duel.DuelId,Assert.Single(duelRoom.Capture().Duels).DuelId);duelRoom.MarkPlayerDisconnected(First);
        duelRoom.Advance(TimeSpan.FromSeconds(19),Epoch.AddSeconds(19));
        Assert.Equal(TimeSpan.FromSeconds(15),duelRoom.GetPlayer(First).TerminalRoomElapsed);Assert.Null(duelRoom.GetPlayer(Second).TerminalRoomElapsed);
        Assert.Empty(duelRoom.Capture().Duels);Assert.Equal(RoomPlayerPhase.ActionBar,duelRoom.GetPlayer(Second).Phase);
    }

    [Fact]
    public void BotTerminationHasItsOwnObservedClockAndRemainsExplicitlyBotData()
    {
        var room=Room(secondIsBot:true);room.MarkPlayerDisconnected(First);room.Advance(TimeSpan.FromSeconds(16),Epoch.AddSeconds(16));
        Assert.Equal(TimeSpan.FromSeconds(15),room.GetPlayer(First).TerminalRoomElapsed);
        Assert.True(room.GetPlayer(Second).IsBot);Assert.Equal(RoomPlayerPhase.Extracted,room.GetPlayer(Second).Phase);Assert.Equal(TimeSpan.FromSeconds(16),room.GetPlayer(Second).TerminalRoomElapsed);
    }

    [Fact]
    public void LegacyMissingClocksStayMissingInsteadOfBeingReconstructedFromElapsed()
    {
        var source=Room().Capture();var legacy=source with{StartedAtUtc=null,Observations=null,Elapsed=TimeSpan.FromHours(2),Players=source.Players.Select(p=>p with{Phase=RoomPlayerPhase.Dead,Pve=null,Combat=p.Combat with{Hp=0},TerminalRoomElapsed=null}).ToArray()};
        var restored=BattleRoom.Restore(legacy,Catalog(),73).Capture();Assert.Null(restored.StartedAtUtc);Assert.All(restored.Players,p=>Assert.Null(p.TerminalRoomElapsed));
        var raw=JsonSerializer.Serialize(restored);Assert.DoesNotContain("TerminalRoomElapsed",raw,StringComparison.Ordinal);Assert.DoesNotContain("StartedAtUtc",raw,StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(-1,true)] [InlineData(11,true)] [InlineData(1,false)]
    public void ExplicitBadClockIsRejectedWithoutReinterpretingOtherSavedFields(int seconds,bool terminal)
    {
        var saved=Room().Capture();saved=saved with{Elapsed=TimeSpan.FromSeconds(10),Players=saved.Players.Select(p=>p with{Phase=terminal?RoomPlayerPhase.Dead:RoomPlayerPhase.ActionBar,Pve=null,Combat=p.Combat with{Hp=terminal?0:p.Combat.Hp},TerminalRoomElapsed=TimeSpan.FromSeconds(seconds)}).ToArray()};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(saved,Catalog(),73));
    }
}
