using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Frozen D01 boundaries using the published catalog, real resolver and 100ms room clock.</summary>
public sealed class SeasonCombatBoundaryMatrixTests
{
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D01_BOUNDARIES") == "1";
    private static readonly string[] Groups = ["O1","O2","O3","O4","O5","O6","O7","O8","M1","M2","M3","M4","M5","E1","E2","E3","E4","E5","E6","BOSS","BOX"];
    private static readonly string[] Elements = ["Fire","Wood","Earth","Metal","Water","Mixed"];
    private static readonly string[] Variants = ["diagnostic","piercing3","piercing-vitality","bulwark5","bulwark-vitality","rapid-draw"];
    private static readonly string[] Slots = ["Head","Hands","Chest","Legs","Feet"];
    private static readonly string[] Core = ["GP15","GP16","GP17","GB19","GB20","GB23","GP20","GP21","GP22","ET-WATER-P","ET-WOOD-P","GO03","GP18","GP23"];
    private static readonly string[] Tail = ["GP13","GP19","GP10","GP02"];
    private static readonly int[] Counts = [0,5,10,15];
    private static readonly int[] Health = [100,60,25];
    private static readonly int[] ArmorLevels = [0,0,1,2,3,5];
    private static readonly TimeSpan Tick = TimeSpan.FromMilliseconds(100);
    private static readonly DateTimeOffset Epoch = new(2026,11,20,0,0,0,TimeSpan.Zero);
    private static readonly Dictionary<string,string> Species = new(StringComparer.Ordinal)
    {
        ["fire-bat"]="FireBat",["thorn-mite"]="ThornMite",["murk-snail"]="MudHydra",["sand-lizard"]="SandLizard",
        ["rust-rat"]="RustRat",["box-spirit"]="BoxSpirit",["metal-guard"]="GoldGuard",["fire-herald"]="FireReaver",
        ["marsh-mother"]="SwampMother",["stone-guard"]="StoneGuard",["thorn-guard"]="ThornGuard",["annihilation-core"]="VoidCore"
    };

    private sealed record Case(string Id,string Family,string Hero,int Growth,int Difficulty,string Group,string Element,int MonsterCards,int HpPercent,string Variant,int Seed);

