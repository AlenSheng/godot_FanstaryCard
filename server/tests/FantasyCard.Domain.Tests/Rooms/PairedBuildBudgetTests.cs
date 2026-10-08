using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class PairedBuildBudgetTests
{
    [Fact]
    public void Single_published_white_card_swap_preserves_cost_rarity_level_and_twenty_instances()
    {
        var source=GameConfigCatalog.Current;
        var before=Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"MAG-{i:D2}")).ToArray();
        var after=before.Select(id=>id=="C01"?"C17":id).ToArray();
        PairedDeckBudget.Validate(source,HeroClass.Mage,before,after);
        var old=source.Cards.Single(c=>c.CardId=="C01");var replacement=source.Cards.Single(c=>c.CardId=="C17");
        Assert.Equal(old.Rarity,replacement.Rarity);Assert.Equal(old.UnlockCost,replacement.UnlockCost);
        Assert.Equal(20,before.Length);Assert.Equal(20,after.Length);Assert.Equal(20,after.Distinct().Count());
        Assert.Single(before.Except(after));Assert.Single(after.Except(before));
        var a=new PlayerCombatState(HeroClass.Mage,before,new Random(61));
        var b=new PlayerCombatState(HeroClass.Mage,after,new Random(61));
        Assert.Equal(a.Hp,b.Hp);Assert.Equal(a.MaximumHp,b.MaximumHp);Assert.Equal(a.Shield,b.Shield);
        Assert.Equal(a.Deck.Hand.Count,b.Deck.Hand.Count);Assert.Equal(a.Deck.Library.Count,b.Deck.Library.Count);
        Assert.Equal(a.Deck.DrawCharge,b.Deck.DrawCharge);
        Assert.All(a.Deck.Hand.Concat(a.Deck.Library).Concat(b.Deck.Hand).Concat(b.Deck.Library),c=>Assert.Equal(0,c.Level));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void PVP_side_swap_keeps_mirrored_starting_resources_and_restores_each_own_pool(bool reverse)
    {
        var room=new BattleRoom(Guid.NewGuid(),"paired-side",CombatCardCatalog.CreatePrototype(),79);
        var first=Guid.NewGuid();var second=Guid.NewGuid();var cards=Enumerable.Range(1,20).Select(i=>$"C{i:D2}").ToArray();
        room.AddPlayer(new(first,HeroClass.Mage,cards,null,WeaponLevel:2));room.AddPlayer(new(second,HeroClass.Mage,cards,null,WeaponLevel:2));
        var beforeA=room.GetPlayer(first).Combat.Capture();var beforeB=room.GetPlayer(second).Combat.Capture();
        var duel=room.StartDuel(reverse?second:first,reverse?first:second,DateTimeOffset.UnixEpoch);
        var a=room.GetPlayer(first).Combat;var b=room.GetPlayer(second).Combat;
        Assert.Equal(a.Hp,b.Hp);Assert.Equal(a.MaximumHp,b.MaximumHp);Assert.Equal(a.Shield,b.Shield);Assert.Equal(a.WeaponLevel,b.WeaponLevel);
        Assert.Equal(a.Deck.Hand.Count,b.Deck.Hand.Count);Assert.Equal(a.Deck.Library.Count,b.Deck.Library.Count);Assert.Equal(a.Deck.DrawCharge,b.Deck.DrawCharge);
        Assert.Equal(a.Deck.Hand.Concat(a.Deck.Library).Select(c=>c.CardId).Order(),b.Deck.Hand.Concat(b.Deck.Library).Select(c=>c.CardId).Order());
        room.EndDuelSurvived(duel.DuelId,DuelEndReason.MutualLeave);
        Assert.Equivalent(beforeA,room.GetPlayer(first).Combat.Capture(),strict:true);Assert.Equivalent(beforeB,room.GetPlayer(second).Combat.Capture(),strict:true);
    }

    [Fact]
    public void Higher_rarity_or_level_replacement_is_rejected_before_experiment_entry()
    {
        var config=GameConfigCatalog.Current;
        var before=Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"MAG-{i:D2}")).ToArray();
        Assert.Throws<DomainValidationException>(()=>PairedDeckBudget.Validate(config,HeroClass.Mage,before,before.Select(id=>id=="C01"?"GP21":id).ToArray()));
        var after=before.Select(id=>id=="C01"?"C17":id).ToArray();var levels=new int[20];levels[0]=1;
        Assert.Throws<DomainValidationException>(()=>PairedDeckBudget.Validate(config,HeroClass.Mage,before,after,candidateLevels:levels));
    }
}
