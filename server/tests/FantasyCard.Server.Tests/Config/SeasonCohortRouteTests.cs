using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>D03 independently seeded D2-entry cohort attempts; economic stream pilot, not a population acceptance claim.</summary>
public sealed class SeasonCohortRouteTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_COHORTS")=="1";
    private static readonly string[] Slots=["Head","Hands","Chest","Legs","Feet"];
    private static readonly TimeSpan Tick=TimeSpan.FromMilliseconds(100);
    private static readonly DateTimeOffset Epoch=new(2026,11,20,0,0,0,TimeSpan.Zero);
    internal sealed record Scenario(string Id,string Hero,string Cohort,int Seed,int Difficulty=2,string Route="R1",bool EarlyExtract=false,bool AdaptiveEquipment=false);

    private static Scenario[] Plan()
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_COHORT_PLAN")??throw new InvalidOperationException("Frozen route plan required.")));
        var prior=document.RootElement.GetProperty("prior_used").GetInt32();
        var rows=document.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Scenario(x.GetProperty("id").GetString()!,x.GetProperty("hero").GetString()!,x.GetProperty("cohort").GetString()!,x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows){Assert.True(Enum.TryParse<HeroClass>(row.Hero,out var hero)&&Enum.IsDefined(hero));Assert.True(row.Cohort is "novice" or "returning" or "skilled");}
        return rows;
    }

    [Fact(Skip="Requires explicit frozen D03 natural-route inputs; no encounter clock.",SkipUnless=nameof(Enabled))]
    public void CohortInputsAndOriginalR1GeometryAreLegal()
    {
        var config=GameConfigCatalog.Current;var rows=Plan();
        foreach(var row in rows)
        {
            var hero=Enum.Parse<HeroClass>(row.Hero);DeckRules.Validate(hero,Deck(hero,row.Cohort),config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            SeasonLootRules.RequireEntry(new("d03-cohorts",2,"season-v1",config.Version,"season-equipment-v1"),Armor().Select(x=>x.Equipment!),config);
            var map=ChaosMapGenerator.Generate(row.Seed,1,config.SeasonThemes);var route=Path(map);
            Assert.Equal(map.SpawnPositions[0],route[0]);Assert.Equal(map.BossPosition,route[^1]);
            Assert.All(route.Zip(route.Skip(1)),pair=>Assert.True(map.CanMove(pair.First,pair.Second)&&pair.First.ManhattanDistance(pair.Second)==1));
        }
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_COHORT_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New proof output required."),JsonSerializer.Serialize(new {cases=rows.Length,config.Version,config.ContentHash,map_edits=false,new_timed_routes=0}));
    }

    [Fact(Skip="Budgeted current routes; no completed B05 or other matrix replay.",SkipUnless=nameof(Enabled))]
    public void CohortR1AttemptsRecordUnforcedOutcomesAndThreeLedgerInputs()
    {
        var rows=Plan();var directory=Environment.GetEnvironmentVariable("FANTASYCARD_D03_COHORT_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        using var attempts=new StreamWriter(System.IO.Path.Combine(directory,"attempts.original.jsonl"));using var trace=new StreamWriter(System.IO.Path.Combine(directory,"events.original.jsonl"));using var results=new StreamWriter(System.IO.Path.Combine(directory,"routes.original.jsonl"));
        foreach(var row in rows){attempts.WriteLine(JsonSerializer.Serialize(row));attempts.Flush();Run(row,trace,results);trace.Flush();results.Flush();}
    }

    internal static BattleRoomSnapshot Run(Scenario scenario,StreamWriter trace,StreamWriter results,IReadOnlyList<ExplorationItem>? ownedArmor=null)
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var hero=Enum.Parse<HeroClass>(scenario.Hero);var id=Guid.NewGuid();
        var context=new SeasonContext("d03-cohorts",scenario.Difficulty,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,scenario.Seed,season:context);
        var startingCards=Deck(hero,scenario.Cohort);var player=room.AddPlayer(new(id,hero,startingCards,null,WeaponLevel:Math.Min(scenario.Cohort=="novice"?2:5,scenario.Difficulty),WornArmor:ownedArmor??Armor(),CardLevels:Enumerable.Repeat(Math.Min(scenario.Cohort=="novice"?2:5,scenario.Difficulty),20).ToArray()));
        var originalArmor=player.WornArmor.ToArray();var choiceRandom=new Random(scenario.Seed^0x43484f49);var lastAction=TimeSpan.FromSeconds(-1);var reaction=TimeSpan.FromSeconds(scenario.Cohort=="novice"?1:scenario.Cohort=="returning"?.7:.5);
        var map=ChaosMapGenerator.Generate(scenario.Seed,1,config.SeasonThemes);var mapOriginal=JsonSerializer.Serialize(map.Capture());var path=Path(map,scenario.Route);room.InitializeMap(map);
        var originalIds=Instances(player).Select(x=>x.InstanceId).ToHashSet();var pathIndex=0;var casts=0;var kills=0;var clears=0;var potions=0;var springs=0;var redRolls=0;
        var recoveredAction=false;var recoveredExtraction=false;var extracting=false;DateTimeOffset? expectedExtraction=null;
        var open=false;var monsters=Array.Empty<MonsterCombatState>();var previous=new Dictionary<string,(int Hp,int Shield)>(StringComparer.Ordinal);
        var initialHp=0;var initialShield=0;long hpAdded=0,shieldAdded=0,hpOtherLoss=0,shieldDiscarded=0,damage=0,totalDamage=0;
        trace.WriteLine(JsonSerializer.Serialize(new {kind="start",scenario,config.Version,config.ContentHash,context,path,map=map.Capture(),player=room.CapturePlayer(id),permanent_card_weapon_assumption=scenario.Cohort=="novice"?2:5,actual_effective_level=Math.Min(scenario.Cohort=="novice"?2:5,scenario.Difficulty),quota_fixture="Only if a real red roll hits, assume that logical server's weekly quota was already spent; do not mint or claim PostgreSQL verification."}));trace.Flush();
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
                var choices=room.GetRewardChoice(id);var equipment=choices.Options.Single(x=>x.Kind==RewardChoiceKind.Equipment);var offered=equipment.Item!.Equipment!;var wantGear=scenario.Cohort=="novice"||scenario.Cohort=="returning"&&choiceRandom.NextDouble()<.75||scenario.Cohort=="skilled"&&SeasonLootConfig.Rank(offered.Quality)>=3&&!player.Inventory.Items.Any(x=>x.Equipment is {} e&&e.Slot==offered.Slot&&SeasonLootConfig.Rank(e.Quality)>=SeasonLootConfig.Rank(offered.Quality));
                var previousSlot=player.WornArmor.FirstOrDefault(x=>x.Equipment!.Slot==offered.Slot);var better=previousSlot is null||SeasonLootConfig.Rank(offered.Quality)>SeasonLootConfig.Rank(previousSlot.Equipment!.Quality)||offered.Quality==previousSlot.Equipment!.Quality&&offered.Level>previousSlot.Equipment.Level;
                var salvageNeed=scenario.AdaptiveEquipment&&scenario.Difficulty<=1&&better&&!player.Inventory.Items.Any(x=>x.Equipment is {} e&&e.Slot==offered.Slot&&SeasonLootConfig.Rank(e.Quality)>=SeasonLootConfig.Rank(offered.Quality));wantGear|=salvageNeed;
                var selected=player.Combat.Hp<=player.Combat.MaximumHp*.60?choices.Options.Single(x=>x.Kind==RewardChoiceKind.ImmediateHeal):wantGear?equipment:choices.Options.Single(x=>x.Kind==RewardChoiceKind.EquipmentFragments);
                var equip=scenario.AdaptiveEquipment&&better&&selected.Kind==RewardChoiceKind.Equipment&&(SeasonLootConfig.Rank(offered.Quality)<4||!player.WornArmor.Any(x=>x.Equipment!.Slot!=offered.Slot&&SeasonLootConfig.Rank(x.Equipment.Quality)>=4));
                var hpBefore=player.Combat.Hp;var applied=room.ClaimReward(id,selected.OptionId,equip:equip);trace.WriteLine(JsonSerializer.Serialize(new {kind="reward",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,choices,selected,applied,equipped=equip,salvageNeed,hpBefore,hpAfter=player.Combat.Hp,inventory=player.Inventory.Capture()}));continue;
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
                if(pathIndex+1<path.Length&&!(scenario.EarlyExtract&&map.GetCell(player.Position!.Value).HasEvacuation))
                {
                    var from=player.Position!.Value;var to=path[++pathIndex];Assert.True(map.CanMove(from,to)&&from.ManhattanDistance(to)==1);
                    var moved=room.MovePlayerAndPair(id,to,room.Revision,Epoch+room.Elapsed);Assert.Null(moved.StartedDuel);Assert.Equal(to,player.Position);
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="move",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,from,to}));Begin();continue;
                }
                var requestedAt=Epoch+room.Elapsed;var duration=room.RequestExtraction(id);expectedExtraction=requestedAt+duration;extracting=true;Step();Recover("ExtractionReading");recoveredExtraction=true;
                trace.WriteLine(JsonSerializer.Serialize(new {kind="extraction-reading",scenario.Id,requestedAt,duration,expectedExtraction,remaining=room.CapturePlayer(id).ExtractionRemaining}));continue;
            }
            if(player.Phase==RoomPlayerPhase.Pve&&player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(id).RemainingMs==0&&room.Elapsed-lastAction>=reaction&&player.Combat.Deck.Hand.Count>0)
            {
                var target=monsters.Where(x=>!x.IsDead).OrderBy(x=>x.Hp+x.Shield).First();var chosen=SeasonClassEfficiencyPilotTests.Choose(room,player,target,catalog,startingCards,out var previews,out var candidates);
                if(chosen.Length>0)
                {
                    var beforeIds=Instances(player).Select(x=>x.InstanceId).ToHashSet();var ids=chosen.Select(x=>x.InstanceId).ToArray();var hpBefore=player.Combat.Hp;var battle=player.Pve!.BattleId;
                    var resolution=room.PlayCards(id,battle,target.MonsterId,ids,room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(id));lastAction=room.Elapsed;casts++;damage+=resolution.HpDamage+resolution.ShieldDamage;Observe("cast",resolution,target.MonsterId);
                    var added=Instances(player).Where(x=>!beforeIds.Contains(x.InstanceId)).ToArray();if(resolution.TargetDefeated){kills++;var card=Assert.Single(added);Assert.StartsWith("M-",card.CardId);Assert.Equal(0,card.Level);Assert.Contains(card,player.Combat.Deck.Discard);}else Assert.Empty(added);
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="cast",scenario.Id,pathIndex,seconds=room.Elapsed.TotalSeconds,selected=chosen.Select(x=>new{x.CardId,x.Level}),resolution,previews,candidates,added,hpBefore,hpAfter=player.Combat.Hp,shieldAfter=player.Combat.Shield}));
                    if(!recoveredAction){Recover("FirstAcceptedAction",resolution,ids);recoveredAction=true;}
                }
            }
            Step();
        }
        var outcome=player.Phase==RoomPlayerPhase.Extracted?"Extracted":player.Phase==RoomPlayerPhase.Dead?"Dead":"Timeout";if(open)Finish(outcome);
        Assert.Equal(mapOriginal,JsonSerializer.Serialize(room.Map!.Capture()));
        if(outcome=="Extracted"){Assert.Equal(pathIndex+1,clears);Assert.True(recoveredAction&&recoveredExtraction);Assert.Equal(expectedExtraction,player.ExtractionCompletedAt);Assert.True(map.GetCell(player.Position!.Value).HasEvacuation||map.GetCell(player.Position.Value).IsBoss);if(!scenario.EarlyExtract)Assert.Equal(path[^1],player.Position);}
        var playerSnapshot=room.CapturePlayer(id);var ownCleared=room.Map!.Cells.Where(x=>playerSnapshot.ClearedCells!.Contains(x.Position));var marks=outcome=="Extracted"?config.SeasonCrafting!.Pending(scenario.Difficulty,false,ownCleared):new PendingBlueprints();
        var resultRow=new {scenario,outcome,seconds=room.Elapsed.TotalSeconds,casts,kills,clears,pathIndex,totalDamage,potions,springs,redRolls,recoveredAction,recoveredExtraction,expectedExtraction,original_map_unchanged=true,marks,realizedGold=outcome=="Extracted"?player.Inventory.Items.Where(x=>x.Kind==ExplorationItemKind.Gold).Sum(x=>x.Quantity):0,realizedFragments=outcome=="Extracted"?player.Inventory.Items.Where(x=>x.Kind==ExplorationItemKind.EquipmentFragments).Sum(x=>x.Quantity):0,lostBlueBodies=outcome=="Dead"?originalArmor.Count(x=>x.Equipment!.Quality=="Blue"):0,lostEnhancementInvestment=outcome=="Dead"?originalArmor.Sum(x=>Enumerable.Range(1,x.Equipment!.Level).Sum(level=>config.EquipmentQuality(x.Equipment.Quality,"season-equipment-v1").EnhancementCost(level))):0,not_long_run_or_first_set_quantiles=true,snapshot=room.Capture()};trace.WriteLine(JsonSerializer.Serialize(new {kind="end",result=resultRow}));results.WriteLine(JsonSerializer.Serialize(resultRow));return room.Capture();
    }

    private static readonly MapPosition[] R1=[new(0,0),new(0,1),new(0,2),new(0,3),new(0,4),new(1,4),new(2,4),new(2,3)];
    private static MapPosition[] Path(ChaosMapState map,string route="R1")
    {
        if(route=="R1"){Assert.Equal(R1[0],map.SpawnPositions[0]);Assert.Equal(R1[^1],map.BossPosition);return R1;}
        Assert.Equal("natural-shortest",route);var start=map.SpawnPositions[0];var queue=new Queue<MapPosition>();queue.Enqueue(start);var previous=new Dictionary<MapPosition,MapPosition?>{{start,null}};
        while(queue.TryDequeue(out var current))
        {
            if(current==map.BossPosition){var path=new List<MapPosition>();for(MapPosition? p=current;p is {} pos;p=previous[pos])path.Add(pos);path.Reverse();return path.ToArray();}
            foreach(var next in map.GetNeighbors(current).Where(next=>map.CanMove(current,next)))if(previous.TryAdd(next,current))queue.Enqueue(next);
        }
        throw new InvalidOperationException("Original generated map has no legal Boss path.");
    }
    private static CombatCardInstance[] Instances(RoomPlayerState player)=>player.Combat.Deck.Hand.Concat(player.Combat.Deck.Library).Concat(player.Combat.Deck.Discard).ToArray();
    private static string[] Deck(HeroClass hero,string cohort)=>cohort=="novice"?GameConfigCatalog.Current.BorrowedDeck(hero).CardIds.ToArray():SeasonClassEfficiencyPilotTests.Deck(hero,"counter-tempo");
    private static ExplorationItem[] Armor()=>Slots.Select((slot,i)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,Equipment:new(slot,"Blue",i<3?"Water":"Fire",null,"DrawInterval",1,StatsVersion:"season-equipment-v1"),IsGenerated:false)).ToArray();
}
