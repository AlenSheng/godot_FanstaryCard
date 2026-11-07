using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RoomBuildProfileTests
{
    private static readonly Guid Player=Guid.Parse("11111111-1111-1111-1111-111111111111");
    private static CombatCardCatalog Catalog()=>CombatCardCatalog.CreatePrototype();
    private static BattleRoom Room(int level=0,IReadOnlyList<ExplorationItem>? armor=null)
    {
        var room=new BattleRoom(Guid.NewGuid(),"build-fixture",Catalog(),73);
        var equipment=armor is null?null:EquipmentCombatRules.Calculate(armor.Select(item=>new CombatEquipmentItem(Guid.Parse(item.ItemId),item.Equipment!.Slot,item.Equipment.Quality,item.Equipment.Level,
            Enum.Parse<CardElement>(item.Equipment.Element),item.Equipment.EffectAffix,item.Equipment.SecondaryTrait,item.Equipment.UniqueAffix,
            item.Equipment.UniqueElement is null?null:Enum.Parse<CardElement>(item.Equipment.UniqueElement))).ToArray(),Catalog().Configuration);
        room.AddPlayer(new(Player,HeroClass.Mage,Enumerable.Repeat("C01",20).ToArray(),null,WeaponLevel:level,WornArmor:armor,Equipment:equipment,CardLevels:Enumerable.Repeat(level,20).ToArray()));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1),DateTimeOffset.UnixEpoch);return room;
    }

    [Theory]
    [InlineData(0)][InlineData(1)][InlineData(2)][InlineData(3)][InlineData(4)][InlineData(5)]
    public void GrowthNamesTheEffectiveBaseCardMaximumWithoutPretendingToBeDiagnosticP0P5OrAccountAge(int level)
    {
        var room=Room(level);var player=room.GetPlayer(Player);var profile=RoomBuildProfiles.Capture(player,Catalog())!;profile.RequireValid();
        Assert.Equal("EffectiveBaseCardMaxL"+level,profile.GrowthStage);Assert.Equal(level,profile.WeaponLevel);Assert.Equal("MonoFire/NoActiveEffectSet",profile.BuildType);
        player.Combat.Deck.AddToDiscard(new(Guid.NewGuid(),"M-BOXSPIRIT",0,CardElement.Water));
        var diluted=RoomBuildProfiles.Capture(player,Catalog())!;Assert.Equal(profile.GrowthStage,diluted.GrowthStage);Assert.NotEqual(profile.ProfileId,diluted.ProfileId);
        Assert.Equal(20,Assert.Single(profile.Cards).Count);Assert.Equal(21,diluted.Cards.Sum(c=>c.Count));
    }

    [Fact]
    public void FingerprintIgnoresHandOrderAndPhysicalCardIdsButRetainsEffectiveComposition()
    {
        var room=Room(2);var player=room.GetPlayer(Player);var before=RoomBuildProfiles.Capture(player,Catalog())!;var deck=player.Combat.Deck.Capture();
        player.Combat.Deck.Restore(deck with{Hand=deck.Hand.Reverse().Select(c=>c with{InstanceId=Guid.NewGuid()}).ToArray()});
        Assert.Equal(before.ProfileId,RoomBuildProfiles.Capture(player,Catalog())!.ProfileId);
    }

    [Fact]
    public void ActiveEffectClassificationUsesAppliedProfileRatherThanEveryPrintedAffix()
    {
        var slots=new[]{"Head","Chest","Hands","Legs","Feet"};
        var armor=slots.Select((slot,i)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new(slot,"Purple","Fire",i<3?"Piercing":"Vitality","DrawInterval",2))).ToArray();
        var profile=RoomBuildProfiles.Capture(Room(3,armor).GetPlayer(Player),Catalog())!;profile.RequireValid();
        Assert.Equal("MonoFire/Piercing",profile.BuildType);Assert.Equal(5,profile.Armor.Count);Assert.Equal(2,profile.Armor.Count(a=>a.EffectAffix=="Vitality"));
    }

    [Fact]
    public void BattleStartAndEventProfilesRemainDistinctAndStableAcrossRestore()
    {
        var room=Room();var player=room.GetPlayer(Player);var deck=player.Combat.Deck.Capture();
        // Explicit metadata boundary fixture; no player casts, gear grant or progression transaction.
        player.Combat.Deck.Restore(deck with{Hand=deck.Hand.Select((card,i)=>i==0?card with{Level=5}:card).ToArray()});
        room.AbandonBattle(Player);var saved=room.Capture();var ended=Assert.Single(saved.Observations!.Events,e=>e.EventName=="battle_finished");
        Assert.NotEqual(ended.BattleBuildProfileId,ended.BuildProfileId);
        var profiles=saved.Observations.Profiles!.ToDictionary(p=>p.ProfileId);
        Assert.Equal("EffectiveBaseCardMaxL0",profiles[ended.BattleBuildProfileId!].GrowthStage);Assert.Equal("EffectiveBaseCardMaxL5",profiles[ended.BuildProfileId!].GrowthStage);
        var restored=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(saved))!,Catalog(),73);
        Assert.Equal(JsonSerializer.Serialize(saved.Observations),JsonSerializer.Serialize(restored.Capture().Observations));
    }

    [Fact]
    public void OldMissingProfileReferencesAreNotFilledFromCurrentPlayerOrAnUnrelatedIndexedProfile()
    {
        var room=Room();room.AbandonBattle(Player);var saved=room.Capture();var journal=saved.Observations!;
        var old=journal with{Profiles=null,BattleBuilds=null,Events=journal.Events.Select(e=>e with{BuildProfileId=null,BattleBuildProfileId=null}).ToArray()};
        var restored=BattleRoom.Restore(saved with{Observations=old},Catalog(),73).Capture();
        Assert.All(restored.Observations!.Events,e=>{Assert.Null(e.BuildProfileId);Assert.Null(e.BattleBuildProfileId);});Assert.Empty(restored.Observations.Profiles!);
    }

    [Fact]
    public void LegacyUniqueElementIsRetainedAndDifferentCombatEquipmentDoesNotShareAFingerprint()
    {
        var id=Guid.NewGuid().ToString("D");var fire=new ExplorationItem(id,ExplorationItemKind.Equipment,
            Equipment:new("Head","Red","Water","Piercing","DrawInterval",UniqueAffix:"Inferno",UniqueElement:"Fire"));
        var water=fire with{Equipment=fire.Equipment! with{UniqueElement="Water"}};
        var firePlayer=Room(0,[fire]).GetPlayer(Player);var waterPlayer=Room(0,[water]).GetPlayer(Player);
        Assert.True(firePlayer.Combat.Equipment.DamageBonus(CardElement.Fire)>waterPlayer.Combat.Equipment.DamageBonus(CardElement.Fire));
        var first=RoomBuildProfiles.Capture(firePlayer,Catalog())!;
        var second=RoomBuildProfiles.Capture(waterPlayer,Catalog())!;
        first.RequireValid();second.RequireValid();Assert.Equal("Fire",Assert.Single(first.Armor).UniqueElement);Assert.NotEqual(first.ProfileId,second.ProfileId);
    }

    [Fact]
    public void TamperedProfileDoesNotKeepItsOriginalFingerprint()
    {
        var profile=RoomBuildProfiles.Capture(Room().GetPlayer(Player),Catalog())!;
        Assert.Throws<DomainValidationException>(()=>(profile with{WeaponLevel=5}).RequireValid());
    }

    [Fact]
    public void OversizedProfileIndexIsRejectedAtItsBound()
    {
        var room=Room();var saved=room.Capture();var profile=Assert.Single(saved.Observations!.Profiles!);
        var oversized=saved.Observations with{Profiles=Enumerable.Repeat(profile,513).ToArray()};
        Assert.Throws<DomainValidationException>(()=>BattleRoom.Restore(saved with{Observations=oversized},Catalog(),73));
    }
}
