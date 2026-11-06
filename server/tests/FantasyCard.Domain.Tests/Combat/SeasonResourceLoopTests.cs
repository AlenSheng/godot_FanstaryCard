using System.IO.Compression;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Combat;

public sealed partial class SeasonResourceLoopTests(ITestOutputHelper output)
{
    public static bool MatrixEnabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_B05_MATRIX") == "1";
    private const int MaximumSeconds = 1200;
    private static readonly TimeSpan Step = TimeSpan.FromMilliseconds(100);
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly string[] EquipmentSlots = ["Head","Chest","Hands","Legs","Feet"];
    private static readonly string[] OverflowCards = ["GP20","GP21"];
    private static readonly Dictionary<string, string> Species = new()
    {
        ["fire-bat"]="FireBat", ["thorn-mite"]="ThornMite", ["murk-snail"]="MudHydra", ["sand-lizard"]="SandLizard",
        ["rust-rat"]="RustRat", ["box-spirit"]="BoxSpirit", ["metal-guard"]="GoldGuard", ["fire-herald"]="FireReaver",
        ["marsh-mother"]="SwampMother", ["stone-guard"]="StoneGuard", ["thorn-guard"]="ThornGuard", ["annihilation-core"]="VoidCore"
    };

    [Fact(Skip = "Explicit bounded acceptance matrix; consult the retained B05 budget before enabling.", SkipUnless = nameof(MatrixEnabled))]
    public void LegalTimedExpeditionsAccountForEveryCardAndEveryRealMonsterKill()
    {
        var root=new DirectoryInfo(AppContext.BaseDirectory);
        while(root is not null && !File.Exists(Path.Combine(root.FullName,"global.json"))) root=root.Parent;
        Assert.NotNull(root);
        var directory = Path.Combine(root.FullName,".artifacts/season-b05"); Directory.CreateDirectory(directory);
        using var trace = new StreamWriter(new GZipStream(File.Create(Path.Combine(directory,"actions.jsonl.gz")), CompressionLevel.Fastest), new UTF8Encoding(false));
        var rows = new List<RunRow>();
        foreach (var hero in Enum.GetValues<HeroClass>())
        foreach (var build in new[] { "starter", "draw-engine", "water", "core" })
        for (var level = 0; level <= 5; level++)
        foreach (var fast in new[] { false, true })
        foreach (var seed in new[] { 73101, 73102 })
            rows.Add(Run(hero, build, level, fast, seed, trace));
        trace.Flush();
        Assert.Equal(288, rows.Count);
        File.WriteAllText(Path.Combine(directory,"routes.json"), JsonSerializer.Serialize(new
        {
            scope="Actual current compiled enemy factory and legal 20-card season resource routing; not the pending six-difficulty curve or class-efficiency acceptance",
            maximumMatches=300, actualMatches=rows.Count, tickMilliseconds=100, maximumSeconds=MaximumSeconds,
            noHpOrDeckReset=true, noMonsterHpReduction=true, noOptionalMonsterPool=true, rows
        }), new UTF8Encoding(false));
        foreach (var hero in Enum.GetValues<HeroClass>())
        {
            var subset = rows.Where(r => r.Hero == hero.ToString()).ToArray();
            output.WriteLine(JsonSerializer.Serialize(new { hero=hero.ToString(),matches=subset.Length,
                dead=subset.Count(r=>r.Outcome=="Dead"),extracted=subset.Count(r=>r.Outcome=="Extracted"),
                timeout=subset.Count(r=>r.Outcome=="Timeout"),maxKills=subset.Max(r=>r.Kills),maxActions=subset.Max(r=>r.Actions),
                maxActionsPerSecond=subset.Max(r=>r.Actions/Math.Max(.5,r.Seconds)),maxDps=subset.Max(r=>r.ActualDamage/Math.Max(.5,r.Seconds)) }));
        }
        Assert.DoesNotContain(rows, row => row.Outcome == "Timeout");
        Assert.Contains(rows, row => row.Kills >= 15);
        Assert.All(rows, row => Assert.True(row.Actions <= Math.Floor(row.Seconds / .5) + 1));
    }

