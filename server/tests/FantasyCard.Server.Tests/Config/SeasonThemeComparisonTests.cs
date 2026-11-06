using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Opt-in, bounded actual encounter observations, separate from full route/B05 evidence.</summary>
public sealed class SeasonThemeComparisonTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_THEME_COMPARISON")=="1";
    private static readonly string[] Slots=["Head","Hands","Chest","Legs","Feet"];
    private static readonly HeroClass[] Heroes=[HeroClass.Mage,HeroClass.Priest,HeroClass.Guardian];
    private static readonly string[] Themes=["Fire","Wood","Earth","Metal","Water"];
    private static readonly string[] Builds=["starter","mature-mixed"];
    private static readonly int[] Difficulties=[2,5];
    private static readonly TimeSpan Step=TimeSpan.FromMilliseconds(100);
    private static readonly JsonSerializerOptions Indented=new(){WriteIndented=true};

    [Fact(Skip="Requires explicit bounded theme comparison admission.",SkipUnless=nameof(Enabled))]
    public void ActualMatchedMixedClassEncountersRetainUnmodifiedMonstersAndEmitEveryOutcome()
    {
        var folder=Environment.GetEnvironmentVariable("FANTASYCARD_THEME_COMPARISON_DIR")??throw new InvalidOperationException("Owned result directory required.");
        Directory.CreateDirectory(folder);var path=Path.Combine(folder,"encounters.original.jsonl");Assert.False(File.Exists(path));
        var seeds=(Environment.GetEnvironmentVariable("FANTASYCARD_THEME_COMPARISON_SEEDS")??"73").Split(',').Select(int.Parse).ToArray();
        Assert.InRange(seeds.Length,1,3);Assert.Equal(seeds.Length,seeds.Distinct().Count());
        var build=Environment.GetEnvironmentVariable("FANTASYCARD_THEME_COMPARISON_BUILD")??"starter";
        Assert.Contains(build,Builds);
        using var attempts=new StreamWriter(Path.Combine(folder,"attempts.original.jsonl"),append:false);
        using var trace=new StreamWriter(Path.Combine(folder,"actions.original.jsonl"),append:false);
        using var log=new StreamWriter(path,append:false);var rows=new List<Encounter>();
        foreach(var element in Themes)
        {
            var config=SeasonThemeConfigIntegrationTests.Variant(element);
            foreach(var difficulty in Difficulties)
            foreach(var hero in Heroes)
            foreach(var boss in new[]{false,true})
            foreach(var seed in seeds)
            {
                attempts.WriteLine(JsonSerializer.Serialize(new{element,difficulty,hero=hero.ToString(),boss,seed,build,number=rows.Count+1}));attempts.Flush();
                var row=Run(config,difficulty,hero,boss,seed,build,trace);rows.Add(row);log.WriteLine(JsonSerializer.Serialize(row));log.Flush();trace.Flush();
            }
        }
        Assert.Equal(60*seeds.Length,rows.Count);
        File.WriteAllText(Path.Combine(folder,"summary.json"),JsonSerializer.Serialize(new
        {
            actual_encounters=rows.Count,actual_full_routes=0,production_used=false,monsters_weakened=false,
            tick_ms=100,minimum_action_ms=500,permanent_card_weapon_level_assumed=5,effective_card_weapon_level="min(actual,difficulty)",build,armor_level=3,armor="1Orange4Purple",potions_carried=2,potions_used_in_combat=0,
            criteria_accepted=false,note="Observations only. Win rates, medians, three viable archetypes and fifteen-percent bounds require inspection.",
            groups=rows.GroupBy(r=>(r.Difficulty,r.Hero,r.Boss)).Select(g=>new
            {
                g.Key,themes=g.GroupBy(r=>r.Theme).Select(t=>new{theme=t.Key,wins=t.Count(r=>r.Outcome=="Win"),attempts=t.Count(),
                    median_seconds=Median(t.Where(r=>r.Outcome=="Win").Select(r=>r.Seconds)),outcomes=t.Select(r=>r.Outcome).ToArray()})
            })
        },Indented));
    }

    private static Encounter Run(GameConfigCatalog config,int difficulty,HeroClass hero,bool isBoss,int seed,string build,StreamWriter trace)
    {
        var theme=config.SeasonThemes!.Selected;var catalog=CombatCardCatalog.Create(config);var id=Guid.NewGuid();
        var context=new FantasyCard.Domain.Seasons.SeasonContext("theme-comparison",difficulty,"season-v1",config.Version,"season-equipment-v1");
        var deck=Deck(hero,theme,build);
        DeckRules.Validate(hero,deck,config.Cards.Where(c=>c.IsCodex).ToDictionary(c=>c.CardId,c=>new OwnedCard(c.CardId,c.HeroClass,(CardRarity)c.Rarity,1,false)));
        var armor=Slots.Select((slot,index)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new(slot,index==0?"Orange":"Purple",(index<3?theme.PhaseOnePrimary:theme.PhaseTwoPrimary).ToString(),
                hero==HeroClass.Guardian?(index<3?"Bulwark":"Vitality"):hero==HeroClass.Priest?(index<3?"Vitality":"Piercing"):(index<3?"Piercing":"Vitality"),
                "DrawInterval",3,StatsVersion:context.StatsVersion),IsGenerated:false)).ToArray();
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,seed,season:context);
        var player=room.AddPlayer(new(id,hero,deck,null,WeaponLevel:difficulty,WornArmor:armor,CardLevels:Enumerable.Repeat(difficulty,20).ToArray()));
        Assert.True(player.Inventory.TryAdd(new("comparison-potions",ExplorationItemKind.HealthPotion,2)));
        var group=isBoss?"BOSS":theme.Element switch {CardElement.Fire=>"E2",CardElement.Wood=>"E5",CardElement.Earth=>"E4",CardElement.Metal=>"E1",_=>"E3"};
        var map=ChaosMapGenerator.Generate(seed,1,config.SeasonThemes).Capture();
        var selected=isBoss?map.Cells.Single(c=>c.IsBoss):map.Cells.First(c=>c.MonsterGroupId.StartsWith('E')) with {MonsterGroupId=group};
        map=map with {Cells=map.Cells.Select(c=>c.Position==selected.Position?selected:c).ToArray()};
        // Independent encounter fixture: choose its generated location as the
        // initial spawn, placing the original matching elite group there.
        // All monster HP/shield/intents, card rules and clocks
        // stay real. This does not claim a legal movement route.
        room.InitializeMap(ChaosMapState.Restore(map with {SpawnPositions=[selected.Position]}));
        var initial=player.Pve!.Capture();var actions=0;var potions=0;var damage=0L;var last=TimeSpan.FromSeconds(-1);var outcome="Timeout";
        while(room.Elapsed.TotalSeconds<600)
        {
            if(player.Phase==RoomPlayerPhase.Dead){outcome="Dead";break;}
            if(player.Phase==RoomPlayerPhase.Choice){outcome="Win";break;}
            if(player.Phase==RoomPlayerPhase.Pve&&player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(id).RemainingMs==0&&player.Combat.Deck.Hand.Count>0)
            {
                var target=player.Pve!.Monsters.Where(m=>!m.IsDead).OrderBy(m=>m.Hp+m.Shield).First();
                var preferred=Counter(target.ThemeProfile is {} profile?(target.BossPhase==1?profile.PhaseOnePrimary:profile.PhaseTwoPrimary):target.Intents.First(i=>i.Element!=CardElement.None).Element);
                var cards=Choose(player,target,catalog,preferred,build);
                var hpBefore=player.Combat.Hp;
                var resolution=room.PlayCards(id,player.Pve.BattleId,target.MonsterId,cards.Select(c=>c.InstanceId).ToArray(),room.Revision,
                    new DateTimeOffset(2026,11,20,0,0,0,TimeSpan.Zero)+room.Elapsed,room.NewCombatActionId(id));
                Assert.True(room.Elapsed-last>=TimeSpan.FromMilliseconds(500));last=room.Elapsed;actions++;damage+=resolution.HpDamage+resolution.ShieldDamage;
                trace.WriteLine(JsonSerializer.Serialize(new{theme=theme.ThemeId,difficulty,hero=hero.ToString(),boss=isBoss,seed,build,seconds=room.Elapsed.TotalSeconds,
                    selected=cards.Select(c=>new{c.CardId,c.Level}),hpBefore,hpAfter=player.Combat.Hp,shield=player.Combat.Shield,targetHp=target.Hp,targetShield=target.Shield,
                    resolution.HpDamage,resolution.ShieldDamage,resolution.Heal,resolution.ShieldGain,resolution.DrawCharge,resolution.ImmediateDraw}));
            }
            room.Advance(Step,new DateTimeOffset(2026,11,20,0,0,0,TimeSpan.Zero)+room.Elapsed+Step);
        }
        var final=player.Pve?.Capture();
        return new(theme.ThemeId,difficulty,hero.ToString(),isBoss,seed,outcome,room.Elapsed.TotalSeconds,actions,potions,damage,
            initial.Monsters.Sum(m=>m.MaximumHp),initial.Monsters.Sum(m=>m.Shield),final?.Monsters.Sum(m=>m.ThemeRecoveredHp)??0,
            final?.Monsters.Sum(m=>m.ThemeShieldGenerated)??0,player.Combat.Hp,deck,armor.Select(a=>a.Equipment!).ToArray(),build);
    }

    private static CombatCardInstance[] Choose(RoomPlayerState player,MonsterCombatState target,CombatCardCatalog catalog,CardElement preferred,string build)
    {
        var hand=player.Combat.Deck.Hand;CombatCardInstance[] best=[hand[0]];var score=double.NegativeInfinity;
        for(var mask=1;mask<(1<<hand.Count);mask++)
        {
            var cards=hand.Where((_,index)=>(mask&(1<<index))!=0).OrderByDescending(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride).Effect.Element==preferred).ThenBy(c=>c.CardId,StringComparer.Ordinal).ToArray();
            var definitions=cards.Select(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride)).ToArray();
            var result=CombatResolver.Resolve(definitions,player.Combat,target.ElementalResistance);
            var healing=Math.Min(result.Heal,Math.Max(0,player.Combat.EffectiveMaximumHp-player.Combat.Hp));
            var shielding=Math.Min(result.Shield,Math.Max(0,player.Combat.MaximumHp/2-player.Combat.Shield));
            var value=Math.Min(result.Damage,target.Hp+target.Shield)+healing*3+shielding*1.5+definitions.Sum(c=>c.Effect.ImmediateDraw+c.Effect.DrawCharge)*4-cards.Length;
            if(build=="mature-mixed")
            {
                if(target.WindupRemaining>TimeSpan.Zero&&target.StunRemaining<=TimeSpan.Zero)value+=Math.Min(1.2,result.Stun.TotalSeconds)*15;
                value-=result.HealthCost*(player.Combat.Hp<player.Combat.MaximumHp*.75?3:.5);
                if(result.HealthCost>=player.Combat.Hp)value-=1000;
            }
            if(value>score){score=value;best=cards;}
        }
        return best;
    }
    private static string[] Deck(HeroClass hero,SeasonThemeDefinition theme,string build)
    {
        var prefix=hero==HeroClass.Mage?"MAG":hero==HeroClass.Priest?"PRI":"GUA";
        if(build=="starter")return Enumerable.Range(1,13).Select(n=>$"C{n:D2}").Concat(Enumerable.Range(1,7).Select(n=>$"{prefix}-{n:D2}")).ToArray();
        string[] support=["GP18","GP19","GP20","GP21","GP22","GP23","GO05","ET-WATER-P","ET-WOOD-P"];
        var requested=support.Concat(Enumerable.Range(8,3).Select(n=>$"{prefix}-{n:D2}"))
            .Concat(new[]{"GP15","GP16","GP13","GP05","GP10","GP07","GP02","ET-"+Counter(theme.PhaseOnePrimary).ToString().ToUpperInvariant()+"-P","ET-EARTH-P","ET-METAL-P","ET-FIRE-P"});
        return requested.Distinct(StringComparer.Ordinal).Take(20).ToArray();
    }
    private static CardElement Counter(CardElement target)=>target switch {CardElement.Fire=>CardElement.Water,CardElement.Wood=>CardElement.Metal,CardElement.Earth=>CardElement.Wood,CardElement.Metal=>CardElement.Fire,_=>CardElement.Earth};
    private static double? Median(IEnumerable<double> values)
    {
        var a=values.Order().ToArray();return a.Length==0?null:a.Length%2==1?a[a.Length/2]:(a[a.Length/2-1]+a[a.Length/2])/2;
    }
    private sealed record Encounter(string Theme,int Difficulty,string Hero,bool Boss,int Seed,string Outcome,double Seconds,int Actions,int Potions,long Damage,
        int InitialMonsterHp,int InitialMonsterShield,int RegeneratedHp,long GeneratedShield,int EndingHp,IReadOnlyList<string> Deck,IReadOnlyList<EquipmentRewardData> Armor,string Build);
}
