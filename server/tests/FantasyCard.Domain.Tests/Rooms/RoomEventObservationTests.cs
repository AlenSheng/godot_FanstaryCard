using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RoomEventObservationTests
{
    private static readonly Guid First=Guid.Parse("11111111-1111-1111-1111-111111111111");
    private static readonly Guid Second=Guid.Parse("22222222-2222-2222-2222-222222222222");
    private static readonly DateTimeOffset Epoch=DateTimeOffset.UnixEpoch;
    private static CombatCardCatalog Catalog()=>CombatCardCatalog.CreatePrototype();
    private static BattleRoom Room()
    {
        var room=new BattleRoom(Guid.NewGuid(),"observations-fixture",Catalog(),73);var deck=Enumerable.Range(1,20).Select(i=>$"common-{i:D2}").ToArray();
        room.AddPlayer(new(First,HeroClass.Mage,deck,null));room.AddPlayer(new(Second,HeroClass.Priest,deck,null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,2),Epoch);return room;
    }
    private static BattleRoom Restore(BattleRoomSnapshot snapshot)=>BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(snapshot))!,Catalog(),73);
    private static BattleRoom Choice()
    {
        var room=Room();var snapshot=room.Capture();var choice=RewardChoiceState.Create(ChaosMapLayer.Outer,new Random(4));
        return Restore(snapshot with{Players=snapshot.Players.Select(p=>p.PlayerId==First?p with{Phase=RoomPlayerPhase.Choice,Pve=null,RewardChoice=choice.Capture()}:p).ToArray()});
    }

    [Fact]
    public void AbandonObservesBattleAndCustodyOnceAndRestoredOtherPlayerContinuesTheSameSequence()
    {
        var room=Room();room.GetPlayer(First).Inventory.TryAdd(new("gold",ExplorationItemKind.Gold,9));room.AbandonBattle(First);
        var first=room.Capture();Assert.Equal(2,first.Observations!.Events.Count);
        var battle=Assert.Single(first.Observations.Events,e=>e.EventName=="battle_finished");Assert.Equal("Abandoned",battle.Result);Assert.NotNull(battle.BattleId);
        var loss=Assert.Single(first.Observations.Events,e=>e.EventName=="loot_lost");Assert.Equal(9,Assert.Single(loss.Items).Quantity);
        Assert.Equal("RelicCustodyPendingSettlement",loss.Result);Assert.Throws<DomainValidationException>(()=>room.AbandonBattle(First));Assert.Equal(2,room.Capture().Observations!.LastSequence);
        var restored=Restore(first);Assert.Equal(JsonSerializer.Serialize(first.Observations),JsonSerializer.Serialize(restored.Capture().Observations));
        restored.AbandonBattle(Second);Assert.Equal(4,restored.Capture().Observations!.LastSequence);Assert.Equal(new long[]{1,2,3,4},restored.Capture().Observations!.Events.Select(e=>e.Sequence));
    }

    [Fact]
    public void RefreshHasThreePotentialAlternativesAndReplayDoesNotGenerateAgainWhileActualZeroHealIsAChosenEvent()
    {
        var room=Choice();var revision=room.Revision;var receipt=room.RefreshRewardChoice(First,revision,60,"observed-refresh");
        var events=room.Capture().Observations!.Events;Assert.Equal(3,events.Count);Assert.All(events,e=>Assert.Equal("PotentialChoice",e.Result));
        Assert.Equal(3,events.Select(e=>e.OptionId).Distinct().Count());Assert.Contains(events,e=>e.HealPercent>0&&e.Items.Count==0);
        Assert.Equal(receipt,room.RefreshRewardChoice(First,revision,60,"observed-refresh"));Assert.Equal(3,room.Capture().Observations!.LastSequence);
        var heal=room.GetRewardChoice(First).Options.Single(o=>o.Kind==RewardChoiceKind.ImmediateHeal);
        Assert.Equal(0,room.ClaimReward(First,heal.OptionId));var chosen=Assert.Single(room.Capture().Observations!.Events,e=>e.EventName=="loot_chosen");
        Assert.Equal(0,chosen.AppliedQuantity);Assert.Equal(70,chosen.HpBefore);Assert.Equal(70,chosen.EffectiveMaximumHp);Assert.Empty(chosen.Items);
        Assert.Equal(4,Restore(room.Capture()).Capture().Observations!.LastSequence);
    }

    [Fact]
    public void DeclaredClearedCheckpointAndExtractionHaveSeparateBattleAndPendingAssetExitObservations()
    {
        var room=Room();var player=room.GetPlayer(First);
        // Declared terminal monster-state fixture, no successful player casts or gameplay campaign.
        foreach(var monster in player.Pve!.Monsters)monster.TakeDamage(int.MaxValue);player.Pve.RefreshPhase();
        Assert.True(room.TryEnterActionBar(First));Assert.False(room.TryEnterActionBar(First));
        Assert.Single(room.Capture().Observations!.Events,e=>e.EventName=="battle_finished");
        var snapshot=room.Capture();var exit=snapshot.Map!.Cells.First(c=>c.HasEvacuation).Position;
        room=Restore(snapshot with{Players=snapshot.Players.Select(p=>p.PlayerId==First?p with{Position=exit,Pve=null,ClearedCells=[exit]}:p).ToArray()});
        room.GetPlayer(First).Inventory.TryAdd(new("gold",ExplorationItemKind.Gold,5));var duration=room.RequestExtraction(First);
        room.Advance(duration+TimeSpan.FromSeconds(2),Epoch+duration+TimeSpan.FromSeconds(2));
        var extracted=Assert.Single(room.Capture().Observations!.Events,e=>e.EventName=="loot_extracted");
        Assert.Equal(duration,extracted.RoomElapsed);Assert.Equal(Epoch+duration,extracted.OccurredAtUtc);Assert.Equal("RoomExitPendingSettlement",extracted.Result);Assert.Equal(5,Assert.Single(extracted.Items).Quantity);
    }

    [Fact]
    public void PvpDeathAlsoRecordsTheFrozenPveThatCannotResume()
    {
        var room=Room();var original=room.GetPlayer(First).Pve!.BattleId;var duel=room.StartDuel(First,Second,Epoch);
        room.EndDuelWithDeath(duel.DuelId,First);var events=room.Capture().Observations!.Events;
        Assert.Contains(events,e=>e.EventName=="battle_finished"&&e.PlayerId==First&&e.BattleId==original&&e.Result=="InterruptedByPvpDeath");
        Assert.Equal(2,events.Count(e=>e.EventName=="battle_finished"&&e.BattleId==duel.DuelId));
    }

    [Fact]
    public void CapacityIsBoundedAndTheExplicitGapSurvivesRestore()
    {
        var room=Choice();var saved=room.Capture();var template=new RoomEventObservation(1,First,HeroClass.Mage,false,"loot_generated","DeclaredBoundaryFixture","PotentialChoice",TimeSpan.Zero,Epoch,null,null,"Unknown",[],0,70,70);
        var metadata=Enumerable.Range(1,4096).Select(i=>template with{Sequence=i}).ToArray();
        room=Restore(saved with{Observations=new(1,4096,0,metadata)});room.RefreshRewardChoice(First,room.Revision,60,"at-cap");
        var bounded=room.Capture().Observations!;Assert.Equal(4096,bounded.Events.Count);Assert.Equal(4099,bounded.LastSequence);Assert.Equal(3,bounded.DroppedEvents);
        Assert.Equal(3,Restore(room.Capture()).Capture().Observations!.DroppedEvents);
    }

    [Fact]
    public void MissingLegacyJournalIsNotInventedEvenWhenItsOriginalUtcStartIsKnown()
    {
        var room=Restore(Room().Capture() with{Observations=null});room.AbandonBattle(First);Assert.Null(room.Capture().Observations);
    }

    [Fact]
    public void ObservationDoesNotChangeRefreshRandomnessPricesOrGameplayState()
    {
        var enabled=Choice();var disabled=Restore(enabled.Capture() with{Observations=null});
        enabled.RefreshRewardChoice(First,enabled.Revision,60,"same");disabled.RefreshRewardChoice(First,disabled.Revision,60,"same");
        var choice=enabled.GetRewardChoice(First).Options.Single(o=>o.Kind==RewardChoiceKind.ImmediateHeal).OptionId;
        enabled.ClaimReward(First,choice);disabled.ClaimReward(First,choice);
        Assert.Equal(JsonSerializer.Serialize(enabled.Capture() with{Observations=null}),JsonSerializer.Serialize(disabled.Capture()));
    }

    [Theory]
    [InlineData("player")][InlineData("time")][InlineData("sequence")][InlineData("class")][InlineData("version")]
    public void InvalidNewJournalIsRejectedWithoutRepairingIt(string change)
    {
        var room=Room();room.AbandonBattle(First);var snapshot=room.Capture();var journal=snapshot.Observations!;var events=journal.Events.ToArray();
        events[0]=change switch{"player"=>events[0] with{PlayerId=Guid.Empty},"time"=>events[0] with{OccurredAtUtc=Epoch.AddSeconds(1)},"sequence"=>events[0] with{Sequence=2},"class"=>events[0] with{HeroClass=HeroClass.Guardian},_=>events[0]};
        journal=journal with{Events=events,SchemaVersion=change=="version"?2:1};
        Assert.Throws<DomainValidationException>(()=>Restore(snapshot with{Observations=journal}));
    }
}