    private static RunRow Run(HeroClass hero, string build, int level, bool fast, int seed, StreamWriter trace)
    {
        var deck = Deck(hero, build); SeasonFenxianTests.ValidateDeck(hero, deck);
        var context = new SeasonContext("resource-test", level, "season-v1", GameConfigCatalog.Current.Version, "pre-c05-resource-bound");
        var room = new BattleRoom(Guid.NewGuid(), context.ConfigVersion, Catalog, seed, season:context);
        var element = hero switch { HeroClass.Mage => CardElement.Fire, HeroClass.Priest => CardElement.Water, _ => CardElement.Earth };
        var profile = fast ? EquipmentCombatRules.Calculate(EquipmentSlots
            .Select(slot=>new CombatEquipmentItem(Guid.NewGuid(),slot,"Blue",5,element,null,"DrawInterval")).ToArray()) : CombatEquipmentProfile.Empty;
        var player = room.AddPlayer(new(Guid.NewGuid(),hero,deck,null,WeaponLevel:level,Equipment:profile,CardLevels:Enumerable.Repeat(level,20).ToArray()));
        trace.WriteLine(JsonSerializer.Serialize(new {kind="start",hero=hero.ToString(),build,level,fast,seed,deck,profile,
            enemyCurve="CurrentPrototypeFactory; six scaled curves not yet accepted"}));
        var map = ChaosMapGenerator.Generate(seed,1).Capture();
        // Select a legal outer spawn to traverse a reproducible inward spiral; cells/intents/health stay generated.
        room.InitializeMap(ChaosMapState.Restore(map with { SpawnPositions=[new(0,0)] }));
        var originals = Instances(player).Select(c=>c.InstanceId).ToHashSet();
        var path = Spiral(); var index = 0; var kills = 0; var actions = 0; var actualDamage = 0L;
        var requestedDraw = 0L; var actualDraw = 0L; var naturalDraw=0L; var spent=0L;
        var emptySeconds=0d; var fullSeconds=0d; var castCharge=0d;
        var thresholds = new HashSet<int> {0}; var outcome="Timeout";
        var lastAction = TimeSpan.FromMilliseconds(-500);
        while (room.Elapsed.TotalSeconds < MaximumSeconds)
        {
            var total = Instances(player).ToArray();
            var known=total.Select(c=>c.InstanceId).ToHashSet();
            Assert.Equal(20+kills,total.Length); Assert.Equal(total.Length,known.Count);
            Assert.True(originals.IsSubsetOf(known));
            Assert.InRange(player.Combat.Deck.Hand.Count,0,5); Assert.True(player.Combat.Deck.DrawCharge>=0 && player.Combat.Deck.DrawCharge<1);
            Assert.False(room.Numerics.OptionalMonsterPool); Assert.Empty(player.MonsterPool.Pending); Assert.Empty(player.MonsterPool.Active);
            if (player.Phase == RoomPlayerPhase.Dead) { outcome="Dead"; break; }
            if (player.Phase == RoomPlayerPhase.Extracted) { outcome="Extracted"; break; }
            if (player.Phase == RoomPlayerPhase.Choice)
            {
                var options=player.RewardChoice!.Options;
                var choice=options.Single(o=>o.Kind==(player.Combat.Hp<player.Combat.MaximumHp*.80 ? RewardChoiceKind.ImmediateHeal : RewardChoiceKind.EquipmentFragments));
                room.ClaimReward(player.PlayerId,choice.OptionId);
            }
            if (player.Phase == RoomPlayerPhase.ActionBar)
            {
                var cell=room.Map!.GetCell(player.Position!.Value);
                if (cell.HasSpring && !(room.CapturePlayer(player.PlayerId).ConsumedSprings ?? []).Contains(cell.Position))
                {
                    var drink=room.RequestSpring(player.PlayerId);
                    var until=room.Elapsed+drink;
                    while(room.Elapsed<until && player.Phase!=RoomPlayerPhase.Dead) room.Advance(Step,DateTimeOffset.UnixEpoch+room.Elapsed+Step);
                }
                if (cell.IsBoss || index+1>=path.Length)
                {
                    var remaining=room.RequestExtraction(player.PlayerId); var until=room.Elapsed+remaining;
                    while(room.Elapsed<until && player.Phase!=RoomPlayerPhase.Extracted && player.Phase!=RoomPlayerPhase.Dead)
                        room.Advance(Step,DateTimeOffset.UnixEpoch+room.Elapsed+Step);
                    continue;
                }
                var next=path[++index];
                Assert.Contains(next,room.GetMapProjection(player.PlayerId).LegalMoves);
                room.MovePlayerAndPair(player.PlayerId,next,room.Revision,DateTimeOffset.UnixEpoch+room.Elapsed);
            }
            if (player.Phase==RoomPlayerPhase.Pve && player.Combat.StunRemaining<=TimeSpan.Zero &&
                room.GetCombatActionStatus(player.PlayerId).RemainingMs==0 && player.Combat.Deck.Hand.Count>0)
            {
                var target=player.Pve!.Monsters.Where(m=>!m.IsDead).OrderBy(m=>m.Hp+m.Shield).ThenBy(m=>m.MonsterId,StringComparer.Ordinal).First();
                var selected=Choose(player,target,build,element);
                var before=Instances(player).ToArray(); var hand=player.Combat.Deck.Hand.Count;
                var resolution=room.PlayCards(player.PlayerId,player.Pve.BattleId,target.MonsterId,selected.Select(c=>c.InstanceId).ToArray(),
                    room.Revision,DateTimeOffset.UnixEpoch+room.Elapsed,room.NewCombatActionId(player.PlayerId));
                Assert.True(room.Elapsed-lastAction>=TimeSpan.FromMilliseconds(500)); lastAction=room.Elapsed;
                actions++; actualDamage+=resolution.ShieldDamage+resolution.HpDamage; requestedDraw+=resolution.ImmediateDraw;
                spent+=selected.Length;
                actualDraw+=player.Combat.Deck.Hand.Count-hand+selected.Length; castCharge+=resolution.DrawCharge;
                var newCards=Instances(player).Where(c=>before.All(old=>old.InstanceId!=c.InstanceId)).ToArray();
                if (resolution.TargetDefeated)
                {
                    kills++; var species=target.MonsterId.EndsWith("-a",StringComparison.Ordinal)||target.MonsterId.EndsWith("-b",StringComparison.Ordinal) ? target.MonsterId[..^2] : target.MonsterId;
                    var expected=GameConfigCatalog.Current.Cards.Single(c=>c.MonsterType==Species[species]);
                    var added=Assert.Single(newCards); Assert.Equal(expected.CardId,added.CardId); Assert.Equal(0,added.Level);
                    Assert.Contains(added,player.Combat.Deck.Discard);
                    Assert.Equal(species=="box-spirit" ? target.Intents[0].Element : (CardElement?)null,added.ElementOverride);
                    foreach(var threshold in new[]{5,10,15}) if(kills>=threshold) thresholds.Add(threshold);
                }
                else Assert.Empty(newCards);
                trace.WriteLine(JsonSerializer.Serialize(new { hero=hero.ToString(),build,level,fast,seed,seconds=room.Elapsed.TotalSeconds,
                    actions,selected=selected.Select(c=>new{c.InstanceId,c.CardId,c.Level}),resolution,kills,
                    handBefore=hand,handAfter=player.Combat.Deck.Hand.Count,totalPool=20+kills,
                    chargeAfter=player.Combat.Deck.DrawCharge,newCards }));
            }
            if(player.Combat.Deck.Hand.Count==0) emptySeconds+=Step.TotalSeconds;
            if(player.Combat.Deck.Hand.Count==5) fullSeconds+=Step.TotalSeconds;
            var beforeNatural=player.Combat.Deck.Hand.Count;
            room.Advance(Step,DateTimeOffset.UnixEpoch+room.Elapsed+Step);
            Assert.True(player.Combat.Deck.Hand.Count>=beforeNatural);
            naturalDraw+=player.Combat.Deck.Hand.Count-beforeNatural;
        }
        if(player.Phase==RoomPlayerPhase.Dead) outcome="Dead";
        if(player.Phase==RoomPlayerPhase.Extracted) outcome="Extracted";
        Assert.Equal(player.Combat.Deck.Hand.Count,3+naturalDraw+actualDraw-spent);
        var row=new RunRow(hero.ToString(),build,level,fast,seed,outcome,room.Elapsed.TotalSeconds,actions,kills,actualDamage,
            requestedDraw,actualDraw,naturalDraw,spent,player.Combat.Deck.Hand.Count,castCharge,emptySeconds,fullSeconds,thresholds.Order().ToArray(),player.Combat.Hp);
        trace.WriteLine(JsonSerializer.Serialize(new{kind="end",row}));
        return row;
    }

