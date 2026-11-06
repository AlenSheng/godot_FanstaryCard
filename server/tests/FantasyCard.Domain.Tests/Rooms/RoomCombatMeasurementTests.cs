using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RoomCombatMeasurementTests
{
    private static readonly Guid First=Guid.Parse("11111111-1111-1111-1111-111111111111");
    private static readonly Guid Second=Guid.Parse("22222222-2222-2222-2222-222222222222");
    private static readonly DateTimeOffset Epoch=DateTimeOffset.UnixEpoch;
    private static CombatCardCatalog Catalog()=>new([new("low",new CombatCardEffect(DirectDamage:3,Heal:5,Shield:6,DrawCharge:.2,ImmediateDraw:1,StunSeconds:1))]);
    private static BattleRoom Room(bool second=false,CombatEquipmentProfile? equipment=null,bool seasonal=false)
    {
        var room=new BattleRoom(Guid.NewGuid(),"combat-fixture",Catalog(),73,season:seasonal?new SeasonContext("counter-season",0,"season-v1","combat-fixture","counter-stats"):null);
        room.AddPlayer(new(First,HeroClass.Mage,Enumerable.Repeat("low",20).ToArray(),null,Equipment:equipment));
        if(second)room.AddPlayer(new(Second,HeroClass.Priest,Enumerable.Repeat("low",20).ToArray(),null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,second?2:1),Epoch);return room;
    }
    private static RoomCombatObservation Row(BattleRoom room,Guid? battle)=>Assert.Single(room.Capture().Observations!.Combat!.Rows,r=>r.PlayerId==First&&r.BattleId==battle);
    private static long Count(RoomCombatObservation row,CombatMetric metric)=>row.Counters.GetValueOrDefault(metric.ToString());

    [Fact]
    public void NaturalEffectiveEmptyAndFullResetDifferFromRequestedInstantDraws()
    {
        var room=Room();var player=room.GetPlayer(First);var battle=player.Pve!.BattleId;
        player.Combat.Advance(TimeSpan.FromSeconds(8),true);Assert.Equal(5,player.Combat.Deck.Hand.Count);
        player.Combat.Advance(TimeSpan.FromSeconds(8),true);player.Combat.DrawImmediate(3);
        player.Combat.Deck.DiscardPlayed(player.Combat.Deck.Hand.ToArray());player.Combat.DrawImmediate(2);
        player.Combat.Deck.Restore(new([],[],[],0));player.Combat.DrawImmediate(3);player.Combat.Advance(TimeSpan.FromSeconds(4),true);
        var row=Row(room,battle);Assert.Equal(3,Count(row,CombatMetric.EntryHandObserved));Assert.Equal(3,Count(row,CombatMetric.NaturalAttempts));
        Assert.Equal(2,Count(row,CombatMetric.NaturalEffective));Assert.Equal(1,Count(row,CombatMetric.NaturalEmpty));Assert.Equal(1,Count(row,CombatMetric.NaturalFullResets));Assert.Equal(2,Count(row,CombatMetric.NaturalDiscardedWholeCharge));
        Assert.Equal(8,Count(row,CombatMetric.InstantRequested));Assert.Equal(2,Count(row,CombatMetric.InstantEffective));Assert.Equal(3,Count(row,CombatMetric.InstantEmpty));Assert.Equal(3,Count(row,CombatMetric.InstantFullBlocked));
    }

    [Fact]
    public void ChainDrawIsNotReportedAsAnotherNaturalCard()
    {
        var room=Room(equipment:CombatEquipmentProfile.Empty with{ChainDrawBasisPoints=10000});var player=room.GetPlayer(First);var battle=player.Pve!.BattleId;
        player.Combat.Advance(TimeSpan.FromSeconds(4),true);var row=Row(room,battle);
        Assert.Equal(1,Count(row,CombatMetric.NaturalEffective));Assert.Equal(1,Count(row,CombatMetric.ChainEffective));Assert.Equal(5,player.Combat.Deck.Hand.Count);
    }

    [Fact]
    public void OverlappingPlayerControlAndEnemyTimerVersusSuppressedStepHaveDifferentDenominators()
    {
        var room=Room();var player=room.GetPlayer(First);var battle=player.Pve!.BattleId;
        player.Combat.ApplyStun(TimeSpan.FromSeconds(3));player.Combat.ApplyDrawBlock(TimeSpan.FromSeconds(4));room.Advance(TimeSpan.FromSeconds(5),Epoch.AddSeconds(5));
        var row=Row(room,battle);Assert.Equal(TimeSpan.FromSeconds(3).Ticks,Count(row,CombatMetric.StunnedTicks));Assert.Equal(TimeSpan.FromSeconds(4).Ticks,Count(row,CombatMetric.UnionBlockedTicks));Assert.Equal(TimeSpan.FromSeconds(1).Ticks,Count(row,CombatMetric.EligibleDrawTicks));
        player.Pve!.Monsters[0].ApplyStun(TimeSpan.FromSeconds(1));room.Advance(TimeSpan.FromSeconds(2),Epoch.AddSeconds(7));row=Row(room,battle);
        Assert.Equal(TimeSpan.FromSeconds(1).Ticks,Count(row,CombatMetric.EnemyStunTimerTicks));Assert.Equal(TimeSpan.FromSeconds(2).Ticks,Count(row,CombatMetric.EnemyStunSuppressedTicks));
    }

    [Fact]
    public void Legal80Over70UsesEffective98AndReportsActualHealingAndShieldOverflow()
    {
        var room=Room(equipment:CombatEquipmentProfile.Empty with{VitalityOvercapBonus=.4});var player=room.GetPlayer(First);var battle=player.Pve!.BattleId;
        Assert.Equal(10,player.Combat.Heal(10));Assert.Equal(80,player.Combat.Hp);Assert.Equal(98,player.Combat.EffectiveMaximumHp);Assert.Equal(18,player.Combat.Heal(30));
        Assert.Equal(35,player.Combat.GainShield(100));Assert.Equal(0,player.Combat.GainShield(10));var row=Row(room,battle);
        Assert.Equal(40,Count(row,CombatMetric.HealRequested));Assert.Equal(28,Count(row,CombatMetric.HealApplied));Assert.Equal(12,Count(row,CombatMetric.HealOverflow));
        Assert.Equal(110,Count(row,CombatMetric.ShieldRequested));Assert.Equal(35,Count(row,CombatMetric.ShieldApplied));Assert.Equal(75,Count(row,CombatMetric.ShieldOverflow));Assert.Equal(0,Count(row,CombatMetric.HealClampCorrection));
    }

    [Fact]
    public void SuccessfulCastReplayDoesNotRepeatMeasurements()
    {
        var room=Room(seasonal:true);var player=room.GetPlayer(First);var battle=player.Pve!.BattleId;var target=player.Pve.Monsters[0].MonsterId;var card=player.Combat.Deck.Hand[0].InstanceId;
        var id="1:"+Guid.NewGuid().ToString("N");var result=room.PlayCards(First,battle,target,[card],room.Revision,Epoch,id);Assert.False(result.BattleEnded);
        var before=JsonSerializer.Serialize(room.Capture().Observations!.Combat);var replay=room.PlayCards(First,battle,target,[card],room.Revision,Epoch,id);
        Assert.True(replay.ActionReplayed);Assert.Equal(before,JsonSerializer.Serialize(room.Capture().Observations!.Combat));Assert.Equal(1,Count(Row(room,battle),CombatMetric.Casts));
    }

    [Fact]
    public void PvpCountersDoNotDisappearWhenFrozenPveStateReturns()
    {
        var room=Room(second:true);var pve=room.GetPlayer(First).Pve!.BattleId;room.Advance(TimeSpan.FromSeconds(1),Epoch.AddSeconds(1));
        var duel=room.StartDuel(First,Second,Epoch.AddSeconds(1));room.Advance(TimeSpan.FromSeconds(2),Epoch.AddSeconds(3));room.EndDuelSurvived(duel.DuelId,DuelEndReason.MutualLeave);room.Advance(TimeSpan.FromSeconds(1),Epoch.AddSeconds(4));
        Assert.Equal(TimeSpan.FromSeconds(2).Ticks,Count(Row(room,pve),CombatMetric.AdvancedTicks));Assert.Equal(TimeSpan.FromSeconds(2).Ticks,Count(Row(room,duel.DuelId),CombatMetric.AdvancedTicks));
        Assert.Equal(3,Count(Row(room,duel.DuelId),CombatMetric.OpeningEffective));
        room=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(room.Capture()))!,Catalog(),73);room.Advance(TimeSpan.FromSeconds(1),Epoch.AddSeconds(5));
        Assert.Equal(TimeSpan.FromSeconds(3).Ticks,Count(Row(room,pve),CombatMetric.AdvancedTicks));Assert.Equal(TimeSpan.FromSeconds(2).Ticks,Count(Row(room,duel.DuelId),CombatMetric.AdvancedTicks));
    }

    [Fact]
    public void OldMissingCountersStartPartialWithoutClaimingPastAdvancesWereZero()
    {
        var room=Room();room.Advance(TimeSpan.FromSeconds(2),Epoch.AddSeconds(2));var snapshot=room.Capture();snapshot=snapshot with{Observations=snapshot.Observations! with{Combat=null}};
        room=BattleRoom.Restore(snapshot,Catalog(),73);var battle=room.GetPlayer(First).Pve!.BattleId;room.Advance(TimeSpan.FromSeconds(1),Epoch.AddSeconds(3));
        Assert.True(room.Capture().Observations!.Combat!.HistoryMissing);var row=Row(room,battle);Assert.True(row.Partial);Assert.Equal(TimeSpan.FromSeconds(2),row.ObservedFromRoomElapsed);Assert.Equal(TimeSpan.FromSeconds(1).Ticks,Count(row,CombatMetric.AdvancedTicks));
    }

    [Fact]
    public void ObserverLeavesSuccessfulResolverStateAndRandomStreamsUnchanged()
    {
        var enabled=Room();var disabled=BattleRoom.Restore(enabled.Capture() with{Observations=null},Catalog(),73);
        foreach(var room in new[]{enabled,disabled})
        {
            var player=room.GetPlayer(First);room.PlayCards(First,player.Pve!.BattleId,player.Pve.Monsters[0].MonsterId,[player.Combat.Deck.Hand[0].InstanceId],room.Revision,Epoch);
            player.Combat.ApplyStun(TimeSpan.FromSeconds(1));room.Advance(TimeSpan.FromSeconds(5),Epoch.AddSeconds(5));
        }
        Assert.Equal(JsonSerializer.Serialize(enabled.Capture() with{Observations=null}),JsonSerializer.Serialize(disabled.Capture()));
    }

    [Fact]
    public void ZeroDamageAttackIsObservedButZeroUtilityIsNotAnotherDamageIntent()
    {
        var room=Room();var snapshot=room.Capture();var monster=new MonsterCombatState("zero",100,100,0,TimeSpan.FromSeconds(2),[new(MonsterIntentKind.Attack,0,CardElement.None),new(MonsterIntentKind.Shield,0,CardElement.None)]);
        var pve=new PveBattleState(Guid.NewGuid(),"zero",[monster]);room=BattleRoom.Restore(snapshot with{Players=snapshot.Players.Select(p=>p with{Pve=pve.Capture()}).ToArray()},Catalog(),73);
        room.Advance(TimeSpan.FromSeconds(2),Epoch.AddSeconds(2));room.Advance(TimeSpan.FromSeconds(1),Epoch.AddSeconds(3));room.Advance(TimeSpan.FromSeconds(2),Epoch.AddSeconds(5));room.Advance(TimeSpan.FromSeconds(1),Epoch.AddSeconds(6));
        var row=Row(room,pve.BattleId);Assert.Equal(1,Count(row,CombatMetric.DamageIntents));Assert.Equal(1,Count(row,CombatMetric.ZeroResolvedDamageIntents));Assert.Equal(1,Count(row,CombatMetric.ZeroAppliedDamageIntents));
    }

    [Theory]
    [InlineData("negative")][InlineData("metric")][InlineData("version")]
    public void InvalidNewCombatRecordsAreRejectedWithoutRepair(string change)
    {
        var room=Room();var snapshot=room.Capture();var combat=snapshot.Observations!.Combat!;var row=combat.Rows[0];var counters=new Dictionary<string,long>(row.Counters);
        if(change=="negative")counters[nameof(CombatMetric.Casts)]=-1;
        if(change=="metric")counters["player-specific-label"]=1;
        combat=combat with{SchemaVersion=change=="version"?2:1,Rows=[row with{Counters=counters}]};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(snapshot with{Observations=snapshot.Observations with{Combat=combat}},Catalog(),73));
    }
}
