using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Bounded observations using legal builds, visible state and the real read-only card preview.</summary>
public sealed class SeasonThemeCalibrationTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_C16_CALIBRATION")=="1";
    private static readonly string[] Themes=["Wood","Fire","Earth","Metal","Water"];
    private static readonly string[] Builds=["direct-engine","counter-combo","fortress-control"];
    private static readonly HeroClass[] Heroes=[HeroClass.Mage,HeroClass.Priest,HeroClass.Guardian];
    private static readonly string[] Slots=["Head","Hands","Chest","Legs","Feet"];
    private static readonly string[] DirectCore=["GP15","GP16","GP17","GB19","GB20","GB23","GP20","GP21","GP22","ET-WATER-P","ET-WOOD-P","GO03","GP18","GP23"];
    private static readonly string[] FortressCore=["GP20","GP21","GP22","GO05","GP18","GP19","GP23","ET-METAL-P","ET-EARTH-P"];
    private static readonly string[] CounterCore=["GP20","GP21","GP22","GP18","GO08"];
    private static readonly string[] Fallback=["GP13","GP19","GP10","GP02","GP07","GP05","GP15","GP16","GP17","ET-WATER-P","ET-WOOD-P","GP23","GB19","GB20","GB23"];
    private static readonly int[] BoundaryDifficulties=[2,5];
    private static readonly bool[] EncounterKinds=[false,true];
    private static readonly string[] CounterProbeThemes=["Fire","Wood"];
    private static readonly string[] RemainingProbeThemes=["Earth","Metal","Water"];
    private static readonly TimeSpan Step=TimeSpan.FromMilliseconds(100);
    private static readonly DateTimeOffset Epoch=new(2026,11,20,0,0,0,TimeSpan.Zero);

    [Fact]
    public void PreflightBuildsAreDistinctLegalAndRespectAllSixArmorEntryCapsWithoutRunningEncounters()
    {
        foreach(var themeId in Themes)
        {
            var config=Configuration(themeId);var theme=config.SeasonThemes!.Selected;
            foreach(var hero in Heroes)
            {
                var sets=new List<HashSet<string>>();
                foreach(var build in Builds)
                {
                    var deck=Deck(config,hero,theme,build);Validate(config,hero,deck);sets.Add(deck.ToHashSet(StringComparer.Ordinal));
                    for(var difficulty=0;difficulty<6;difficulty++)
                    {
                        var armor=Armor(theme,build,difficulty);Assert.Equal(5,armor.Length);
                        Assert.All(armor,item=>Assert.True(EquipmentRewardRules.IsValid(item.Equipment!)));
                        Assert.All(armor,item=>Assert.Equal(3,item.Equipment!.Level));
                        Assert.Equal(difficulty<2?0:1,armor.Count(item=>item.Equipment!.Quality=="Orange"));
                        if(difficulty==0)Assert.All(armor,item=>Assert.Equal("Blue",item.Equipment!.Quality));
                        if(difficulty==1)Assert.All(armor,item=>Assert.Equal("Purple",item.Equipment!.Quality));
                    }
                }
                for(var i=0;i<sets.Count;i++)for(var j=i+1;j<sets.Count;j++)
                    Assert.True(sets[i].Except(sets[j]).Count()+sets[j].Except(sets[i]).Count()>=4);
                var offense=Deck(config,hero,theme,"counter-offense");Validate(config,hero,offense);
                Assert.Equal(Deck(config,hero,theme,"counter-combo"),offense); // Same archetype, different elemental armor allocation.
                for(var difficulty=0;difficulty<6;difficulty++)
                {
                    var armor=Armor(theme,"counter-offense",difficulty);Assert.All(armor,item=>Assert.True(EquipmentRewardRules.IsValid(item.Equipment!)));
                    for(var i=0;i<armor.Length;i++)Assert.Equal(Counter(i<3?theme.PhaseOnePrimary:theme.PhaseTwoPrimary).ToString(),armor[i].Equipment!.Element);
                }
            }
        }
    }

    [Fact(Skip="Requires the explicit eighteen-encounter C16 admission; never rerun a used budget.",SkipUnless=nameof(Enabled))]
    public void SameFormalThemeSixDifficultiesThreeClassesRecordAllActualResources()
    {
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_C16_CALIBRATION_DIR")??throw new InvalidOperationException("Owned evidence directory required.");
        Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        var config=GameConfigCatalog.Current;var theme=config.SeasonThemes!.SelectedThemeId;Assert.Contains(theme,Themes);
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"));
        using var actions=new StreamWriter(Path.Combine(directory,"actions.original.jsonl"));
        using var resources=new StreamWriter(Path.Combine(directory,"monster-resources.original.jsonl"));
        using var results=new StreamWriter(Path.Combine(directory,"encounters.original.jsonl"));
        var number=0;
        for(var difficulty=0;difficulty<6;difficulty++)foreach(var hero in Heroes)
        {
            number++;attempts.WriteLine(JsonSerializer.Serialize(new{number,theme,difficulty,hero=hero.ToString(),build="direct-engine",boss=true,seed=73,config.Version,config.ContentHash,priorBudget=121,maximumBudget=300}));attempts.Flush();
            var row=Run(config,difficulty,hero,"direct-engine",73,actions,resources);results.WriteLine(JsonSerializer.Serialize(row));results.Flush();actions.Flush();resources.Flush();
        }
        Assert.Equal(18,number);
    }

    [Fact(Skip="Requires the explicit thirty-encounter C16 expansion admission.",SkipUnless=nameof(Enabled))]
    public void AdditionalBuildsAndElitesRecordOneBoundedFormalThemeRoster()
    {
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_C16_CALIBRATION_DIR")??throw new InvalidOperationException("Owned evidence directory required.");
        Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        var config=GameConfigCatalog.Current;var theme=config.SeasonThemes!.SelectedThemeId;
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"));
        using var actions=new StreamWriter(Path.Combine(directory,"actions.original.jsonl"));
        using var resources=new StreamWriter(Path.Combine(directory,"monster-resources.original.jsonl"));
        using var results=new StreamWriter(Path.Combine(directory,"encounters.original.jsonl"));
        var number=0;
        foreach(var difficulty in BoundaryDifficulties)foreach(var hero in Heroes)foreach(var build in Builds)foreach(var boss in EncounterKinds)
        {
            if(build=="direct-engine"&&boss)continue; // The six original Fire/D2,D5 cases are already retained.
            number++;attempts.WriteLine(JsonSerializer.Serialize(new{number,theme,difficulty,hero=hero.ToString(),build,boss,seed=73,config.Version,config.ContentHash,priorBudget=139,maximumBudget=300}));attempts.Flush();
            var row=Run(config,difficulty,hero,build,73,actions,resources,boss);results.WriteLine(JsonSerializer.Serialize(row));results.Flush();actions.Flush();resources.Flush();
        }
        Assert.Equal(30,number);
    }

    [Fact(Skip="Requires the explicit eighteen-encounter Wood comparison admission.",SkipUnless=nameof(Enabled))]
    public void WoodBoundarySeparatesRegenerationFromShieldWorkAcrossThreeBuilds()
    {
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_C16_CALIBRATION_DIR")??throw new InvalidOperationException("Owned evidence directory required.");
        Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        var config=Configuration("Wood");var theme=config.SeasonThemes!.SelectedThemeId;Assert.Equal("Wood",theme);
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"));
        using var actions=new StreamWriter(Path.Combine(directory,"actions.original.jsonl"));
        using var resources=new StreamWriter(Path.Combine(directory,"monster-resources.original.jsonl"));
        using var results=new StreamWriter(Path.Combine(directory,"encounters.original.jsonl"));
        var number=0;
        foreach(var hero in Heroes)foreach(var build in Builds)foreach(var boss in EncounterKinds)
        {
            number++;attempts.WriteLine(JsonSerializer.Serialize(new{number,theme,difficulty=5,hero=hero.ToString(),build,boss,seed=73,config.Version,config.ContentHash,priorBudget=169,maximumBudget=300}));attempts.Flush();
            var row=Run(config,5,hero,build,73,actions,resources,boss);results.WriteLine(JsonSerializer.Serialize(row));results.Flush();actions.Flush();resources.Flush();
        }
        Assert.Equal(18,number);
    }

    [Fact(Skip="Requires the explicit twelve-encounter counter-armor probe admission.",SkipUnless=nameof(Enabled))]
    public void CounterArmorProbeUsesTheSameDecksAndUnmodifiedFireWoodEnemies()
    {
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_C16_CALIBRATION_DIR")??throw new InvalidOperationException("Owned evidence directory required.");
        Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"));
        using var actions=new StreamWriter(Path.Combine(directory,"actions.original.jsonl"));
        using var resources=new StreamWriter(Path.Combine(directory,"monster-resources.original.jsonl"));
        using var results=new StreamWriter(Path.Combine(directory,"encounters.original.jsonl"));
        var number=0;
        foreach(var theme in CounterProbeThemes)
        {
            var config=Configuration(theme);
            foreach(var hero in Heroes)foreach(var boss in EncounterKinds)
            {
                number++;attempts.WriteLine(JsonSerializer.Serialize(new{number,theme,difficulty=5,hero=hero.ToString(),build="counter-offense",boss,seed=73,config.Version,config.ContentHash,priorBudget=187,maximumBudget=300}));attempts.Flush();
                var row=Run(config,5,hero,"counter-offense",73,actions,resources,boss);results.WriteLine(JsonSerializer.Serialize(row));results.Flush();actions.Flush();resources.Flush();
            }
        }
        Assert.Equal(12,number);
    }

    [Fact(Skip="Requires the explicit eighteen-encounter remaining-theme admission.",SkipUnless=nameof(Enabled))]
    public void RemainingThemesDirectBoundaryUsesTheOriginalNeutralBenchmark()
    {
        var directory=Environment.GetEnvironmentVariable("FANTASYCARD_C16_CALIBRATION_DIR")??throw new InvalidOperationException("Owned evidence directory required.");
        Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"));
        using var actions=new StreamWriter(Path.Combine(directory,"actions.original.jsonl"));
        using var resources=new StreamWriter(Path.Combine(directory,"monster-resources.original.jsonl"));
        using var results=new StreamWriter(Path.Combine(directory,"encounters.original.jsonl"));
        var number=0;
        foreach(var theme in RemainingProbeThemes)
        {
            var config=Configuration(theme);
            foreach(var hero in Heroes)foreach(var boss in EncounterKinds)
            {
                number++;attempts.WriteLine(JsonSerializer.Serialize(new{number,theme,difficulty=5,hero=hero.ToString(),build="direct-engine",boss,seed=73,config.Version,config.ContentHash,priorBudget=199,maximumBudget=300}));attempts.Flush();
                var row=Run(config,5,hero,"direct-engine",73,actions,resources,boss);results.WriteLine(JsonSerializer.Serialize(row));results.Flush();actions.Flush();resources.Flush();
            }
        }
        Assert.Equal(18,number);
    }

    private static CalibrationRow Run(GameConfigCatalog config,int difficulty,HeroClass hero,string build,int seed,StreamWriter actions,StreamWriter resources,bool isBoss=true)
    {
        var theme=config.SeasonThemes!.Selected;var catalog=CombatCardCatalog.Create(config);var deck=Deck(config,hero,theme,build);Validate(config,hero,deck);
        var armor=Armor(theme,build,difficulty);var id=Guid.NewGuid();
        var context=new FantasyCard.Domain.Seasons.SeasonContext("c16-calibration",difficulty,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,seed,season:context);
        var player=room.AddPlayer(new(id,hero,deck,null,WeaponLevel:difficulty,WornArmor:armor,CardLevels:Enumerable.Repeat(difficulty,20).ToArray()));
        var map=ChaosMapGenerator.Generate(seed,1,config.SeasonThemes).Capture();
        var elite=theme.Element switch{CardElement.Fire=>"E2",CardElement.Wood=>"E5",CardElement.Earth=>"E4",CardElement.Metal=>"E1",_=>"E3"};
        var cell=isBoss?map.Cells.Single(c=>c.IsBoss):map.Cells.First(c=>c.MonsterGroupId.StartsWith('E')) with{MonsterGroupId=elite};
        map=map with{Cells=map.Cells.Select(c=>c.Position==cell.Position?cell:c).ToArray()};
        // Independent boss/representative original elite encounter, not a natural movement route.
        room.InitializeMap(ChaosMapState.Restore(map with{SpawnPositions=[cell.Position]}));
        var monsters=player.Pve!.Monsters.ToArray();var initial=monsters.Select(m=>m.Capture()).ToArray();
        var previous=monsters.ToDictionary(m=>m.MonsterId,m=>(m.Hp,m.Shield));
        var shieldAdded=0L;var shieldDiscarded=0L;var hpAdded=0L;var hpOtherLoss=0L;var totalDamage=0L;var count=0;var previews=0;var last=TimeSpan.FromMilliseconds(-500);var outcome="Timeout";
        resources.WriteLine(JsonSerializer.Serialize(new{kind="start",theme=theme.ThemeId,difficulty,hero=hero.ToString(),build,boss=isBoss,seed,config.Version,config.ContentHash,context,deck,armor,
            actualEquipment=player.Combat.Equipment,initial,scope="Independent encounter, permanent5/effective min(5,D), legal tier armor+3, no red, no resets or combat potion"}));resources.Flush();
        void Observe(string reason,CombatResolution? resolution=null,string? targetId=null)
        {
            foreach(var monster in monsters)
            {
                var prior=previous[monster.MonsterId];var hpDamage=monster.MonsterId==targetId?resolution?.HpDamage??0:0;var shieldDamage=monster.MonsterId==targetId?resolution?.ShieldDamage??0:0;
                var hpDelta=monster.Hp-(prior.Hp-hpDamage);var shieldDelta=monster.Shield-(prior.Shield-shieldDamage);
                hpAdded+=Math.Max(0,hpDelta);hpOtherLoss+=Math.Max(0,-hpDelta);shieldAdded+=Math.Max(0,shieldDelta);shieldDiscarded+=Math.Max(0,-shieldDelta);
                if(hpDelta!=0||shieldDelta!=0)resources.WriteLine(JsonSerializer.Serialize(new{kind="resource-change",theme=theme.ThemeId,difficulty,hero=hero.ToString(),build,boss=isBoss,seconds=room.Elapsed.TotalSeconds,reason,monster.MonsterId,hpBefore=prior.Hp,hpAfter=monster.Hp,shieldBefore=prior.Shield,shieldAfter=monster.Shield,hpDamage,shieldDamage,hpDelta,shieldDelta}));
                previous[monster.MonsterId]=(monster.Hp,monster.Shield);
            }
        }
        while(room.Elapsed.TotalSeconds<600)
        {
            if(player.Phase==RoomPlayerPhase.Dead){outcome="Dead";break;}
            if(player.Phase==RoomPlayerPhase.Choice){outcome="Win";break;}
            if(player.Phase==RoomPlayerPhase.Pve&&player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(id).RemainingMs==0&&player.Combat.Deck.Hand.Count>0)
            {
                var target=monsters.Where(m=>!m.IsDead).OrderBy(m=>m.Hp+m.Shield).First();
                var chosen=Choose(room,player,target,catalog,build,out var used);previews+=used;
                if(chosen.Length>0)
                {
                    var hpBefore=player.Combat.Hp;var intent=target.Intents[target.IntentIndex];
                    var intentIndexBefore=target.IntentIndex;var windupBeforeMs=target.WindupRemaining.TotalMilliseconds;var stunBeforeMs=target.StunRemaining.TotalMilliseconds;var bossPhaseBefore=target.BossPhase;
                    var resolution=room.PlayCards(id,player.Pve!.BattleId,target.MonsterId,chosen.Select(c=>c.InstanceId).ToArray(),room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(id));
                    Assert.True(room.Elapsed-last>=TimeSpan.FromMilliseconds(500));last=room.Elapsed;count++;totalDamage+=resolution.HpDamage+resolution.ShieldDamage;Observe("cast",resolution,target.MonsterId);
                    actions.WriteLine(JsonSerializer.Serialize(new{theme=theme.ThemeId,difficulty,hero=hero.ToString(),build,boss=isBoss,seconds=room.Elapsed.TotalSeconds,selected=chosen.Select(c=>new{c.CardId,c.Level}),hpBefore,hpAfter=player.Combat.Hp,shield=player.Combat.Shield,targetHp=target.Hp,targetShield=target.Shield,telegraphed=intent.Kind.ToString(),intentIndexBefore,intentIndexAfter=target.IntentIndex,windupBeforeMs,stunBeforeMs,bossPhaseBefore,bossPhaseAfter=target.BossPhase,resolution,previews=used}));
                }
            }
            room.Advance(Step,Epoch+room.Elapsed+Step);Observe("tick");
        }
        if(player.Phase==RoomPlayerPhase.Dead)outcome="Dead";if(player.Phase==RoomPlayerPhase.Choice)outcome="Win";
        var remainingHp=monsters.Sum(m=>m.Hp);var remainingShield=monsters.Sum(m=>m.Shield);
        var accounted=initial.Sum(m=>(long)m.Hp+m.Shield)+hpAdded+shieldAdded-hpOtherLoss-shieldDiscarded-remainingHp-remainingShield;
        Assert.Equal(totalDamage,accounted);
        var row=new CalibrationRow(theme.ThemeId,difficulty,hero.ToString(),build,seed,outcome,room.Elapsed.TotalSeconds,count,previews,totalDamage,
            initial.Sum(m=>m.Hp),initial.Sum(m=>m.Shield),hpAdded,shieldAdded,hpOtherLoss,shieldDiscarded,remainingHp,remainingShield,player.Combat.Hp,deck,armor.Select(x=>x.Equipment!).ToArray(),isBoss);
        resources.WriteLine(JsonSerializer.Serialize(new{kind="end",row}));return row;
    }

    private static CombatCardInstance[] Choose(BattleRoom room,RoomPlayerState player,MonsterCombatState target,CombatCardCatalog catalog,string build,out int previews)
    {
        var before=JsonSerializer.Serialize(room.Capture());var hand=player.Combat.Deck.Hand;
        var phase=target.ThemeProfile is {} profile?(target.BossPhase==1?profile.PhaseOnePrimary:profile.PhaseTwoPrimary):target.Intents.First(i=>i.Element!=CardElement.None).Element;
        var preferred=Counter(phase);
        var atRisk=player.Combat.Hp+player.Combat.Shield<player.Combat.EffectiveMaximumHp*.60;
        var current=target.Intents[target.IntentIndex];var visibleValue=MonsterCombatState.PublishedIntentValue(target.Capture());
        var interruption=current.Kind is MonsterIntentKind.Shield or MonsterIntentKind.Regenerate?visibleValue:visibleValue*(atRisk?1.2:.2);
        var candidates=new List<(CombatCardInstance[] Cards,double Score)>();
        double Value(int damage,int heal,int shield,int draws,double charge,double stun,int healthCost,int n,double speedModifier,double speedSeconds)
        {
            var actualHeal=Math.Min(heal,Math.Max(0,player.Combat.EffectiveMaximumHp-player.Combat.Hp));var actualShield=Math.Min(shield,Math.Max(0,player.Combat.MaximumHp/2-player.Combat.Shield));
            var returns=Math.Min(5-hand.Count+n,draws+Math.Min(1,charge));
            var value=Math.Min(damage,target.Hp+target.Shield)+actualHeal*(atRisk?2:.2)+actualShield*(atRisk?1:.1)+returns*6-n*1.25-healthCost*(atRisk?3:.5);
            if(speedSeconds>0&&speedModifier<0)
            {
                var projected=Math.Clamp(player.Combat.NaturalDrawIntervalSeconds*(1+speedModifier),player.Combat.Equipment.MinimumDrawInterval??1.8,player.Combat.Equipment.MaximumDrawInterval??6);
                value+=Math.Max(0,1/projected-1/player.Combat.DrawIntervalSeconds)*Math.Min(15,speedSeconds)*12;
            }
            if(target.WindupRemaining>TimeSpan.Zero&&target.StunRemaining<=TimeSpan.Zero&&stun>0)value+=interruption*(build=="fortress-control"?1.3:1);
            if(healthCost>=player.Combat.Hp)value-=10000;
            return value;
        }
        for(var mask=1;mask<(1<<hand.Count);mask++)
        {
            var cards=hand.Where((_,i)=>(mask&(1<<i))!=0).OrderByDescending(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride).Effect.Element==preferred).ThenBy(c=>c.CardId,StringComparer.Ordinal).ToArray();
            var draft=CombatResolver.Resolve(cards.Select(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride)).ToArray(),player.Combat,target.ElementalResistance);
            candidates.Add((cards,Value(draft.Damage,draft.Heal,draft.Shield,draft.ImmediateDraw,draft.DrawCharge,draft.Stun.TotalSeconds,draft.HealthCost,cards.Length,draft.DrawSpeedModifier,draft.DrawSpeedDuration.TotalSeconds)));
        }
        var best=Array.Empty<CombatCardInstance>();var bestValue=double.NegativeInfinity;previews=0;
        foreach(var candidate in candidates.OrderByDescending(x=>x.Score).Take(3))
        {
            var preview=room.PreviewCards(player.PlayerId,player.Pve!.BattleId,target.MonsterId,candidate.Cards.Select(c=>c.InstanceId).ToArray(),room.Revision,Epoch+room.Elapsed);previews++;
            var score=Value(preview.HpDamage+preview.ShieldDamage,preview.Heal,preview.ShieldGain,preview.ImmediateDraw,preview.DrawCharge,preview.StunSeconds,preview.HealthCost,candidate.Cards.Length,preview.DrawSpeedModifier,preview.DrawSpeedSeconds);
            if(score>bestValue){bestValue=score;best=candidate.Cards;}
        }
        Assert.Equal(before,JsonSerializer.Serialize(room.Capture()));
        return bestValue<-1000?[]:best;
    }

    private static GameConfigCatalog Configuration(string theme)=>theme==GameConfigCatalog.Current.SeasonThemes!.SelectedThemeId?GameConfigCatalog.Current:SeasonThemeConfigIntegrationTests.Variant(theme);
    private static void Validate(GameConfigCatalog config,HeroClass hero,string[] deck)=>DeckRules.Validate(hero,deck,config.Cards.Where(c=>c.IsCodex).ToDictionary(c=>c.CardId,c=>new OwnedCard(c.CardId,c.HeroClass,(CardRarity)c.Rarity,1,false)));
    private static string[] Deck(GameConfigCatalog config,HeroClass hero,SeasonThemeDefinition theme,string build)
    {
        var prefix=hero==HeroClass.Mage?"MAG":hero==HeroClass.Priest?"PRI":"GUA";
        var available=config.Cards.Where(c=>c.Enabled&&c.IsCodex&&(c.HeroClass is null||c.HeroClass==hero)).ToDictionary(c=>c.CardId);
        IEnumerable<string> requested=build switch
        {
            "direct-engine"=>DirectCore.Concat(new[]{prefix+"-09",prefix+"-10","GP13","GP19","GP10","ET-"+Counter(theme.PhaseOnePrimary).ToString().ToUpperInvariant()+"-P"}),
            "fortress-control"=>FortressCore.Concat(new[]{prefix+"-08",prefix+"-09",prefix+"-10","GP15","GP16","GP17","GB19","GB20","GP13","ET-WATER-P","ET-WOOD-P"}),
            "counter-combo" or "counter-offense"=>CounterCore.Concat(new[]{prefix+"-09",prefix+"-10"}).Concat(available.Values.Where(c=>c.Effect.ElementalDamage>0&&c.Effect.Element==Counter(theme.PhaseOnePrimary)).OrderByDescending(c=>c.Rarity).ThenBy(c=>c.CardId,StringComparer.Ordinal).Take(6).Select(c=>c.CardId))
                .Concat(available.Values.Where(c=>c.Effect.ElementalDamage>0&&c.Effect.Element==Counter(theme.PhaseTwoPrimary)).OrderByDescending(c=>c.Rarity).ThenBy(c=>c.CardId,StringComparer.Ordinal).Take(6).Select(c=>c.CardId)),
            _=>throw new InvalidOperationException("Unknown declared calibration archetype.")
        };
        var result=new List<string>();var orangeKinds=new HashSet<bool>();
        foreach(var id in requested.Concat(Fallback))
        {
            if(result.Contains(id,StringComparer.Ordinal))continue;var card=available[id];
            if(card.Rarity==(short)CardRarity.Orange&&!orangeKinds.Add(card.HeroClass is not null))continue;
            result.Add(id);if(result.Count==20)break;
        }
        return result.ToArray();
    }
    private static ExplorationItem[] Armor(SeasonThemeDefinition theme,string build,int difficulty)=>Slots.Select((slot,i)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
        Equipment:new(slot,difficulty==0?"Blue":difficulty==1?"Purple":i==0?"Orange":"Purple",(build=="counter-offense"?Counter(i<3?theme.PhaseOnePrimary:theme.PhaseTwoPrimary):(i<3?theme.PhaseOnePrimary:theme.PhaseTwoPrimary)).ToString(),difficulty==0?null:i<2?"Piercing":build=="fortress-control"?"Bulwark":"Vitality","DrawInterval",3,StatsVersion:"season-equipment-v1"),IsGenerated:false)).ToArray();
    private static CardElement Counter(CardElement target)=>target switch{CardElement.Fire=>CardElement.Water,CardElement.Wood=>CardElement.Metal,CardElement.Earth=>CardElement.Wood,CardElement.Metal=>CardElement.Fire,_=>CardElement.Earth};
    private sealed record CalibrationRow(string Theme,int Difficulty,string Hero,string Build,int Seed,string Outcome,double Seconds,int Actions,int PreviewCalls,long Damage,
        int InitialHp,int InitialShield,long ActualHpRegeneration,long ActualShieldAdded,long HpOtherLoss,long ShieldDiscarded,int RemainingHp,int RemainingShield,int EndingHp,IReadOnlyList<string> Deck,IReadOnlyList<EquipmentRewardData> Armor,bool Boss=true);
}
