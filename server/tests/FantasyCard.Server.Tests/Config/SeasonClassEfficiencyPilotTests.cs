using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>D03 development-only efficiency candidates; real resolver/clock and public-state tempo forecasts.</summary>
public sealed class SeasonClassEfficiencyPilotTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_EFFICIENCY")=="1";
    private static readonly string[] Core=["GP15","GP16","GP17","GB19","GB20","GB23","GP20","GP21","GP22","ET-WATER-P","ET-WOOD-P","GO03","GP18","GP23"];
    private static readonly string[] Tail=["GP13","GP19","GP10","GP02"];
    private static readonly string[] Slots=["Head","Hands","Chest","Legs","Feet"];
    private static readonly string[] CounterCore=["GP20","GP21","GP22","GP18","GO04"];
    private static readonly string[] UniversalSupport=["GP19","GP23"];
    private static readonly string[] FlowCore=["GP20","GP21","GP22","GP24","GO04","GP18","ET-WATER-P","ET-WATER-B","GB29"];
    private static readonly string[] FlowLoop=["GP25","GB34","GB35","ET-WATER-G"];
    private static readonly DateTimeOffset Epoch=new(2026,11,20,0,0,0,TimeSpan.Zero);
    private sealed record Scenario(string Id,string Hero,string Deck,string Armor,int Seed,string Policy="published");

    private static Scenario[] Plan()
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_PLAN")??throw new InvalidOperationException("Frozen D03 plan required.")));
        var prior=document.RootElement.GetProperty("prior_used").GetInt32();var rows=document.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Scenario(x.GetProperty("id").GetString()!,x.GetProperty("hero").GetString()!,x.GetProperty("deck").GetString()!,x.GetProperty("armor").GetString()!,x.GetProperty("seed").GetInt32(),x.TryGetProperty("policy",out var p)?p.GetString()!:"published")).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows){Assert.True(Enum.TryParse<HeroClass>(row.Hero,out var h)&&Enum.IsDefined(h));Assert.True(row.Deck is "reference" or "tempo" or "counter-tempo" or "universal-tempo" or "flow-counter" or "flow-loop" or "flow-paired" or "flow-offense");Assert.True(row.Armor is "balanced" or "offense" or "counter-offense");Assert.True(row.Policy is "published" or "rate-budget-v1" or "rate-budget-half-v1" or "rate-budget-half-card10-v1");}
        return rows;
    }

    [Fact(Skip="Frozen D03 development candidates, no timed encounters.",SkipUnless=nameof(Enabled))]
    public void CandidateInputsAreLegalAndBothSpeedLayersAreValued()
    {
        var config=GameConfigCatalog.Current;var rows=Plan();
        if(rows.Any(row=>row.Policy=="rate-budget-half-card10-v1"))_=SeasonMageCardCandidate.Current;
        foreach(var row in rows)
        {
            var hero=Enum.Parse<HeroClass>(row.Hero);var cards=Deck(hero,row.Deck);DeckRules.Validate(hero,cards,config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            var armor=Armor(row.Armor);Assert.All(armor,x=>Assert.True(EquipmentRewardRules.IsValid(x.Equipment!)));Assert.All(armor,x=>Assert.Equal(3,x.Equipment!.Level));Assert.Equal(1,armor.Count(x=>x.Equipment!.Quality=="Orange"));
            SeasonLootRules.RequireEntry(new("d03-pilot",5,"season-v1",config.Version,"season-equipment-v1"),armor.Select(x=>x.Equipment!),config);
            if(row.Deck=="flow-paired")
            {
                Assert.True(cards.Count(id=>config.Cards.Single(c=>c.CardId==id).Effect is {Element:CardElement.Fire,ElementalDamage:>0})>=2);
                Assert.True(cards.Count(id=>config.Cards.Single(c=>c.CardId==id).Effect is {Element:CardElement.Water,ElementalDamage:>0})>=2);
            }
        }
        var state=new PlayerCombatState(HeroClass.Mage,Deck(HeroClass.Mage,"reference"),new Random(1));
        Assert.Equal(Deck(HeroClass.Mage,"flow-loop"),Deck(HeroClass.Mage,"flow-offense"));
        Assert.Equal(3,FutureDraws(state,0,0,0,12),8);Assert.Equal(4.5,FutureDraws(state,0,0,6,12),8);Assert.Equal(8,FutureDraws(state,-.5,12,4,12),8);
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New proof path required."),JsonSerializer.Serialize(new {cases=rows.Length,config.Version,config.ContentHash,new_encounters=0,forecast_horizon_seconds=12,not_an_acceptance_result=true}));
    }

    [Fact(Skip="D03 exploratory development roster only, not population or final acceptance.",SkipUnless=nameof(Enabled))]
    public void DeclaredCandidatesRecordActualBossOutcomesWithoutChangingAnyGameRules()
    {
        var rows=Plan();var root=Environment.GetEnvironmentVariable("FANTASYCARD_D03_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(root));Directory.CreateDirectory(root);
        using var attempts=new StreamWriter(Path.Combine(root,"attempts.original.jsonl"));using var trace=new StreamWriter(Path.Combine(root,"events.original.jsonl"));using var results=new StreamWriter(Path.Combine(root,"encounters.original.jsonl"));
        foreach(var row in rows){attempts.WriteLine(JsonSerializer.Serialize(row));attempts.Flush();Run(row,trace,results);trace.Flush();results.Flush();}
    }

    private static void Run(Scenario row,StreamWriter trace,StreamWriter results)
    {
        var config=row.Policy=="rate-budget-half-card10-v1"?SeasonMageCardCandidate.Current:GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var hero=Enum.Parse<HeroClass>(row.Hero);var cards=Deck(hero,row.Deck);var gear=Armor(row.Armor);var context=new SeasonContext("d03-pilot",5,"season-v1",config.Version,"season-equipment-v1");
        var policy=row.Policy is "rate-budget-half-v1" or "rate-budget-half-card10-v1"?NumericalRules.SeasonV1 with {SeasonMageSustainBudget=true,SeasonMageReturnRateBasisPoints=500}:row.Policy=="rate-budget-v1"?NumericalRules.SeasonV1 with {SeasonMageSustainBudget=true}:NumericalRules.SeasonV1;
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,row.Seed,numerics:policy,season:context);var id=Guid.NewGuid();var player=room.AddPlayer(new(id,hero,cards,null,WeaponLevel:5,WornArmor:gear,CardLevels:Enumerable.Repeat(5,20).ToArray()));
        var map=ChaosMapGenerator.Generate(row.Seed,1,config.SeasonThemes).Capture();var boss=map.Cells.Single(x=>x.IsBoss);room.InitializeMap(ChaosMapState.Restore(map with {SpawnPositions=[boss.Position]}));
        var target=Assert.Single(player.Pve!.Monsters);var initial=target.Capture();var previous=(target.Hp,target.Shield);long addedHp=0,addedShield=0,otherHpLoss=0,discardedShield=0,damage=0;var casts=0;var previews=0;var last=TimeSpan.FromMilliseconds(-500);
        trace.WriteLine(JsonSerializer.Serialize(new {kind="start",row,config.Version,config.ContentHash,context,cards,gear,initial,player=room.CapturePlayer(id),scope="Independent original Boss development encounter, not legal route/settlement/population evidence."}));trace.Flush();
        void Observe(string reason,CombatResolution? result=null)
        {
            var hp=target.Hp-previous.Hp+(result?.HpDamage??0);var shield=target.Shield-previous.Shield+(result?.ShieldDamage??0);addedHp+=Math.Max(0,hp);addedShield+=Math.Max(0,shield);otherHpLoss+=Math.Max(0,-hp);discardedShield+=Math.Max(0,-shield);
            if(hp!=0||shield!=0)trace.WriteLine(JsonSerializer.Serialize(new {kind="resource",row.Id,seconds=room.Elapsed.TotalSeconds,reason,hpBefore=previous.Hp,hpAfter=target.Hp,shieldBefore=previous.Shield,shieldAfter=target.Shield,hpDamage=result?.HpDamage??0,shieldDamage=result?.ShieldDamage??0,hpDelta=hp,shieldDelta=shield}));previous=(target.Hp,target.Shield);
        }
        while(room.Elapsed.TotalSeconds<600&&player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Choice))
        {
            Assert.InRange(player.Combat.Hp,0,player.Combat.EffectiveMaximumHp);Assert.InRange(player.Combat.Shield,0,player.Combat.MaximumHp/2);Assert.InRange(player.Combat.Deck.Hand.Count,0,5);
            if(player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(id).RemainingMs==0&&player.Combat.Deck.Hand.Count>0)
            {
                var chosen=Choose(room,player,target,catalog,cards,out var used,out var candidates,valueSustainIntents:row.Deck is "flow-counter" or "flow-loop" or "flow-paired" or "flow-offense");previews+=used;
                if(chosen.Length>0)
                {
                    var hpBefore=player.Combat.Hp;var result=room.PlayCards(id,player.Pve!.BattleId,target.MonsterId,chosen.Select(x=>x.InstanceId).ToArray(),room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(id));
                    Assert.True(room.Elapsed-last>=TimeSpan.FromMilliseconds(500));last=room.Elapsed;casts++;damage+=result.HpDamage+result.ShieldDamage;Observe("cast",result);
                    trace.WriteLine(JsonSerializer.Serialize(new {kind="cast",row.Id,seconds=room.Elapsed.TotalSeconds,selected=chosen.Select(x=>new{x.CardId,x.Level}),result,previews=used,candidates,hpBefore,hpAfter=player.Combat.Hp,shield=player.Combat.Shield,naturalInterval=player.Combat.NaturalDrawIntervalSeconds,actualInterval=player.Combat.DrawIntervalSeconds,blockSpeedRemaining=player.Combat.DrawBlockSpeedRemaining.TotalSeconds}));
                }
            }
            room.Advance(TimeSpan.FromMilliseconds(100),Epoch+room.Elapsed+TimeSpan.FromMilliseconds(100));Observe("tick");
        }
        Assert.Equal(damage,(long)initial.Hp+initial.Shield+addedHp+addedShield-otherHpLoss-discardedShield-target.Hp-target.Shield);
        var resultRow=new {row,outcome=player.Phase==RoomPlayerPhase.Choice?"Win":player.Phase==RoomPlayerPhase.Dead?"Dead":"Timeout",seconds=room.Elapsed.TotalSeconds,casts,previews,damage,initialHp=initial.Hp,initialShield=initial.Shield,addedHp,addedShield,otherHpLoss,discardedShield,remainingHp=target.Hp,remainingShield=target.Shield,endingHp=player.Combat.Hp};trace.WriteLine(JsonSerializer.Serialize(new {kind="end",result=resultRow}));results.WriteLine(JsonSerializer.Serialize(resultRow));
    }

    internal static CombatCardInstance[] Choose(BattleRoom room,RoomPlayerState player,MonsterCombatState target,CombatCardCatalog catalog,string[] baseDeck,out int previews,out int candidateCount,bool valueSustainIntents=false,DateTimeOffset? observedAtUtc=null)
    {
        var before=JsonSerializer.Serialize(room.Capture());var hand=player.Combat.Deck.Hand;
        var scratch=new PlayerCombatState(player.HeroClass,baseDeck,new Random(1),player.Combat.WeaponLevel,player.Combat.Equipment,Enumerable.Repeat(5,20).ToArray());
        // Forecast helpers need visible counters only; keep a separate dummy deck/RNG.
        var dummy=scratch.Capture();var snapshot=player.Combat.Capture() with {Deck=dummy.Deck,RandomState=dummy.RandomState};
        var currentFuture=FutureDraws(player.Combat,player.Combat.DrawSpeedModifier,player.Combat.DrawSpeedRemaining.TotalSeconds,player.Combat.DrawBlockSpeedRemaining.TotalSeconds,12);
        double Value(int hit,int heal,int shield,int draws,double charge,double stun,int cost,int spent,double speed,double duration,double blockDuration)
        {
            var atRisk=player.Combat.Hp+player.Combat.Shield<player.Combat.EffectiveMaximumHp*.60;
            scratch.Restore(snapshot);scratch.ApplyDrawSpeed(TimeSpan.FromSeconds(duration),speed);scratch.ApplyDrawBlockSpeed(TimeSpan.FromSeconds(blockDuration));
            var future=FutureDraws(scratch,scratch.DrawSpeedModifier,scratch.DrawSpeedRemaining.TotalSeconds,scratch.DrawBlockSpeedRemaining.TotalSeconds,12)-currentFuture;
            var returns=Math.Min(5-hand.Count+spent,draws+Math.Floor(player.Combat.Deck.DrawCharge+charge));
            var value=Math.Min(hit,target.Hp+target.Shield)+Math.Min(heal,Math.Max(0,player.Combat.EffectiveMaximumHp-player.Combat.Hp))*(atRisk?2:.2)+Math.Min(shield,Math.Max(0,player.Combat.MaximumHp/2-player.Combat.Shield))*(atRisk?1:.1)+returns*6+future*12-spent*1.25-cost*(atRisk?3:.5);
            if(target.WindupRemaining>TimeSpan.Zero&&target.StunRemaining<=TimeSpan.Zero&&stun>0)
            {
                var sustain=valueSustainIntents&&target.Intents[target.IntentIndex].Kind is MonsterIntentKind.Shield or MonsterIntentKind.Regenerate;
                value+=MonsterCombatState.PublishedIntentValue(target.Capture())*(sustain?1:atRisk?1.2:.2);
            }
            if(cost>=player.Combat.Hp)value-=10000;return value;
        }
        var candidates=new List<(CombatCardInstance[] Cards,double Score)>();
        for(var mask=1;mask<(1<<hand.Count);mask++)
        {
            var subset=hand.Where((_,i)=>(mask&(1<<i))!=0).ToArray();var orders=new List<CombatCardInstance[]>{subset};
            foreach(var core in subset.Where(c=>{var e=catalog.Get(c.CardId,c.Level,c.ElementOverride).Effect;return e.ElementalDamage>0&&e.Element!=CardElement.None&&e.SecondaryElementalDamage==0;}).GroupBy(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride).Effect.Element))
            {
                var first=core.First();if(first.InstanceId!=subset[0].InstanceId)orders.Add(new[]{first}.Concat(subset.Where(x=>x.InstanceId!=first.InstanceId)).ToArray());
            }
            foreach(var cards in orders)
            {
                var draft=CombatResolver.Resolve(cards.Select(x=>catalog.Get(x.CardId,x.Level,x.ElementOverride)).ToArray(),player.Combat,target.ElementalResistance);scratch.Restore(snapshot);var passive=scratch.UpdateFenxian(draft.CoreElement,draft.CoreCount,cards.Length);
                var block=player.Combat.ResolveControl(TimeSpan.FromSeconds(cards.Max(x=>catalog.Get(x.CardId,x.Level,x.ElementOverride).Effect.DrawBlockSeconds)/2)).TotalSeconds;
                candidates.Add((cards,Value(draft.Damage,draft.Heal,draft.Shield,draft.ImmediateDraw+passive.Draw,draft.DrawCharge+passive.Charge,draft.Stun.TotalSeconds,draft.HealthCost,cards.Length,draft.DrawSpeedModifier,draft.DrawSpeedDuration.TotalSeconds,block)));
            }
        }
        candidateCount=candidates.Count;var best=Array.Empty<CombatCardInstance>();var bestValue=double.NegativeInfinity;previews=0;
        foreach(var candidate in candidates.OrderByDescending(x=>x.Score).Take(3))
        {
            var preview=room.PreviewCards(player.PlayerId,player.Pve!.BattleId,target.MonsterId,candidate.Cards.Select(x=>x.InstanceId).ToArray(),room.Revision,observedAtUtc??Epoch+room.Elapsed);previews++;
            var score=Value(preview.HpDamage+preview.ShieldDamage,preview.Heal,preview.ShieldGain,preview.ImmediateDraw,preview.DrawCharge,preview.StunSeconds,preview.HealthCost,candidate.Cards.Length,preview.DrawSpeedModifier,preview.DrawSpeedSeconds,preview.DrawBlockSpeedSeconds);
            if(score>bestValue){bestValue=score;best=candidate.Cards;}
        }
        Assert.Equal(before,JsonSerializer.Serialize(room.Capture()));return bestValue<-1000?[]:best;
    }

    private static double FutureDraws(PlayerCombatState state,double speed,double speedRemaining,double blockRemaining,double horizon)
    {
        var boundaries=new[]{0d,Math.Clamp(speedRemaining,0,horizon),Math.Clamp(blockRemaining,0,horizon),horizon}.Distinct().Order().ToArray();var total=0d;
        for(var i=0;i+1<boundaries.Length;i++)
        {
            var t=boundaries[i];var interval=Math.Clamp(4*(1+state.Equipment.DrawIntervalModifier)*(1+(t<speedRemaining?speed:0)),state.Equipment.MinimumDrawInterval??1.8,state.Equipment.MaximumDrawInterval??6);total+=(boundaries[i+1]-t)/interval*(t<blockRemaining?2:1);
        }
        return total;
    }
    internal static string[] Deck(HeroClass hero,string variant)
    {
        var classCards=new[]{hero==HeroClass.Mage?"MAG-09":hero==HeroClass.Priest?"PRI-09":"GUA-09",hero==HeroClass.Mage?"MAG-10":hero==HeroClass.Priest?"PRI-10":"GUA-10"};
        if(variant is "reference" or "tempo")return Core.Select(x=>x=="GO03"&&variant=="tempo"?"GO04":x).Concat(classCards).Concat(Tail).ToArray();
        var available=GameConfigCatalog.Current.Cards.Where(x=>x.Enabled&&x.IsCodex&&(x.HeroClass is null||x.HeroClass==hero)&&x.Rarity!=(short)CardRarity.Orange).ToArray();
        var water=available.Where(x=>x.Effect.Element==CardElement.Water&&x.Effect.ElementalDamage>0).OrderByDescending(x=>x.Rarity).ThenByDescending(x=>x.Effect.ElementalDamage+3*x.Effect.ImmediateDraw+2*x.Effect.DrawCharge).ThenBy(x=>x.CardId,StringComparer.Ordinal).Take(6).Select(x=>x.CardId);
        var fire=available.Where(x=>x.Effect.Element==CardElement.Fire&&x.Effect.ElementalDamage>0).OrderByDescending(x=>x.Rarity).ThenByDescending(x=>x.Effect.ElementalDamage+3*x.Effect.ImmediateDraw+2*x.Effect.DrawCharge).ThenBy(x=>x.CardId,StringComparer.Ordinal).Take(6).Select(x=>x.CardId);
        if(variant is "flow-counter" or "flow-loop" or "flow-paired" or "flow-offense")
        {
            // Reserve both counter elements before the twenty-card cut, rather than exhausting every water candidate first.
            var damage=variant=="flow-paired"?water.Zip(fire).SelectMany(pair=>new[]{pair.First,pair.Second}):water.Concat(fire);
            // Solo offense can spend utility-only class slots on damage; the Mage's strongest known recipe remains identical.
            var requestedClass=variant=="flow-offense"?hero==HeroClass.Mage?classCards:hero==HeroClass.Priest?classCards.Take(1):Array.Empty<string>():classCards;
            return FlowCore.Concat(variant is "flow-loop" or "flow-paired" or "flow-offense"?FlowLoop:Array.Empty<string>()).Concat(requestedClass).Concat(damage).Concat(Core).Concat(Tail).Distinct(StringComparer.Ordinal).Take(20).ToArray();
        }
        return CounterCore.Concat(variant=="counter-tempo"?classCards:UniversalSupport).Concat(water).Concat(fire).Concat(Core).Concat(Tail).Distinct(StringComparer.Ordinal).Take(20).ToArray();
    }
    private static ExplorationItem[] Armor(string variant)=>Slots.Select((slot,i)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,Equipment:new(slot,i==0?"Orange":"Purple",variant=="counter-offense"?(i<3?"Water":"Fire"):(i<3?"Fire":"Metal"),variant is "offense" or "counter-offense"||i<2?"Piercing":"Vitality","DrawInterval",3,StatsVersion:"season-equipment-v1"),IsGenerated:false)).ToArray();
}
