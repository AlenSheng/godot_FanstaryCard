using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonCraftingTests
{
    [Theory]
    [InlineData("Purple",4,0,4,0)]
    [InlineData("Purple",1,3,1,3)]
    [InlineData("Purple",0,4,0,4)]
    [InlineData("Orange",100,14,0,14)]
    public void PublishedBlueprintPaymentsPreferLowTierAndAllowOnlyOneWaySubstitution(string quality,long blue,long orange,long spentBlue,long spentOrange)
    {
        var policy=GameConfigCatalog.Current.SeasonCrafting!;
        Assert.Equal(new BlueprintPayment(spentBlue,spentOrange),policy.Payment(quality,blue,orange));
        Assert.Throws<DomainValidationException>(()=>policy.Payment("Orange",100,13));
        Assert.Throws<DomainValidationException>(()=>policy.Payment("Red",100,100));
        Assert.Equal(1,policy.Offer("Purple").ReforgeFragmentCost);Assert.Equal(2,policy.Offer("Orange").ReforgeFragmentCost);
    }

    [Fact]
    public void EveryEffectAndQualityHasAtMostThreeAttemptsAndAHitResetsOnlyItsOwnCounter()
    {
        var policy=GameConfigCatalog.Current.SeasonCrafting!;
        foreach(var quality in new[]{"Purple","Orange"})
        foreach(var effect in SeasonCraftingConfig.Effects)
        foreach(var roll in Enumerable.Range(0,3))
        {
            var forced=policy.Wish(quality,effect,2,roll);Assert.True(forced.Guaranteed);Assert.Equal(effect,forced.EffectAffix);Assert.Equal(0,forced.FailuresAfter);
            var first=policy.Wish(quality,effect,0,roll);Assert.False(first.Guaranteed);
            Assert.Equal(first.EffectAffix==effect?0:1,first.FailuresAfter);
        }
        Assert.Throws<DomainValidationException>(()=>policy.Wish("Purple","unknown",0,0));
        Assert.Throws<DomainValidationException>(()=>policy.Wish("Purple","Vitality",3,0));
    }

    [Theory]
    [InlineData(0,0,0)]
    [InlineData(1,4,0)]
    [InlineData(2,0,4)]
    [InlineData(5,0,4)]
    public void OwnDistinctEliteAndBossCellsRespectTheOriginalDifficultyAndPerMatchCap(int difficulty,long blue,long orange)
    {
        var policy=GameConfigCatalog.Current.SeasonCrafting!;
        ChaosMapCell[] cells=[new(new(0,0),ChaosMapLayer.Core,false,false,false,"E1"),
            new(new(0,1),ChaosMapLayer.Core,true,false,false,"BOSS"),new(new(0,2),ChaosMapLayer.Core,false,false,false,"E2"),
            new(new(0,3),ChaosMapLayer.Outer,false,false,false,"O1")];
        Assert.Equal(new PendingBlueprints(blue,orange),policy.Pending(difficulty,false,cells.Concat(cells)));
        Assert.Equal(new PendingBlueprints(),policy.Pending(difficulty,true,cells));
        Assert.Equal(new PendingBlueprints(),policy.Pending(difficulty,false,[]));
    }

    [Fact]
    public void AnActualFinishingPlayRecordsTheOwnClearBeforeRewardChoiceAndRestoreOrRefreshCannotDuplicateIt()
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:new SeasonContext("clear",1,"season-v1",config.Version,"season-equipment-v1"));
        var cards=Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"MAG-{i:D2}")).ToArray();
        var player=room.AddPlayer(new(Guid.NewGuid(),HeroClass.Mage,cards,null));
        var map=ChaosMapGenerator.Generate(73,1).Capture();var elite=map.Cells.First(cell=>cell.MonsterGroupId.StartsWith('E'));
        room.InitializeMap(ChaosMapState.Restore(map with {SpawnPositions=[elite.Position]}));
        // A declared finishing boundary preserves real monsters/cards/intents; it is not a full encounter or balance claim.
        foreach(var monster in player.Pve!.Monsters)monster.TakeDamage(monster.Hp+monster.Shield-1);
        var now=DateTimeOffset.UnixEpoch;
        foreach(var monster in player.Pve.Monsters)
        {
            CombatCardInstance? card=null;
            for(var tick=0;tick<100 && card is null;tick++)
            {
                card=player.Combat.Deck.Hand.FirstOrDefault(value=>CombatResolver.Resolve([catalog.Get(value.CardId,value.Level,value.ElementOverride)],player.Combat,monster.ElementalResistance).Damage>0);
                if(card is null){now=now.AddMilliseconds(100);room.Advance(TimeSpan.FromMilliseconds(100),now);}
            }
            Assert.NotNull(card);now=now.AddSeconds(1);
            var actionId=$"{room.Capture().Players.Single().LastCombatActionSequence+1}:{Guid.NewGuid():N}";
            Assert.True(room.PlayCards(player.PlayerId,player.Pve.BattleId,monster.MonsterId,[card.InstanceId],room.Revision,now,actionId).TargetDefeated);
        }
        Assert.Equal(RoomPlayerPhase.Choice,player.Phase);
        Assert.Contains(elite.Position,Assert.Single(room.Capture().Players).ClearedCells!);
        var restored=BattleRoom.Restore(room.Capture(),catalog,73);var before=restored.Capture();
        restored.RefreshRewardChoice(player.PlayerId,restored.Revision,10000,"refresh-control");
        Assert.Equal(before.Players[0].ClearedCells,restored.Capture().Players[0].ClearedCells);
        var saved=restored.Capture();var cleared=saved.Map!.Cells.Where(cell=>saved.Players[0].ClearedCells!.Contains(cell.Position));
        Assert.Equal(new PendingBlueprints(1,0),config.SeasonCrafting!.Pending(1,false,cleared));
    }
}