    [Theory]
    [InlineData(HeroClass.Mage)]
    [InlineData(HeroClass.Priest)]
    [InlineData(HeroClass.Guardian)]
    public void LegalFullHandAndPrintedDrawChargeDoNotBankOverflowOrRewritePrintedEffects(HeroClass hero)
    {
        var cards=SeasonFenxianTests.Starter(hero).Take(18).Concat(OverflowCards).ToArray();
        SeasonFenxianTests.ValidateDeck(hero,cards);
        var context=new SeasonContext("overflow",0,"season-v1",GameConfigCatalog.Current.Version,"current-resource-bound");
        var room=new BattleRoom(Guid.NewGuid(),context.ConfigVersion,Catalog,73,season:context);
        var player=room.AddPlayer(new(Guid.NewGuid(),hero,cards,new PveBattleState(Guid.NewGuid(),"overflow-target",
            [new MonsterCombatState("overflow-target",100000,100000,0,TimeSpan.FromDays(1),[new(MonsterIntentKind.Attack,2,CardElement.Fire)])])));
        SeasonFenxianTests.SetHand(player,"GP20","GP21",cards[0],cards[1],cards[2]);
        var original=Instances(player).Select(c=>c.InstanceId).Order().ToArray();
        for(var i=0;i<200;i++) room.Advance(Step,DateTimeOffset.UnixEpoch+room.Elapsed+Step);
        Assert.Equal(5,player.Combat.Deck.Hand.Count); Assert.True(player.Combat.Deck.DrawCharge<1);
        var selected=player.Combat.Deck.Hand.Where(c=>c.CardId is "GP20" or "GP21").Select(c=>c.InstanceId).ToArray();
        var result=room.PlayCards(player.PlayerId,player.Pve!.BattleId,"overflow-target",selected,room.Revision,
            DateTimeOffset.UnixEpoch+room.Elapsed,room.NewCombatActionId(player.PlayerId));
        Assert.Equal(3,result.ImmediateDraw); Assert.Equal(1,result.DrawCharge);
        Assert.Equal(5,player.Combat.Deck.Hand.Count); Assert.True(player.Combat.Deck.DrawCharge<1);
        Assert.Equal(original,Instances(player).Select(c=>c.InstanceId).Order().ToArray());
    }