    private static Case[] Plan()
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D01_PLAN") ?? throw new InvalidOperationException("Frozen D01 plan required.")));
        var prior=document.RootElement.GetProperty("prior_used").GetInt32();
        var rows=document.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Case(
            x.GetProperty("id").GetString()!,x.GetProperty("family").GetString()!,x.GetProperty("hero").GetString()!,
            x.GetProperty("growth").GetInt32(),x.GetProperty("difficulty").GetInt32(),x.GetProperty("group").GetString()!,
            x.GetProperty("element").GetString()!,x.GetProperty("monster_cards").GetInt32(),x.GetProperty("hp_percent").GetInt32(),
            x.GetProperty("variant").GetString()!,x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows)
        {
            Assert.True(Enum.TryParse<HeroClass>(row.Hero,out var hero)&&Enum.IsDefined(hero));Assert.InRange(row.Growth,0,5);Assert.InRange(row.Difficulty,0,5);
            Assert.Contains(row.Group,Groups);Assert.Contains(row.Element,Elements);Assert.Contains(row.MonsterCards,Counts);Assert.Contains(row.HpPercent,Health);Assert.Contains(row.Variant,Variants);
            Assert.True(row.Variant=="diagnostic" || row.Growth==5&&row.Difficulty==5);
        }
        return rows;
    }

    [Fact(Skip="Explicit frozen D01 plan legality only; no timed encounters.",SkipUnless=nameof(Enabled))]
    public void FrozenInputsUseLegalEntryCapsAndActualPublishedProfiles()
    {
        var config=GameConfigCatalog.Current;var rows=Plan();
        foreach(var row in rows)
        {
            var hero=Enum.Parse<HeroClass>(row.Hero);var armor=Armor(row);var deck=Deck(hero);
            DeckRules.Validate(hero,deck,config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            Assert.All(armor,x=>Assert.True(EquipmentRewardRules.IsValid(x.Equipment!)));
            var context=new SeasonContext("d01-boundaries",row.Difficulty,"season-v1",config.Version,"season-equipment-v1");
            SeasonLootRules.RequireEntry(context,armor.Select(x=>x.Equipment!),config);
            var profile=EquipmentCombatRules.Calculate(armor.Select(x=>new CombatEquipmentItem(Guid.Parse(x.ItemId),x.Equipment!.Slot,x.Equipment.Quality,x.Equipment.Level,Enum.Parse<CardElement>(x.Equipment.Element),x.Equipment.EffectAffix,x.Equipment.SecondaryTrait,x.Equipment.UniqueAffix)).ToArray(),config,"season-equipment-v1");
            var state=new PlayerCombatState(hero,deck,new Random(row.Seed),Math.Min(row.Growth,row.Difficulty),profile,Enumerable.Repeat(Math.Min(row.Growth,row.Difficulty),20).ToArray());
            Assert.InRange(state.NaturalDrawIntervalSeconds,1.8,6);
            foreach(var element in Enum.GetValues<CardElement>().Where(x=>x!=CardElement.None))Assert.InRange(profile.Resistance(element),0,.6);
            if(row.Variant=="rapid-draw")Assert.Equal(1.8,state.NaturalDrawIntervalSeconds,8);
        }
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D01_PREFLIGHT_OUTPUT") ?? throw new InvalidOperationException("New proof output required."),JsonSerializer.Serialize(new {cases=rows.Length,no_clock_or_resolver_execution=true,config.Version,config.ContentHash}));
    }

    [Fact(Skip="Explicit budgeted D01 clock matrix; never rerun an already attempted roster.",SkipUnless=nameof(Enabled))]
    public void DeclaredBoundaryEncountersPreserveCombatResourcesAndMonsterCards()
    {
        var rows=Plan();var output=Environment.GetEnvironmentVariable("FANTASYCARD_D01_OUTPUT") ?? throw new InvalidOperationException("Owned output required.");
        Assert.False(Directory.Exists(output));Directory.CreateDirectory(output);
        using var attempts=new StreamWriter(Path.Combine(output,"attempts.original.jsonl"));using var trace=new StreamWriter(Path.Combine(output,"events.original.jsonl"));using var results=new StreamWriter(Path.Combine(output,"encounters.original.jsonl"));
        foreach(var row in rows)
        {
            attempts.WriteLine(JsonSerializer.Serialize(row));attempts.Flush();
            Run(row,trace,results);results.Flush();trace.Flush();
        }
    }

    private static void Run(Case row,StreamWriter trace,StreamWriter results)
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var hero=Enum.Parse<HeroClass>(row.Hero);
        var context=new SeasonContext("d01-boundaries",row.Difficulty,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,row.Seed,season:context);var id=Guid.NewGuid();
        var armor=Armor(row);var deck=Deck(hero);var effective=Math.Min(row.Growth,row.Difficulty);
        var player=room.AddPlayer(new(id,hero,deck,null,WeaponLevel:effective,WornArmor:armor,CardLevels:Enumerable.Repeat(effective,20).ToArray(),LootPreferenceElement:row.Element=="Mixed"?"Fire":row.Element));
        var map=ChaosMapGenerator.Generate(row.Seed,1,config.SeasonThemes).Capture();
        var layer=row.Group=="BOSS"||row.Group.StartsWith('E')?ChaosMapLayer.Core:row.Group.StartsWith('M')?ChaosMapLayer.Middle:ChaosMapLayer.Outer;
        var cell=row.Group=="BOSS"?map.Cells.Single(x=>x.IsBoss):map.Cells.First(x=>x.Layer==layer&&!x.IsBoss);
        cell=cell with {MonsterGroupId=row.Group,TreasureElement=row.Group=="BOX"?(CardElement)(row.Seed%6):null};
        room.InitializeMap(ChaosMapState.Restore(map with {Cells=map.Cells.Select(x=>x.Position==cell.Position?cell:x).ToArray(),SpawnPositions=[cell.Position]}));
        // Reconstructed legal prior state, not a claim to have traversed earlier cells.
        var monsterDefinitions=config.Cards.Where(x=>x.MonsterType is not null).OrderBy(x=>x.CardId,StringComparer.Ordinal).ToArray();
        for(var i=0;i<row.MonsterCards;i++)player.Combat.Deck.AddToDiscard(new(Guid.NewGuid(),monsterDefinitions[i%monsterDefinitions.Length].CardId));
        player.Combat.Restore(player.Combat.Capture() with {Hp=Math.Max(1,player.Combat.MaximumHp*row.HpPercent/100)});
        var originalBase=Instances(player).Where(x=>!x.CardId.StartsWith("M-",StringComparison.Ordinal)).Select(x=>x.InstanceId).ToHashSet();Assert.Equal(20,originalBase.Count);
        var monsters=player.Pve!.Monsters.ToArray();var initial=monsters.Select(x=>x.Capture()).ToArray();
        var previous=monsters.ToDictionary(x=>x.MonsterId,x=>(x.Hp,x.Shield));
        long hpAdded=0,shieldAdded=0,hpOtherLoss=0,shieldDiscarded=0,totalDamage=0;var casts=0;var kills=0;var previewCalls=0;var last=TimeSpan.FromMilliseconds(-500);
        trace.WriteLine(JsonSerializer.Serialize(new {kind="start",row,config.Version,config.ContentHash,context,deck,armor,player.Combat.Equipment,initial,startingCombat=player.Combat.Capture(),pool_setup="Prior-state fixture only; additional actual kills must automatically add one base-level monster card. No route claim."}));trace.Flush();
        void Observe(string reason,CombatResolution? resolution=null,string? target=null)
        {
            foreach(var monster in monsters)
            {
                var prior=previous[monster.MonsterId];var hd=monster.MonsterId==target?resolution?.HpDamage??0:0;var sd=monster.MonsterId==target?resolution?.ShieldDamage??0:0;
                var hp=monster.Hp-prior.Hp+hd;var shield=monster.Shield-prior.Shield+sd;
                hpAdded+=Math.Max(0,hp);hpOtherLoss+=Math.Max(0,-hp);shieldAdded+=Math.Max(0,shield);shieldDiscarded+=Math.Max(0,-shield);
                if(hp!=0||shield!=0)trace.WriteLine(JsonSerializer.Serialize(new {kind="resource",row.Id,seconds=room.Elapsed.TotalSeconds,reason,monster.MonsterId,hpBefore=prior.Hp,hpAfter=monster.Hp,shieldBefore=prior.Shield,shieldAfter=monster.Shield,hpDamage=hd,shieldDamage=sd,hpDelta=hp,shieldDelta=shield}));
                previous[monster.MonsterId]=(monster.Hp,monster.Shield);
            }
        }
        while(room.Elapsed.TotalSeconds<600&&player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Choice))
        {
            var pool=Instances(player);Assert.Equal(20+row.MonsterCards+kills,pool.Length);Assert.Equal(pool.Length,pool.Select(x=>x.InstanceId).Distinct().Count());
            Assert.True(originalBase.IsSubsetOf(pool.Select(x=>x.InstanceId)));Assert.InRange(player.Combat.Hp,0,player.Combat.EffectiveMaximumHp);Assert.InRange(player.Combat.Shield,0,player.Combat.MaximumHp/2);
            Assert.InRange(player.Combat.Deck.Hand.Count,0,5);Assert.InRange(player.Combat.Deck.DrawCharge,0,.9999999999999999);
            if(player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(id).RemainingMs==0&&player.Combat.Deck.Hand.Count>0)
            {
                var target=monsters.Where(x=>!x.IsDead).OrderBy(x=>x.Hp+x.Shield).First();
                var beforePreview=JsonSerializer.Serialize(room.Capture());var hand=player.Combat.Deck.Hand;
                var candidates=new List<(CombatCardInstance[] Cards,double Score)>();
                for(var mask=1;mask<(1<<hand.Count);mask++)
                {
                    var selected=hand.Where((_,i)=>(mask&(1<<i))!=0).ToArray();
                    var draft=CombatResolver.Resolve(selected.Select(x=>catalog.Get(x.CardId,x.Level,x.ElementOverride)).ToArray(),player.Combat,target.ElementalResistance);
                    candidates.Add((selected,Score(draft.Damage,draft.Heal,draft.Shield,draft.ImmediateDraw,draft.HealthCost,selected.Length,player,target)));
                }
                var best=Array.Empty<CombatCardInstance>();var bestScore=double.NegativeInfinity;
                foreach(var candidate in candidates.OrderByDescending(x=>x.Score).Take(3))
                {
                    var preview=room.PreviewCards(id,player.Pve!.BattleId,target.MonsterId,candidate.Cards.Select(x=>x.InstanceId).ToArray(),room.Revision,Epoch+room.Elapsed);previewCalls++;
                    var value=Score(preview.HpDamage+preview.ShieldDamage,preview.Heal,preview.ShieldGain,preview.ImmediateDraw,preview.HealthCost,candidate.Cards.Length,player,target);
                    if(value>bestScore){bestScore=value;best=candidate.Cards;}
                }
                Assert.Equal(beforePreview,JsonSerializer.Serialize(room.Capture()));
                if(bestScore>-1000)
                {
                    var beforeIds=Instances(player).Select(x=>x.InstanceId).ToHashSet();var hpBefore=player.Combat.Hp;var shieldBefore=player.Combat.Shield;
                    var resolution=room.PlayCards(id,player.Pve!.BattleId,target.MonsterId,best.Select(x=>x.InstanceId).ToArray(),room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(id));
                    Assert.True(room.Elapsed-last>=TimeSpan.FromMilliseconds(500));last=room.Elapsed;casts++;totalDamage+=resolution.HpDamage+resolution.ShieldDamage;Observe("cast",resolution,target.MonsterId);
                    var added=Instances(player).Where(x=>!beforeIds.Contains(x.InstanceId)).ToArray();
                    if(resolution.TargetDefeated)
                    {
                        kills++;var species=target.MonsterId.EndsWith("-a",StringComparison.Ordinal)||target.MonsterId.EndsWith("-b",StringComparison.Ordinal)?target.MonsterId[..^2]:target.MonsterId;
                        var expected=config.Cards.Single(x=>x.MonsterType==Species[species]);var actual=Assert.Single(added);Assert.Equal(expected.CardId,actual.CardId);Assert.Equal(0,actual.Level);Assert.Contains(actual,player.Combat.Deck.Discard);
                        Assert.Equal(species=="box-spirit"?target.Intents[0].Element:(CardElement?)null,actual.ElementOverride);
                    }
                    else Assert.Empty(added);
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="cast",row.Id,seconds=room.Elapsed.TotalSeconds,battle=resolution.BattleId,selected=best.Select(x=>new{x.CardId,x.Level}),hpBefore,hpAfter=player.Combat.Hp,shieldBefore,shieldAfter=player.Combat.Shield,resolution,added}));
                }
            }
            room.Advance(Tick,Epoch+room.Elapsed+Tick);Observe("tick");
        }
        var outcome=player.Phase==RoomPlayerPhase.Dead?"Dead":player.Phase==RoomPlayerPhase.Choice?"Win":"Timeout";
        var remainingHp=monsters.Sum(x=>x.Hp);var remainingShield=monsters.Sum(x=>x.Shield);
        Assert.Equal(totalDamage,initial.Sum(x=>(long)x.Hp+x.Shield)+hpAdded+shieldAdded-hpOtherLoss-shieldDiscarded-remainingHp-remainingShield);
        var result=new {row,outcome,seconds=room.Elapsed.TotalSeconds,casts,kills,previewCalls,totalDamage,initialHp=initial.Sum(x=>x.Hp),initialShield=initial.Sum(x=>x.Shield),hpAdded,shieldAdded,hpOtherLoss,shieldDiscarded,remainingHp,remainingShield,endingHp=player.Combat.Hp,endingShield=player.Combat.Shield,finalPool=Instances(player).Length,effectiveLevel=effective,armorLevel=row.Growth==0?0:ArmorLevels[row.Growth],scope="Independent combat boundary; not route, efficiency, population or settlement acceptance."};
        trace.WriteLine(JsonSerializer.Serialize(new {kind="end",result}));results.WriteLine(JsonSerializer.Serialize(result));
    }

    private static double Score(int damage,int heal,int shield,int draws,int healthCost,int count,RoomPlayerState player,MonsterCombatState target) =>
        Math.Min(damage,target.Hp+target.Shield)+Math.Min(heal,player.Combat.EffectiveMaximumHp-player.Combat.Hp)*1.5+
        Math.Min(shield,player.Combat.MaximumHp/2-player.Combat.Shield)*.8+draws*4-count-(healthCost>=player.Combat.Hp?10000:healthCost);
    private static CombatCardInstance[] Instances(RoomPlayerState player)=>player.Combat.Deck.Hand.Concat(player.Combat.Deck.Library).Concat(player.Combat.Deck.Discard).ToArray();
    private static string[] Deck(HeroClass hero)=>Core.Concat(new[]{hero==HeroClass.Mage?"MAG-09":hero==HeroClass.Priest?"PRI-09":"GUA-09",hero==HeroClass.Mage?"MAG-10":hero==HeroClass.Priest?"PRI-10":"GUA-10"}).Concat(Tail).ToArray();
    private static ExplorationItem[] Armor(Case row)
    {
        if(row.Growth==0)return [];
        return Slots.Select((slot,i)=>
        {
            var quality=row.Growth switch{1=>i<3?"Green":"Blue",2=>"Blue",3=>"Purple",_=>i==0?row.Variant=="rapid-draw"?"Red":"Orange":"Purple"};
            if(row.Difficulty==0&&quality is "Purple" or "Orange" or "Red")quality="Blue";
            if(row.Difficulty==1&&quality is "Orange" or "Red")quality="Purple";
            var effect=row.Variant switch{"piercing3"=>i<3?"Piercing":null,"piercing-vitality"=>i<2?"Piercing":"Vitality","bulwark5"=>"Bulwark","bulwark-vitality"=>i<2?"Bulwark":"Vitality",_=>i==0&&quality is "Orange" or "Red"?"Piercing":null};
            if(quality is "White" or "Green" or "Blue")effect=null;
            var element=row.Element=="Mixed"?Elements[i]:row.Element;
            return new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,Equipment:new(slot,quality,element,effect,"DrawInterval",ArmorLevels[row.Growth],UniqueAffix:row.Variant=="rapid-draw"&&i==0?"RapidDraw":null,StatsVersion:"season-equipment-v1"),IsGenerated:false);
        }).ToArray();
    }
}
