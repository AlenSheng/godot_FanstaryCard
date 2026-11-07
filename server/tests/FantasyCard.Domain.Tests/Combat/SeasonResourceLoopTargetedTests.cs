using System.Globalization;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed partial class SeasonResourceLoopTests
{
    public static bool FinalNineEnabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_B05_FINAL_NINE") == "1";
    private static readonly string[] FinalBuilds = ["water", "draw-engine", "core"];
    private static readonly string[] FinalOutcomes = ["Dead", "Extracted"];
    private static readonly MapPosition[] R1 = [new(0,0),new(0,1),new(0,2),new(0,3),new(0,4),new(1,4),new(2,4),new(2,3)];
    private const int FormalDifficulty = 2;

    [Fact(Skip = "Explicit final B05 budget: at most nine new routes, previous 291 retained.", SkipUnless = nameof(FinalNineEnabled))]
    public void FinalNinePublishedR1RoutesKeepEveryDrawWithinItsPrintedAndPassiveBudget()
    {
        Assert.False(MatrixEnabled);
        var directory = Environment.GetEnvironmentVariable("FANTASYCARD_B05_FINAL_DIR") ?? throw new InvalidOperationException("Owned evidence directory required.");
        Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        var configuration=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(configuration);
        var seed=Enumerable.Range(73150,10000).First(n=>
        {
            var map=ChaosMapGenerator.Generate(n,1,configuration.SeasonThemes);
            return map.BossPosition==R1[^1]&&map.SpawnPositions[0]==R1[0];
        });
        var map=ChaosMapGenerator.Generate(seed,1,configuration.SeasonThemes);
        Assert.Equal("M",map.GetCell(R1[5]).MonsterGroupId[..1]);Assert.Equal("E",map.GetCell(R1[6]).MonsterGroupId[..1]);
        for(var i=1;i<R1.Length;i++)Assert.True(map.CanMove(R1[i-1],R1[i]));
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"),false,new UTF8Encoding(false));
        using var results=new StreamWriter(Path.Combine(directory,"routes.original.jsonl"),false,new UTF8Encoding(false));
        using var trace=new StreamWriter(new GZipStream(File.Create(Path.Combine(directory,"actions.original.jsonl.gz")),CompressionLevel.Fastest),new UTF8Encoding(false));
        var rows=new List<TargetedRoute>();
        var skip=int.Parse(Environment.GetEnvironmentVariable("FANTASYCARD_B05_SKIP_FIRST")??"0",CultureInfo.InvariantCulture);Assert.InRange(skip,0,8);var number=0;
        foreach(var hero in Enum.GetValues<HeroClass>())
        foreach(var build in FinalBuilds)
        {
            number++;if(number<=skip)continue;
            var deck=Deck(hero,build);SeasonFenxianTests.ValidateDeck(hero,deck);
            attempts.WriteLine(JsonSerializer.Serialize(new{number,hero=hero.ToString(),build,seed,configuration.Version,configuration.ContentHash,difficulty=FormalDifficulty,previousBudget=291+skip,maximumBudget=300}));attempts.Flush();
            var row=RunPublishedR1(hero,build,deck,catalog,seed,trace);rows.Add(row);
            results.WriteLine(JsonSerializer.Serialize(row));results.Flush();trace.Flush();
        }
        Assert.Equal(9-skip,rows.Count);
        Assert.All(rows,row=>Assert.Contains(row.Outcome,FinalOutcomes));
        Assert.Contains(rows,row=>row.Outcome=="Extracted");
        Assert.All(rows,row=>Assert.True(row.Actions<=Math.Floor(row.Seconds/.5)+1));
    }

    private static TargetedRoute RunPublishedR1(HeroClass hero,string build,string[] deck,CombatCardCatalog catalog,int seed,StreamWriter trace)
    {
        var configuration=GameConfigCatalog.Current;var theme=configuration.SeasonThemes!.Selected;
        var context=new SeasonContext("b05-final-r1",FormalDifficulty,"season-v1",configuration.Version,"season-equipment-v1");
        var armor=EquipmentSlots.Select((slot,index)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new(slot,index==0?"Orange":"Purple",(index<3?theme.PhaseOnePrimary:theme.PhaseTwoPrimary).ToString(),
                hero==HeroClass.Guardian?(index<3?"Bulwark":"Vitality"):hero==HeroClass.Priest?(index<3?"Vitality":"Piercing"):(index<3?"Piercing":"Vitality"),
                "DrawInterval",3,StatsVersion:context.StatsVersion),IsGenerated:false)).ToArray();
        var room=new BattleRoom(Guid.NewGuid(),configuration.Version,catalog,seed,season:context);
        var player=room.AddPlayer(new(Guid.NewGuid(),hero,deck,null,WeaponLevel:FormalDifficulty,WornArmor:armor,CardLevels:Enumerable.Repeat(FormalDifficulty,20).ToArray()));
        var map=ChaosMapGenerator.Generate(seed,1,configuration.SeasonThemes);room.InitializeMap(map);
        var original=Instances(player).Select(c=>c.InstanceId).ToHashSet();
        trace.WriteLine(JsonSerializer.Serialize(new{kind="start",hero=hero.ToString(),build,seed,configuration.Version,configuration.ContentHash,context,deck,armor,map=map.Capture(),path=R1,
            original=Instances(player).ToArray(),declaredProfile="Permanent cards/weapon assumed5, effective2; real 1Orange4Purple armor+3; no red; no reset or monster edits"}));
        var index=0;var actions=0;var kills=0;var natural=0L;var effectActual=0L;var spent=0L;var damage=0L;
        var printedRequested=0L;var passiveRequested=0L;var passiveCharge=0d;var fullTicks=0;var emptyTicks=0;
        var last=TimeSpan.FromMilliseconds(-500);var outcome="Timeout";
        void CheckPool()
        {
            var all=Instances(player).ToArray();Assert.Equal(20+kills,all.Length);Assert.Equal(all.Length,all.Select(c=>c.InstanceId).Distinct().Count());
            Assert.True(original.IsSubsetOf(all.Select(c=>c.InstanceId).ToHashSet()));Assert.InRange(player.Combat.Deck.Hand.Count,0,5);
            Assert.InRange(player.Combat.Deck.DrawCharge,0,Math.BitDecrement(1d));
            Assert.False(room.Numerics.OptionalMonsterPool);Assert.Empty(player.MonsterPool.Pending);Assert.Empty(player.MonsterPool.Active);
            Assert.Equal(player.Combat.Deck.Hand.Count,3+natural+effectActual-spent);
        }
        void Tick()
        {
            var before=player.Combat.Deck.Hand.Count;room.Advance(Step,DateTimeOffset.UnixEpoch+room.Elapsed+Step);
            Assert.True(player.Combat.Deck.Hand.Count>=before);natural+=player.Combat.Deck.Hand.Count-before;
            if(player.Combat.Deck.Hand.Count==5)fullTicks++;if(player.Combat.Deck.Hand.Count==0)emptyTicks++;
            CheckPool();
        }
        while(room.Elapsed.TotalSeconds<MaximumSeconds)
        {
            CheckPool();
            if(player.Phase==RoomPlayerPhase.Dead){outcome="Dead";break;}
            if(player.Phase==RoomPlayerPhase.Extracted){outcome="Extracted";break;}
            if(player.Phase==RoomPlayerPhase.Choice)
            {
                if(player.PendingRedEvaluation is {} pending)
                {
                    var hit=room.RedPolicy!.Hits(pending.Source,FormalDifficulty,pending.Roll);
                    trace.WriteLine(JsonSerializer.Serialize(new{kind="red-evaluation",hero=hero.ToString(),build,pending,hit,scope="Actual frozen policy Miss branch only; no database/quota claim"}));trace.Flush();
                    Assert.False(hit,"A winning red roll requires the real quota repository; never fabricate a no-drop receipt.");
                    room.ApplyRedDrop(player.PlayerId,new(pending.AttemptId,"Miss",null));
                }
                var kind=player.Combat.Hp<player.Combat.EffectiveMaximumHp*.80?RewardChoiceKind.ImmediateHeal:RewardChoiceKind.EquipmentFragments;
                room.ClaimReward(player.PlayerId,player.RewardChoice!.Options.Single(o=>o.Kind==kind).OptionId);
            }
            if(player.Phase==RoomPlayerPhase.ActionBar)
            {
                var cell=map.GetCell(player.Position!.Value);
                if(cell.HasSpring&&!(room.CapturePlayer(player.PlayerId).ConsumedSprings??[]).Contains(cell.Position))
                {
                    var until=room.Elapsed+room.RequestSpring(player.PlayerId);
                    while(room.Elapsed<until&&player.Phase!=RoomPlayerPhase.Dead)Tick();
                }
                if(cell.IsBoss)
                {
                    var until=room.Elapsed+room.RequestExtraction(player.PlayerId);
                    while(room.Elapsed<until&&player.Phase is not (RoomPlayerPhase.Extracted or RoomPlayerPhase.Dead))Tick();
                    continue;
                }
                var next=R1[++index];Assert.Contains(next,room.GetMapProjection(player.PlayerId).LegalMoves);
                room.MovePlayerAndPair(player.PlayerId,next,room.Revision,DateTimeOffset.UnixEpoch+room.Elapsed);
            }
            if(player.Phase==RoomPlayerPhase.Pve&&player.Combat.StunRemaining<=TimeSpan.Zero&&room.GetCombatActionStatus(player.PlayerId).RemainingMs==0&&player.Combat.Deck.Hand.Count>0)
            {
                var target=player.Pve!.Monsters.Where(m=>!m.IsDead).OrderBy(m=>m.Hp+m.Shield).ThenBy(m=>m.MonsterId,StringComparer.Ordinal).First();
                var preferred=hero==HeroClass.Mage?CardElement.Fire:hero==HeroClass.Priest?CardElement.Water:CardElement.Earth;
                var chosen=Choose(player,target,build,preferred,catalog);var definitions=chosen.Select(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride)).ToArray();
                var draft=CombatResolver.Resolve(definitions,player.Combat,target.ElementalResistance);
                var before=Instances(player).ToArray();var hand=player.Combat.Deck.Hand.Count;
                var resolution=room.PlayCards(player.PlayerId,player.Pve.BattleId,target.MonsterId,chosen.Select(c=>c.InstanceId).ToArray(),room.Revision,DateTimeOffset.UnixEpoch+room.Elapsed,room.NewCombatActionId(player.PlayerId));
                var passive=resolution.ImmediateDraw-draft.ImmediateDraw;
                var extraCharge=resolution.DrawCharge-draft.DrawCharge;
                Assert.InRange(passive,0,hero==HeroClass.Mage&&draft.CoreCount>=2?chosen.Length-1:0);
                Assert.InRange(extraCharge,0,hero==HeroClass.Mage&&draft.CoreCount>0?.500000001:0);
                Assert.True(room.Elapsed-last>=TimeSpan.FromMilliseconds(500));last=room.Elapsed;
                actions++;spent+=chosen.Length;effectActual+=player.Combat.Deck.Hand.Count-hand+chosen.Length;
                printedRequested+=draft.ImmediateDraw;passiveRequested+=passive;passiveCharge+=extraCharge;damage+=resolution.HpDamage+resolution.ShieldDamage;
                var added=Instances(player).Where(c=>before.All(old=>old.InstanceId!=c.InstanceId)).ToArray();
                if(resolution.TargetDefeated)
                {
                    kills++;var species=target.MonsterId.EndsWith("-a",StringComparison.Ordinal)||target.MonsterId.EndsWith("-b",StringComparison.Ordinal)?target.MonsterId[..^2]:target.MonsterId;
                    var expected=configuration.Cards.Single(c=>c.MonsterType==Species[species]);var card=Assert.Single(added);
                    Assert.Equal(expected.CardId,card.CardId);Assert.Equal(0,card.Level);Assert.Contains(card,player.Combat.Deck.Discard);
                    Assert.Equal(species=="box-spirit"?target.Intents[0].Element:(CardElement?)null,card.ElementOverride);
                }
                else Assert.Empty(added);
                CheckPool();trace.WriteLine(JsonSerializer.Serialize(new{kind="cast",hero=hero.ToString(),build,seconds=room.Elapsed.TotalSeconds,position=player.Position,
                    chosen=chosen.Select(c=>new{c.InstanceId,c.CardId,c.Level}),printedDraw=draft.ImmediateDraw,passive,printedCharge=draft.DrawCharge,extraCharge,
                    resolution,handBefore=hand,handAfter=player.Combat.Deck.Hand.Count,chargeAfter=player.Combat.Deck.DrawCharge,natural,effectActual,spent,kills,added}));
            }
            Tick();
        }
        if(player.Phase==RoomPlayerPhase.Dead)outcome="Dead";if(player.Phase==RoomPlayerPhase.Extracted)outcome="Extracted";
        CheckPool();var row=new TargetedRoute(hero.ToString(),build,seed,FormalDifficulty,outcome,room.Elapsed.TotalSeconds,actions,kills,damage,
            printedRequested,passiveRequested,passiveCharge,natural,effectActual,spent,player.Combat.Deck.Hand.Count,emptyTicks,fullTicks,index+1,player.Combat.Hp);
        trace.WriteLine(JsonSerializer.Serialize(new{kind="end",row}));return row;
    }

    private sealed record TargetedRoute(string Hero,string Build,int Seed,int Difficulty,string Outcome,double Seconds,int Actions,int Kills,long Damage,
        long PrintedDraw,long PassiveDraw,double PassiveCharge,long NaturalDraw,long ActualEffectDraw,long CardsSpent,int FinalHand,int EmptyTicks,int FullTicks,int VisitedCells,int Hp);
}
