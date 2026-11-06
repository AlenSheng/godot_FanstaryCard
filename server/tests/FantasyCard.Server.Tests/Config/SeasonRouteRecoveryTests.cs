using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Natural generated routes and real extraction with action/reading snapshot recovery.</summary>
public sealed class SeasonRouteRecoveryTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D02_ROUTES")=="1";
    private static readonly string[] Slots=["Head","Hands","Chest","Legs","Feet"];
    private static readonly string[] Core=["GP15","GP16","GP17","GB19","GB20","GB23","GP20","GP21","GP22","ET-WATER-P","ET-WOOD-P","GO03","GP18","GP23"];
    private static readonly string[] Tail=["GP13","GP19","GP10","GP02"];
    private static readonly TimeSpan Tick=TimeSpan.FromMilliseconds(100);
    private static readonly DateTimeOffset Epoch=new(2026,11,20,0,0,0,TimeSpan.Zero);
    private sealed record Scenario(string Id,string Hero,int Difficulty,int Seed);

    private static Scenario[] Plan()
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D02_ROUTE_PLAN")??throw new InvalidOperationException("Frozen route plan required.")));
        var prior=document.RootElement.GetProperty("prior_used").GetInt32();
        var rows=document.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Scenario(x.GetProperty("id").GetString()!,x.GetProperty("hero").GetString()!,x.GetProperty("difficulty").GetInt32(),x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows){Assert.True(Enum.TryParse<HeroClass>(row.Hero,out var hero)&&Enum.IsDefined(hero));Assert.InRange(row.Difficulty,0,5);}
        return rows;
    }

    [Fact(Skip="Requires explicit frozen D02 natural-route inputs; no encounter clock.",SkipUnless=nameof(Enabled))]
    public void OriginalMapsAndDeclaredLoadoutsHaveLegalBossRoutes()
    {
        var config=GameConfigCatalog.Current;var rows=Plan();
        foreach(var row in rows)
        {
            var hero=Enum.Parse<HeroClass>(row.Hero);DeckRules.Validate(hero,Deck(hero),config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            SeasonLootRules.RequireEntry(new("d02-routes",row.Difficulty,"season-v1",config.Version,"season-equipment-v1"),Armor(row.Difficulty).Select(x=>x.Equipment!),config);
            var map=ChaosMapGenerator.Generate(row.Seed,1,config.SeasonThemes);var route=Path(map);
            Assert.Equal(map.SpawnPositions[0],route[0]);Assert.Equal(map.BossPosition,route[^1]);
            Assert.All(route.Zip(route.Skip(1)),pair=>Assert.True(map.CanMove(pair.First,pair.Second)&&pair.First.ManhattanDistance(pair.Second)==1));
        }
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D02_ROUTE_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New proof output required."),JsonSerializer.Serialize(new {cases=rows.Length,config.Version,config.ContentHash,map_edits=false,new_timed_routes=0}));
    }

    [Fact(Skip="Budgeted current routes; no completed B05 or other matrix replay.",SkipUnless=nameof(Enabled))]
    public void DeclaredNaturalRoutesKeepRecoveryAndReachTheirRealTerminalOutcome()
    {
        var rows=Plan();var directory=Environment.GetEnvironmentVariable("FANTASYCARD_D02_ROUTE_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        using var attempts=new StreamWriter(System.IO.Path.Combine(directory,"attempts.original.jsonl"));using var trace=new StreamWriter(System.IO.Path.Combine(directory,"events.original.jsonl"));using var results=new StreamWriter(System.IO.Path.Combine(directory,"routes.original.jsonl"));
        foreach(var row in rows){attempts.WriteLine(JsonSerializer.Serialize(row));attempts.Flush();Run(row,trace,results);trace.Flush();results.Flush();}
    }

    private static void Run(Scenario scenario,StreamWriter trace,StreamWriter results)
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var hero=Enum.Parse<HeroClass>(scenario.Hero);var id=Guid.NewGuid();
        var context=new SeasonContext("d02-routes",scenario.Difficulty,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,scenario.Seed,season:context);
        var player=room.AddPlayer(new(id,hero,Deck(hero),null,WeaponLevel:scenario.Difficulty,WornArmor:Armor(scenario.Difficulty),CardLevels:Enumerable.Repeat(scenario.Difficulty,20).ToArray()));
        for(var i=0;i<2;i++)Assert.True(player.Inventory.TryAdd(new(Guid.NewGuid().ToString("D"),ExplorationItemKind.HealthPotion,IsGenerated:false)));
        var map=ChaosMapGenerator.Generate(scenario.Seed,1,config.SeasonThemes);var mapOriginal=JsonSerializer.Serialize(map.Capture());var path=Path(map);room.InitializeMap(map);
        var originalIds=Instances(player).Select(x=>x.InstanceId).ToHashSet();var pathIndex=0;var casts=0;var kills=0;var clears=0;var potions=0;var springs=0;var redRolls=0;
        var recoveredAction=false;var recoveredExtraction=false;var extracting=false;DateTimeOffset? expectedExtraction=null;
        var open=false;var monsters=Array.Empty<MonsterCombatState>();var previous=new Dictionary<string,(int Hp,int Shield)>(StringComparer.Ordinal);
        var initialHp=0;var initialShield=0;long hpAdded=0,shieldAdded=0,hpOtherLoss=0,shieldDiscarded=0,damage=0,totalDamage=0;
        trace.WriteLine(JsonSerializer.Serialize(new {kind="start",scenario,config.Version,config.ContentHash,context,path,map=map.Capture(),player=room.CapturePlayer(id),permanent_card_weapon_assumption=5,actual_effective_level=scenario.Difficulty,quota_fixture="Only if a real red roll hits, assume that logical server's weekly quota was already spent; do not mint or claim PostgreSQL verification."}));trace.Flush();
        void Begin()
        {
            monsters=player.Pve!.Monsters.ToArray();previous=monsters.ToDictionary(x=>x.MonsterId,x=>(x.Hp,x.Shield),StringComparer.Ordinal);
            initialHp=monsters.Sum(x=>x.Hp);initialShield=monsters.Sum(x=>x.Shield);hpAdded=shieldAdded=hpOtherLoss=shieldDiscarded=damage=0;open=true;
            trace.WriteLine(JsonSerializer.Serialize(new {kind="encounter-start",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,position=player.Position,battle=player.Pve.BattleId,monsters=monsters.Select(x=>x.Capture())}));
        }
        void Observe(string reason,CombatResolution? resolution=null,string? target=null)
        {
            if(!open)return;
            foreach(var monster in monsters)
            {
                var prior=previous[monster.MonsterId];var hd=monster.MonsterId==target?resolution?.HpDamage??0:0;var sd=monster.MonsterId==target?resolution?.ShieldDamage??0:0;
                var hp=monster.Hp-prior.Hp+hd;var shield=monster.Shield-prior.Shield+sd;hpAdded+=Math.Max(0,hp);hpOtherLoss+=Math.Max(0,-hp);shieldAdded+=Math.Max(0,shield);shieldDiscarded+=Math.Max(0,-shield);
                if(hp!=0||shield!=0)trace.WriteLine(JsonSerializer.Serialize(new {kind="resource",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,reason,monster.MonsterId,hpBefore=prior.Hp,hpAfter=monster.Hp,shieldBefore=prior.Shield,shieldAfter=monster.Shield,hpDamage=hd,shieldDamage=sd,hpDelta=hp,shieldDelta=shield}));
                previous[monster.MonsterId]=(monster.Hp,monster.Shield);
            }
        }
        void Finish(string outcome)
        {
            var remainingHp=monsters.Sum(x=>x.Hp);var remainingShield=monsters.Sum(x=>x.Shield);
            Assert.Equal(damage,(long)initialHp+initialShield+hpAdded+shieldAdded-hpOtherLoss-shieldDiscarded-remainingHp-remainingShield);totalDamage+=damage;
            trace.WriteLine(JsonSerializer.Serialize(new {kind="encounter-end",scenario.Id,pathIndex,outcome,seconds=room.Elapsed.TotalSeconds,initialHp,initialShield,hpAdded,shieldAdded,hpOtherLoss,shieldDiscarded,remainingHp,remainingShield,damage}));open=false;
        }
        void Step(){room.Advance(Tick,Epoch+room.Elapsed+Tick);Observe("tick");}
        void Recover(string stage,CombatResolution? action=null,Guid[]? selected=null)
        {
            var before=room.Capture();var raw=JsonSerializer.Serialize(before);room=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(raw)!,catalog,scenario.Seed);player=room.GetPlayer(id);Assert.Equivalent(before,room.Capture(),strict:true);
            if(open){monsters=player.Pve!.Monsters.ToArray();previous=monsters.ToDictionary(x=>x.MonsterId,x=>(x.Hp,x.Shield),StringComparer.Ordinal);}
            CombatResolution? replay=null;
            if(action is not null){Assert.NotNull(selected);var pin=JsonSerializer.Serialize(room.Capture());replay=room.ReplayCombatAction(id,action.CombatActionId,action.BattleId,action.TargetId,selected);Assert.True(replay.ActionReplayed);Assert.Equal(pin,JsonSerializer.Serialize(room.Capture()));}
            trace.WriteLine(JsonSerializer.Serialize(new {kind="recovered",scenario.Id,stage,snapshot=room.Capture(),replay,full_snapshot_equivalent=true}));
        }
        Begin();
        while(room.Elapsed.TotalSeconds<1200&&player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted))
        {
            var pool=Instances(player);Assert.Equal(20+kills,pool.Length);Assert.Equal(pool.Length,pool.Select(x=>x.InstanceId).Distinct().Count());Assert.True(originalIds.IsSubsetOf(pool.Select(x=>x.InstanceId)));
            Assert.InRange(player.Combat.Hp,0,player.Combat.EffectiveMaximumHp);Assert.InRange(player.Combat.Shield,0,player.Combat.MaximumHp/2);Assert.InRange(player.Combat.Deck.Hand.Count,0,5);
            if(player.Phase==RoomPlayerPhase.Choice)
            {
                if(open){Finish("Clear");clears++;}
                if(player.PendingRedEvaluation is {} red)
                {
                    var hits=config.SeasonRed!.Hits(red.Source,scenario.Difficulty,red.Roll);var status=hits?"Exhausted":"Miss";room.ApplyRedDrop(id,new(red.AttemptId,status,null));redRolls++;
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="red-adjudication",scenario.Id,evaluation=red,hits,status,fixture_only_no_mint=true}));
                }
                var choices=room.GetRewardChoice(id);var selected=player.Combat.Hp<=player.Combat.MaximumHp*.60?choices.Options.Single(x=>x.Kind==RewardChoiceKind.ImmediateHeal):choices.Options.FirstOrDefault(x=>x.Kind==RewardChoiceKind.EquipmentFragments)??choices.Options.First(x=>x.Kind==RewardChoiceKind.Equipment);
                var hpBefore=player.Combat.Hp;var applied=room.ClaimReward(id,selected.OptionId);trace.WriteLine(JsonSerializer.Serialize(new {kind="reward",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,choices,selected,applied,hpBefore,hpAfter=player.Combat.Hp,inventory=player.Inventory.Capture()}));continue;
            }
            if(player.Phase==RoomPlayerPhase.ActionBar&&!extracting)
            {
                if(player.Combat.Hp<=player.Combat.MaximumHp*.60&&player.Inventory.Items.Any(x=>x.Kind==ExplorationItemKind.HealthPotion))
                {
                    var result=room.UsePotion(id);potions++;trace.WriteLine(JsonSerializer.Serialize(new {kind="potion",scenario.Id,pathIndex,result,player=room.CapturePlayer(id)}));
                }
                if(map.GetCell(player.Position!.Value).HasSpring&&player.Combat.Hp<player.Combat.MaximumHp*.85&&room.CapturePlayer(id).ConsumedSprings?.Contains(player.Position.Value)!=true)
                {
                    room.RequestSpring(id);while(room.CapturePlayer(id).SpringDrink is not null&&room.Elapsed.TotalSeconds<1200)Step();Assert.Null(room.CapturePlayer(id).SpringDrink);springs++;trace.WriteLine(JsonSerializer.Serialize(new {kind="spring",scenario.Id,pathIndex,player=room.CapturePlayer(id)}));
                }
                if(pathIndex+1<path.Length)
                {
                    var from=player.Position!.Value;var to=path[++pathIndex];Assert.True(map.CanMove(from,to)&&from.ManhattanDistance(to)==1);
                    var moved=room.MovePlayerAndPair(id,to,room.Revision,Epoch+room.Elapsed);Assert.Null(moved.StartedDuel);Assert.Equal(to,player.Position);
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="move",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,from,to}));Begin();continue;
                }
                var requestedAt=Epoch+room.Elapsed;var duration=room.RequestExtraction(id);expectedExtraction=requestedAt+duration;extracting=true;Step();Recover("ExtractionReading");recoveredExtraction=true;
                trace.WriteLine(JsonSerializer.Serialize(new {kind="extraction-reading",scenario.Id,requestedAt,duration,expectedExtraction,remaining=room.CapturePlayer(id).ExtractionRemaining}));continue;
            }
            if(player.Phase==RoomPlayerPhase.Pve&&player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(id).RemainingMs==0&&player.Combat.Deck.Hand.Count>0)
            {
                var target=monsters.Where(x=>!x.IsDead).OrderBy(x=>x.Hp+x.Shield).First();var chosen=Choose(room,player,target,catalog,out var previews);
                if(chosen.Length>0)
                {
                    var beforeIds=Instances(player).Select(x=>x.InstanceId).ToHashSet();var ids=chosen.Select(x=>x.InstanceId).ToArray();var hpBefore=player.Combat.Hp;var battle=player.Pve!.BattleId;
                    var resolution=room.PlayCards(id,battle,target.MonsterId,ids,room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(id));casts++;damage+=resolution.HpDamage+resolution.ShieldDamage;Observe("cast",resolution,target.MonsterId);
                    var added=Instances(player).Where(x=>!beforeIds.Contains(x.InstanceId)).ToArray();if(resolution.TargetDefeated){kills++;var card=Assert.Single(added);Assert.StartsWith("M-",card.CardId);Assert.Equal(0,card.Level);Assert.Contains(card,player.Combat.Deck.Discard);}else Assert.Empty(added);
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="cast",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,selected=chosen.Select(x=>new{x.CardId,x.Level}),resolution,previews,added,hpBefore,hpAfter=player.Combat.Hp,shieldAfter=player.Combat.Shield}));
                    if(!recoveredAction){Recover("FirstAcceptedAction",resolution,ids);recoveredAction=true;}
                }
            }
            Step();
        }
        var outcome=player.Phase==RoomPlayerPhase.Extracted?"Extracted":player.Phase==RoomPlayerPhase.Dead?"Dead":"Timeout";if(open)Finish(outcome);
        Assert.Equal(mapOriginal,JsonSerializer.Serialize(room.Map!.Capture()));
        if(outcome=="Extracted"){Assert.Equal(path.Length,clears);Assert.True(recoveredAction&&recoveredExtraction);Assert.Equal(expectedExtraction,player.ExtractionCompletedAt);Assert.Equal(path[^1],player.Position);}
        var resultRow=new {scenario,outcome,seconds=room.Elapsed.TotalSeconds,casts,kills,clears,pathIndex,totalDamage,potions,springs,redRolls,recoveredAction,recoveredExtraction,expectedExtraction,original_map_unchanged=true,snapshot=room.Capture()};trace.WriteLine(JsonSerializer.Serialize(new {kind="end",result=resultRow}));results.WriteLine(JsonSerializer.Serialize(resultRow));
    }

    private static MapPosition[] Path(ChaosMapState map)
    {
        var start=map.SpawnPositions[0];var queue=new Queue<MapPosition>();queue.Enqueue(start);var previous=new Dictionary<MapPosition,MapPosition?>{{start,null}};
        while(queue.TryDequeue(out var current))
        {
            if(current==map.BossPosition){var path=new List<MapPosition>();for(MapPosition? p=current;p is {} position;p=previous[position])path.Add(position);path.Reverse();return path.ToArray();}
            foreach(var next in map.GetNeighbors(current).Where(next=>map.CanMove(current,next)))if(previous.TryAdd(next,current))queue.Enqueue(next);
        }
        throw new InvalidOperationException("Original generated map has no legal inward Boss path.");
    }
    private static CombatCardInstance[] Instances(RoomPlayerState player)=>player.Combat.Deck.Hand.Concat(player.Combat.Deck.Library).Concat(player.Combat.Deck.Discard).ToArray();
    private static string[] Deck(HeroClass hero)=>Core.Concat(new[]{hero==HeroClass.Mage?"MAG-09":hero==HeroClass.Priest?"PRI-09":"GUA-09",hero==HeroClass.Mage?"MAG-10":hero==HeroClass.Priest?"PRI-10":"GUA-10"}).Concat(Tail).ToArray();
    private static ExplorationItem[] Armor(int difficulty)=>Slots.Select((slot,i)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,Equipment:new(slot,difficulty==0?"Blue":difficulty==1?"Purple":i==0?"Orange":"Purple",i<3?"Fire":"Metal",difficulty==0?null:i<2?"Piercing":"Vitality","DrawInterval",3,StatsVersion:"season-equipment-v1"),IsGenerated:false)).ToArray();
    private static CardElement Counter(CardElement target)=>target switch{CardElement.None=>CardElement.None,CardElement.Fire=>CardElement.Water,CardElement.Wood=>CardElement.Metal,CardElement.Earth=>CardElement.Wood,CardElement.Metal=>CardElement.Fire,_=>CardElement.Earth};
    private static CombatCardInstance[] Choose(BattleRoom room,RoomPlayerState player,MonsterCombatState target,CombatCardCatalog catalog,out int previews)
    {
        var before=JsonSerializer.Serialize(room.Capture());var hand=player.Combat.Deck.Hand;var phase=target.ThemeProfile is {} profile?(target.BossPhase==1?profile.PhaseOnePrimary:profile.PhaseTwoPrimary):target.Intents.FirstOrDefault(x=>x.Element!=CardElement.None)?.Element??CardElement.None;var preferred=Counter(phase);
        var atRisk=player.Combat.Hp+player.Combat.Shield<player.Combat.EffectiveMaximumHp*.60;var current=target.Intents[target.IntentIndex];var visible=MonsterCombatState.PublishedIntentValue(target.Capture());var interruption=current.Kind is MonsterIntentKind.Shield or MonsterIntentKind.Regenerate?visible:visible*(atRisk?1.2:.2);
        double Value(int damage,int heal,int shield,int draws,double charge,double stun,int cost,int count,double speedModifier,double speedSeconds)
        {
            var value=Math.Min(damage,target.Hp+target.Shield)+Math.Min(heal,Math.Max(0,player.Combat.EffectiveMaximumHp-player.Combat.Hp))*(atRisk?2:.2)+Math.Min(shield,Math.Max(0,player.Combat.MaximumHp/2-player.Combat.Shield))*(atRisk?1:.1)+Math.Min(5-hand.Count+count,draws+Math.Min(1,charge))*6-count*1.25-cost*(atRisk?3:.5);
            if(speedSeconds>0&&speedModifier<0){var projected=Math.Clamp(player.Combat.NaturalDrawIntervalSeconds*(1+speedModifier),player.Combat.Equipment.MinimumDrawInterval??1.8,player.Combat.Equipment.MaximumDrawInterval??6);value+=Math.Max(0,1/projected-1/player.Combat.DrawIntervalSeconds)*Math.Min(15,speedSeconds)*12;}
            if(target.WindupRemaining>TimeSpan.Zero&&target.StunRemaining<=TimeSpan.Zero&&stun>0)value+=interruption;if(cost>=player.Combat.Hp)value-=10000;return value;
        }
        var candidates=new List<(CombatCardInstance[] Cards,double Score)>();
        for(var mask=1;mask<(1<<hand.Count);mask++)
        {
            var cards=hand.Where((_,i)=>(mask&(1<<i))!=0).OrderByDescending(x=>catalog.Get(x.CardId,x.Level,x.ElementOverride).Effect.Element==preferred).ThenBy(x=>x.CardId,StringComparer.Ordinal).ToArray();var draft=CombatResolver.Resolve(cards.Select(x=>catalog.Get(x.CardId,x.Level,x.ElementOverride)).ToArray(),player.Combat,target.ElementalResistance);
            candidates.Add((cards,Value(draft.Damage,draft.Heal,draft.Shield,draft.ImmediateDraw,draft.DrawCharge,draft.Stun.TotalSeconds,draft.HealthCost,cards.Length,draft.DrawSpeedModifier,draft.DrawSpeedDuration.TotalSeconds)));
        }
        var best=Array.Empty<CombatCardInstance>();var bestValue=double.NegativeInfinity;previews=0;
        foreach(var candidate in candidates.OrderByDescending(x=>x.Score).Take(3))
        {
            var preview=room.PreviewCards(player.PlayerId,player.Pve!.BattleId,target.MonsterId,candidate.Cards.Select(x=>x.InstanceId).ToArray(),room.Revision,Epoch+room.Elapsed);previews++;var value=Value(preview.HpDamage+preview.ShieldDamage,preview.Heal,preview.ShieldGain,preview.ImmediateDraw,preview.DrawCharge,preview.StunSeconds,preview.HealthCost,candidate.Cards.Length,preview.DrawSpeedModifier,preview.DrawSpeedSeconds);if(value>bestValue){bestValue=value;best=candidate.Cards;}
        }
        Assert.Equal(before,JsonSerializer.Serialize(room.Capture()));return bestValue<-1000?[]:best;
    }
}