    private static CombatCardInstance[] Choose(RoomPlayerState player, MonsterCombatState target, string build, CardElement preferred,
        CombatCardCatalog? publishedCatalog = null)
    {
        var catalog = publishedCatalog ?? Catalog;
        var hand=player.Combat.Deck.Hand;
        CombatCardInstance[] best=[hand[0]]; var bestScore=double.NegativeInfinity;
        for(var mask=1;mask<(1<<hand.Count);mask++)
        {
            var cards=hand.Where((_,i)=>(mask&(1<<i))!=0).OrderByDescending(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride).Effect.Element==preferred).ThenBy(c=>c.CardId,StringComparer.Ordinal).ToArray();
            var definitions=cards.Select(c=>catalog.Get(c.CardId,c.Level,c.ElementOverride)).ToArray();
            var result=CombatResolver.Resolve(definitions,player.Combat,target.ElementalResistance);
            var recovery=Math.Min(result.Heal,player.Combat.EffectiveMaximumHp-player.Combat.Hp);
            var shield=Math.Min(result.Shield,player.Combat.MaximumHp/2-player.Combat.Shield);
            var resource=definitions.Sum(c=>c.Effect.ImmediateDraw+c.Effect.DrawCharge);
            var score=Math.Min(result.Damage,target.Hp+target.Shield)+recovery*1.5+shield*.6-cards.Length*2;
            if(build=="draw-engine") score+=resource*12-cards.Length*2;
            if(build=="water") score+=resource*7+(result.CoreElement==CardElement.Water ? result.CoreCount*2 : 0);
            if(build=="core") score+=result.CoreElement==preferred ? result.CoreCount*3 : 0;
            if(score>bestScore) {bestScore=score;best=cards;}
        }
        return best;
    }
    private static string[] Deck(HeroClass hero,string build)
    {
        var starter=SeasonFenxianTests.Starter(hero); if(build=="starter") return starter;
        var usable=GameConfigCatalog.Current.Cards.Where(c=>c.Enabled&&c.IsCodex&&(c.HeroClass is null||c.HeroClass==hero)).ToArray();
        IEnumerable<string> requested=build switch
        {
            "draw-engine"=>new[]{"C16","C22","GW23","GG32","GG33","GG34","GB28","GB29","GP20","GP21","GO05","ET-WATER-G","ET-WATER-B","ET-WATER-P","ET-WOOD-G","ET-WOOD-B","ET-WOOD-P"},
            "water"=>usable.Where(c=>c.Effect.Element==CardElement.Water||c.Effect.ImmediateDraw>0||c.Effect.DrawCharge>0).OrderByDescending(c=>c.Effect.Element==CardElement.Water).ThenBy(c=>c.Rarity).Select(c=>c.CardId),
            _=>usable.Where(c=>c.Effect.Element==(hero==HeroClass.Mage?CardElement.Fire:hero==HeroClass.Priest?CardElement.Water:CardElement.Earth)).OrderBy(c=>c.Rarity).Select(c=>c.CardId)
        };
        var result=new List<string>(); var oranges=new HashSet<bool>();
        foreach(var id in requested.Concat(starter).Concat(usable.Select(c=>c.CardId)))
        {
            if(result.Contains(id,StringComparer.Ordinal)) continue;
            var card=usable.Single(c=>c.CardId==id);
            if(card.Rarity==(short)CardRarity.Orange&&!oranges.Add(card.HeroClass is not null)) continue;
            result.Add(id); if(result.Count==20) break;
        }
        return result.ToArray();
    }
    private static MapPosition[] Spiral()
    {
        var result=new List<MapPosition>();
        for(var layer=0;layer<3;layer++)
        {
            var end=5-layer;
            for(var c=layer;c<=end;c++) result.Add(new(layer,c));
            for(var r=layer+1;r<=end;r++) result.Add(new(r,end));
            for(var c=end-1;c>=layer;c--) result.Add(new(end,c));
            for(var r=end-1;r>layer;r--) result.Add(new(r,layer));
        }
        return result.ToArray();
    }
    private static IEnumerable<CombatCardInstance> Instances(RoomPlayerState p)=>p.Combat.Deck.Hand.Concat(p.Combat.Deck.Library).Concat(p.Combat.Deck.Discard);
    private sealed record RunRow(string Hero,string Build,int Level,bool Fast,int Seed,string Outcome,double Seconds,int Actions,int Kills,
        long ActualDamage,long RequestedImmediateDraw,long ActualEffectDraw,long ActualNaturalDraw,long CardsSpent,int FinalHand,
        double RequestedCastCharge,double EmptyHandSeconds,double FullHandSeconds,int[] MonsterThresholds,int Hp);
}
