using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonThemeGroup(string GroupId,string Tier,string MemberElements,bool SpawnAllowed,int BaseWeight)
{
    public IReadOnlyList<CardElement> Elements=>MemberElements.Split('|').Select(value=>Enum.Parse<CardElement>(value)).ToArray();
}

/// <summary>Original encounter strategy. It adds no damage multiplier or permanent progression.</summary>
public sealed record SeasonThemeDefinition(string ThemeId,CardElement Element,string NameKey,string StrategyId,
    CardElement PhaseOnePrimary,CardElement PhaseOneSecondary,CardElement PhaseTwoPrimary,CardElement PhaseTwoSecondary,
    int RegenerationBudgetBasisPoints,int RegenerationStepBasisPoints,int PhaseOneShield,int PhaseTwoShield,
    string SetupKind,int SetupValue)
{
    public void Validate()
    {
        if(ThemeId!=Element.ToString()||!SeasonThemeConfig.Elements.Contains(Element)||NameKey!="season_theme_"+ThemeId.ToLowerInvariant()||
            !SeasonThemeConfig.Elements.Contains(PhaseOnePrimary)||!SeasonThemeConfig.Elements.Contains(PhaseOneSecondary)||
            !SeasonThemeConfig.Elements.Contains(PhaseTwoPrimary)||!SeasonThemeConfig.Elements.Contains(PhaseTwoSecondary)||
            PhaseOnePrimary==PhaseOneSecondary||PhaseTwoPrimary==PhaseTwoSecondary||
            (PhaseOnePrimary==PhaseTwoPrimary&&PhaseOneSecondary==PhaseTwoSecondary)||
            PhaseOnePrimary!=Element||PhaseOneShield is <0 or >12||PhaseTwoShield is <0 or >10||
            RegenerationBudgetBasisPoints is <0 or >500||RegenerationStepBasisPoints is <0 or >200||
            (Element==CardElement.Wood ? RegenerationBudgetBasisPoints<=0||RegenerationStepBasisPoints<=0||RegenerationStepBasisPoints>RegenerationBudgetBasisPoints
                :RegenerationBudgetBasisPoints!=0||RegenerationStepBasisPoints!=0)||
            (Element==CardElement.Wood?PhaseOneShield!=0||PhaseTwoShield!=0:PhaseOneShield<=0||PhaseTwoShield<=0)||
            (Element==CardElement.Metal?(SetupKind!="Empower"||SetupValue!=2):(SetupKind!="Charge"||SetupValue!=0)))
            throw new InvalidDataException("The theme strategy exceeds its bounded combat contract.");
        var expected=Element switch
        {
            CardElement.Fire=>"ember-windows",CardElement.Wood=>"thorn-regrowth",CardElement.Earth=>"stone-cycle",
            CardElement.Metal=>"metal-telegraph",CardElement.Water=>"tide-shift",_=>throw new InvalidDataException("Unknown theme element.")
        };
        if(StrategyId!=expected)throw new InvalidDataException("The theme needs its named strategy.");
    }

    public IReadOnlyList<MonsterIntentState> Intents(int phase)
    {
        if(phase is not (1 or 2))throw new InvalidDataException("A themed boss has exactly two phases.");
        var primary=phase==1?PhaseOnePrimary:PhaseTwoPrimary;var secondary=phase==1?PhaseOneSecondary:PhaseTwoSecondary;
        var utility=RegenerationBudgetBasisPoints>0?new MonsterIntentState(MonsterIntentKind.Regenerate,RegenerationStepBasisPoints,CardElement.None):
            new(MonsterIntentKind.Shield,phase==1?PhaseOneShield:PhaseTwoShield,CardElement.None);
        return phase==1?
            [new(MonsterIntentKind.Attack,4,primary),new(MonsterIntentKind.Attack,4,secondary),utility,
                new(MonsterIntentKind.Attack,5,primary),new(Enum.Parse<MonsterIntentKind>(SetupKind),SetupValue,CardElement.None),new(MonsterIntentKind.Direct,6,CardElement.None)]:
            [new(MonsterIntentKind.Attack,5,primary),new(MonsterIntentKind.Attack,5,secondary),utility,
                new(MonsterIntentKind.Attack,5,primary),new(MonsterIntentKind.Attack,5,secondary),new(MonsterIntentKind.Direct,8,CardElement.None)];
    }
}

