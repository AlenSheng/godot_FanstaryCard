using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class SeasonEquipmentTests
{
    private const string Stats="season-equipment-v1";
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];
    private static readonly CardElement[] OtherElements=[CardElement.Wood,CardElement.Earth,CardElement.Metal,CardElement.Water];
    private static readonly string[] DiagnosticCards=["C01","C02","GP01"];

    [Theory]
    [InlineData(0,0,0,31)] [InlineData(1,0,1,52)] [InlineData(2,1,2,66)]
    [InlineData(3,2,3,88)] [InlineData(4,3,4,107)] [InlineData(5,5,5,129)]
    public void PublishedCardsAndRealResolverMatchAllSixIndependentDamageAnchors(int sample,int armorLevel,int cardLevel,int damage)
    {
        var profile=EquipmentCombatRules.Calculate(sample==0?[]:Loadout(sample,armorLevel),GameConfigCatalog.Current,Stats);
        var catalog=CombatCardCatalog.Create(GameConfigCatalog.Current);
        var resolved=CombatResolver.Resolve(DiagnosticCards.Select(id=>catalog.Get(id,cardLevel)).ToArray(),DiagnosticState(profile,cardLevel));
        Assert.Equal(damage,resolved.Damage);
    }

    [Theory]
    [InlineData("Orange",null,144)] [InlineData("Red",null,156)] [InlineData("Red","Inferno",164)]
    public void RealResolverKeepsTheDeclaredOrangeRedAndInfernoFullPiercingBudgets(string quality,string? unique,int damage)
    {
        var armor=Loadout(5,5).Select(item=>item with {EffectAffix="Piercing"}).ToArray();
        armor[0]=armor[0] with {Quality=quality,UniqueAffix=unique};
        var profile=EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,Stats);var catalog=CombatCardCatalog.Create(GameConfigCatalog.Current);
        var resolved=CombatResolver.Resolve(DiagnosticCards.Select(id=>catalog.Get(id,5)).ToArray(),DiagnosticState(profile,5));
        Assert.Equal(damage,resolved.Damage);
    }

    [Theory]
    [InlineData(0,0,0,0,4)]
    [InlineData(1,0,.43,.24,3.24)]
    [InlineData(2,1,.65,.325,2.93)]
    [InlineData(3,2,1.00,.51,2.44)]
    [InlineData(4,3,1.21,.586,2.228)]
    [InlineData(5,5,1.47,.65,2.06)]
    public void SixIndependentProposalLoadoutsKeepRawAndEffectiveElementValuesAndNaturalTiming(int sample,int level,double damage,double resistance,double interval)
    {
        var items=sample==0?[]:Loadout(sample,level);
        var profile=EquipmentCombatRules.Calculate(items,GameConfigCatalog.Current,Stats);
        Assert.Equal(damage,profile.DamageBonus(CardElement.Fire),8);
        Assert.Equal(resistance,profile.RawElements!.FireResistance,8);
        Assert.Equal(Math.Min(.6,resistance),profile.Resistance(CardElement.Fire),8);
        foreach(var element in OtherElements)Assert.Equal(0,profile.Resistance(element));
        var state=State(profile);Assert.Equal(interval,state.NaturalDrawIntervalSeconds,8);
        Assert.Equal(Stats,profile.StatsVersion);
    }

    [Fact]
    public void VersionedPurpleZeroRetainsGrowthSpaceAndEscapeShoesDoNotContributeInterval()
    {
        var armor=Loadout(3,0);var legacy=EquipmentCombatRules.Calculate(armor);var current=EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,Stats);
        Assert.Equal(1.8,State(legacy).NaturalDrawIntervalSeconds,8);Assert.Equal(2.6,State(current).NaturalDrawIntervalSeconds,8);
        var shoes=armor.Select(item=>item.Slot=="Feet"?item with {SecondaryTrait="ForcedEscape"}:item).ToArray();
        Assert.Equal(2.88,State(EquipmentCombatRules.Calculate(shoes,GameConfigCatalog.Current,Stats)).NaturalDrawIntervalSeconds,8);
        Assert.Throws<DomainValidationException>(()=>EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,"not-published"));
    }

    [Fact]
    public void RedUniquePolicyUsesNewMainElementBudgetAndKeepsTheOnePointEightFloor()
    {
        var armor=Loadout(5,5);armor[0]=armor[0] with {Quality="Red"};
        var normal=EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,Stats);
        Assert.Equal(1.62,normal.DamageBonus(CardElement.Fire),8);Assert.Equal(.71,normal.RawElements!.FireResistance,8);
        Assert.Equal(.6,normal.Resistance(CardElement.Fire),8);Assert.Equal(1.96,State(normal).NaturalDrawIntervalSeconds,8);
        armor[0]=armor[0] with {UniqueAffix="Inferno",UniqueElement=CardElement.Fire};
        Assert.Equal(1.77,EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,Stats).DamageBonus(CardElement.Fire),8);
        armor[0]=armor[0] with {UniqueElement=CardElement.Water};
        Assert.Throws<DomainValidationException>(()=>EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,Stats));
        armor[0]=armor[0] with {UniqueAffix="RapidDraw",UniqueElement=null};
        var rapid=State(EquipmentCombatRules.Calculate(armor,GameConfigCatalog.Current,Stats));Assert.Equal(1.8,rapid.NaturalDrawIntervalSeconds,8);
        rapid.ApplyDrawSpeed(TimeSpan.FromSeconds(2),-.5);Assert.Equal(1.8,rapid.DrawIntervalSeconds,8);
        rapid.ApplyDrawBlockSpeed(TimeSpan.FromSeconds(2));Assert.Equal(.9,rapid.DrawIntervalSeconds,8);Assert.Equal(1.8,rapid.NaturalDrawIntervalSeconds,8);
    }

    [Fact]
    public void ScavengeOpeningIsIdempotentAcrossRestoreAndPvpResume()
    {
        var profile=Unique("Scavenge");var state=State(profile);var pve=Guid.NewGuid();
        Assert.True(state.BeginBattle(pve));Assert.Equal(4,state.Deck.Hand.Count);var frozen=state.Capture();
        Assert.False(state.BeginBattle(pve));Assert.Equivalent(frozen,state.Capture(),strict:true);
        var restored=State(profile);restored.Restore(frozen);Assert.False(restored.BeginBattle(pve));Assert.Equal(4,restored.Deck.Hand.Count);
        var duel=Guid.NewGuid();restored.PrepareForDuel(new Random(81),duel);Assert.Equal(4,restored.Deck.Hand.Count);
        var opening=restored.Capture();restored.PrepareForDuel(new Random(99),duel);Assert.Equivalent(opening,restored.Capture(),strict:true);
        restored.Restore(frozen);Assert.False(restored.BeginBattle(pve));Assert.Equivalent(frozen,restored.Capture(),strict:true);
    }

    [Fact]
    public void ChainDrawOnlyAddsOneToSuccessfulNaturalDrawsAndNeverRecursesOrAffectsImmediateDraws()
    {
        var configured=Unique("ChainDraw");Assert.Equal(1000,configured.ChainDrawBasisPoints);
        var state=State(configured with {ChainDrawBasisPoints=10000});var deck=state.Deck.Capture();
        state.Deck.Restore(new([],deck.Hand.Concat(deck.Library).ToArray(),[],0));
        state.Advance(TimeSpan.FromSeconds(state.NaturalDrawIntervalSeconds),true);Assert.Equal(2,state.Deck.Hand.Count);
        var restored=State(state.Equipment);restored.Restore(state.Capture());
        restored.DrawImmediate(1);Assert.Equal(3,restored.Deck.Hand.Count);
        restored.Deck.AddCharge(1,new Random(9));Assert.Equal(4,restored.Deck.Hand.Count);
        restored.Advance(TimeSpan.FromSeconds(restored.NaturalDrawIntervalSeconds),true);Assert.Equal(5,restored.Deck.Hand.Count);
        var full=restored.Capture();restored.Advance(TimeSpan.FromSeconds(restored.NaturalDrawIntervalSeconds),true);Assert.Equal(5,restored.Deck.Hand.Count);
        Assert.Equal(full.RandomState,restored.Capture().RandomState);
    }

    [Fact]
    public void GoldenCicadaRequiresRedShoesAndUsesTheExistingTotalEscapeCap()
    {
        var profile=Unique("GoldenCicada","Feet");Assert.Equal(.15,profile.GoldenCicadaBonus,8);
        Assert.Equal(.7,DuelRules.EscapeProbability(HeroClass.Priest,1,80,70,70,0,profile.GoldenCicadaBonus),8);
        Assert.Throws<DomainValidationException>(()=>Unique("GoldenCicada","Head"));
    }

    private static CombatEquipmentProfile Unique(string unique,string slot="Head")=>EquipmentCombatRules.Calculate(
        [new(Guid.NewGuid(),slot,"Red",0,CardElement.Fire,null,"DrawInterval",unique)],GameConfigCatalog.Current,Stats);
    private static PlayerCombatState State(CombatEquipmentProfile profile)=>new(HeroClass.Mage,SeasonFenxianTests.Starter(HeroClass.Mage),new Random(73),equipment:profile);
    private static PlayerCombatState DiagnosticState(CombatEquipmentProfile profile,int level)
    {
        var ids=SeasonFenxianTests.Starter(HeroClass.Mage).Where(id=>id!="C03").Append("GP01").ToArray();
        SeasonFenxianTests.ValidateDeck(HeroClass.Mage,ids);
        return new(HeroClass.Mage,ids,new Random(73),equipment:profile,cardLevels:Enumerable.Repeat(level,20).ToArray(),
            fenxianImmediateDrawPolicy:FenxianImmediateDrawPolicy.SeasonBoundedRhythm);
    }
    private static CombatEquipmentItem[] Loadout(int sample,int level)=>Slots.Select((slot,index)=>new CombatEquipmentItem(Guid.NewGuid(),slot,
        sample switch {1=>index<3?"Green":"Blue",2=>"Blue",3=>"Purple",_=>index==0?"Orange":"Purple"},level,CardElement.Fire,null,"DrawInterval")).ToArray();
}