public sealed record SeasonThemeConfig(string RuleId,string SelectedThemeId,int PreferredWeight,int OtherWeight,string GroupWeightMode,
    int GlobalDamageBasisPoints,string Layout,bool SpawnSingles,IReadOnlyList<SeasonThemeDefinition> Themes,IReadOnlyList<SeasonThemeGroup> Groups)
{
    public const string Version="season-theme-v1";
    public static IReadOnlyList<CardElement> Elements {get;}=Array.AsReadOnly(new[]{CardElement.Wood,CardElement.Fire,CardElement.Earth,CardElement.Metal,CardElement.Water});
    public SeasonThemeDefinition Selected=>Themes.Single(t=>t.ThemeId==SelectedThemeId);

    public void Validate(string defaultLootElement)
    {
        if(RuleId!=Version||PreferredWeight!=4000||OtherWeight!=1500||GroupWeightMode!="member-mean-normalized"||
            GlobalDamageBasisPoints!=10000||Layout!="chaos-6x6"||!SpawnSingles||Themes.Count!=5||
            Themes.Select(t=>t.Element).Distinct().Count()!=5||Themes.Count(t=>t.ThemeId==SelectedThemeId)!=1||
            defaultLootElement!=SelectedThemeId)
            throw new InvalidDataException("Theme selection, layout or non-amplifying weights differ from the published contract.");
        foreach(var theme in Themes)theme.Validate();
        var expected=Enumerable.Range(1,8).Select(n=>$"O{n}").Concat(Enumerable.Range(1,5).Select(n=>$"M{n}"))
            .Concat(Enumerable.Range(1,6).Select(n=>$"E{n}")).Order(StringComparer.Ordinal);
        if(!Groups.Select(g=>g.GroupId).Order(StringComparer.Ordinal).SequenceEqual(expected))
            throw new InvalidDataException("Theme groups must reference exactly the original nineteen enemy groups.");
        foreach(var group in Groups)
        {
            var elements=group.MemberElements.Split('|');
            if(group.Tier!=(group.GroupId[0]=='O'?"outer":group.GroupId[0]=='M'?"middle":"elite")||
                group.BaseWeight is <1 or >1000||elements.Length is <1 or >2||elements.Any(e=>!Enum.TryParse<CardElement>(e,out var value)||!Elements.Contains(value))||
                group.SpawnAllowed!=(group.GroupId[0]=='O'&&int.Parse(group.GroupId[1..],System.Globalization.CultureInfo.InvariantCulture)<=5))
                throw new InvalidDataException("Theme group composition, tier or safe spawn rules are invalid.");
            var layer=group.Tier=="outer"?ChaosMapLayer.Outer:group.Tier=="middle"?ChaosMapLayer.Middle:ChaosMapLayer.Core;
            var actual=PveBattleFactory.Create(new(new(0,0),layer,false,false,false,group.GroupId)).Monsters
                .Select(monster=>monster.Intents.First(intent=>intent.Element!=CardElement.None).Element);
            if(!group.Elements.SequenceEqual(actual))throw new InvalidDataException("Theme group differs from the referenced original monsters.");
        }
    }

    public int Weight(SeasonThemeGroup group)
    {
        var elements=group.Elements;
        return checked(group.BaseWeight*elements.Sum(e=>e==Selected.Element?PreferredWeight:OtherWeight)/elements.Count);
    }

    public string Roll(string tier,bool spawn,int roll)
    {
        var pool=Groups.Where(g=>g.Tier==tier&&(!spawn||g.SpawnAllowed)).ToArray();
        var total=pool.Sum(Weight);
        if(pool.Length==0||roll<0||roll>=total)throw new DomainValidationException("Theme group roll is outside its normalized pool.");
        foreach(var group in pool)
        {
            var weight=Weight(group);if(roll<weight)return group.GroupId;roll-=weight;
        }
        throw new InvalidDataException("Theme group weights failed to cover their domain.");
    }

    public string Roll(string tier,bool spawn,Random random)
    {
        var total=Groups.Where(g=>g.Tier==tier&&(!spawn||g.SpawnAllowed)).Sum(Weight);
        return Roll(tier,spawn,random.Next(total));
    }
}
