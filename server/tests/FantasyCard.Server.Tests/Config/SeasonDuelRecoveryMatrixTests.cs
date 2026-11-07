using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Published-season PVP priority, action replay and disconnect recovery; no capacity simulation.</summary>
public sealed partial class SeasonDuelRecoveryMatrixTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D02_DUELS")=="1";
    private static readonly string[] Slots=["Head","Hands","Chest","Legs","Feet"];
    private static readonly string[] Core=["GP15","GP16","GP17","GB19","GB20","GB23","GP20","GP21","GP22","ET-WATER-P","ET-WOOD-P","GO03","GP18","GP23"];
    private static readonly string[] Tail=["GP13","GP19","GP10","GP02"];
    private static readonly TimeSpan Tick=TimeSpan.FromMilliseconds(100);
    private static readonly DateTimeOffset Epoch=new(2026,11,20,0,0,0,TimeSpan.Zero);
    private sealed record Scenario(string Id,HeroClass First,HeroClass Late,int Difficulty,string Outcome,string DisconnectRole,int Seed);

    private static Scenario[] Plan()
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D02_DUEL_PLAN")??throw new InvalidOperationException("Frozen plan required.")));
        var prior=document.RootElement.GetProperty("prior_used").GetInt32();var rows=document.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Scenario(x.GetProperty("id").GetString()!,Enum.Parse<HeroClass>(x.GetProperty("first").GetString()!),Enum.Parse<HeroClass>(x.GetProperty("late").GetString()!),x.GetProperty("difficulty").GetInt32(),x.GetProperty("outcome").GetString()!,x.GetProperty("disconnect_role").GetString()!,x.GetProperty("seed").GetInt32())).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows){Assert.True(Enum.IsDefined(row.First)&&Enum.IsDefined(row.Late));Assert.True(row.Difficulty is 0 or 5);Assert.True(row.Outcome is "Reconnect" or "Expire");Assert.True(row.DisconnectRole is "First" or "Late");}
        return rows;
    }

    [Fact(Skip="Requires a frozen D02 plan, no timed duel execution.",SkipUnless=nameof(Enabled))]
    public void PublishedDuelInputsAreLegalBeforeAdmission()
    {
        var config=GameConfigCatalog.Current;var rows=Plan();
        foreach(var row in rows)
        foreach(var hero in new[]{row.First,row.Late})
        {
            DeckRules.Validate(hero,Deck(hero),config.Cards.Where(x=>x.IsCodex).ToDictionary(x=>x.CardId,x=>new OwnedCard(x.CardId,x.HeroClass,(CardRarity)x.Rarity,1,false)));
            var armor=Armor(row.Difficulty);Assert.All(armor,x=>Assert.True(EquipmentRewardRules.IsValid(x.Equipment!)));
            SeasonLootRules.RequireEntry(new("d02-duel",row.Difficulty,"season-v1",config.Version,"season-equipment-v1"),armor.Select(x=>x.Equipment!),config);
        }
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D02_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New preflight output required."),JsonSerializer.Serialize(new {cases=rows.Length,config.Version,config.ContentHash,new_timed_duels=0}));
    }

    [Fact(Skip="Budgeted published D02 PVP scenarios; never rerun an attempted roster.",SkipUnless=nameof(Enabled))]
    public void PublishedDuelsKeepPriorityControlLedgersAndFrozenPveThroughRecovery()
    {
        var scenarios=Plan();var directory=Environment.GetEnvironmentVariable("FANTASYCARD_D02_DUEL_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        using var attempts=new StreamWriter(Path.Combine(directory,"attempts.original.jsonl"));using var trace=new StreamWriter(Path.Combine(directory,"events.original.jsonl"));using var results=new StreamWriter(Path.Combine(directory,"cases.original.jsonl"));
        foreach(var scenario in scenarios){attempts.WriteLine(JsonSerializer.Serialize(scenario));attempts.Flush();Run(scenario,trace,results);trace.Flush();results.Flush();}
    }

    private static void Run(Scenario scenario,StreamWriter trace,StreamWriter results)
    {
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);var context=new SeasonContext("d02-duel",scenario.Difficulty,"season-v1",config.Version,"season-equipment-v1");
        var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,scenario.Seed,season:context);var firstId=Guid.NewGuid();var lateId=Guid.NewGuid();
        room.AddPlayer(new(firstId,scenario.First,Deck(scenario.First),null,WeaponLevel:scenario.Difficulty,WornArmor:Armor(scenario.Difficulty),CardLevels:Enumerable.Repeat(scenario.Difficulty,20).ToArray()));
        room.AddPlayer(new(lateId,scenario.Late,Deck(scenario.Late),null,WeaponLevel:scenario.Difficulty,WornArmor:Armor(scenario.Difficulty),CardLevels:Enumerable.Repeat(scenario.Difficulty,20).ToArray()));
        room.InitializeMap(ChaosMapGenerator.Generate(scenario.Seed,2,config.SeasonThemes));room.Advance(Tick,Epoch+Tick);
        foreach(var id in new[]{firstId,lateId})
        {
            var combat=room.GetPlayer(id).Combat;combat.TakeDamage(3);combat.GainShield(5);combat.AddDrawCharge(.45);combat.ApplyDrawSpeed(TimeSpan.FromSeconds(3),-.1);
        }
        var firstBefore=room.CapturePlayer(firstId);var lateBefore=room.CapturePlayer(lateId);var beforeDuel=room.Capture();
        var duel=room.StartDuel(firstId,lateId,Epoch+room.Elapsed);var duelId=duel.DuelId;
        trace.WriteLine(JsonSerializer.Serialize(new {kind="start",scenario,config.Version,config.ContentHash,firstId,lateId,firstBefore,lateBefore,snapshot=room.Capture()}));trace.Flush();
        Assert.Equal(3,room.GetPlayer(firstId).Combat.Deck.Hand.Count);Assert.Equal(3,room.GetPlayer(lateId).Combat.Deck.Hand.Count);
        var beforeReject=JsonSerializer.Serialize(room.Capture());
        Assert.Throws<DomainValidationException>(()=>PlayWeakest(room,lateId,firstId,duelId,catalog));Assert.Equal(beforeReject,JsonSerializer.Serialize(room.Capture()));
        trace.WriteLine(JsonSerializer.Serialize(new {kind="late-lock-rejected",scenario.Id,seconds=room.Elapsed.TotalSeconds,snapshot=room.Capture()}));
        var first=PlayWeakest(room,firstId,lateId,duelId,catalog);var firstReceipt=first.Result;var firstCards=first.Cards;
        trace.WriteLine(JsonSerializer.Serialize(new {kind="cast-first",scenario.Id,seconds=room.Elapsed.TotalSeconds,cards=firstCards,result=firstReceipt,snapshot=room.Capture()}));
        beforeReject=JsonSerializer.Serialize(room.Capture());
        Assert.Throws<DomainValidationException>(()=>PlayWeakest(room,firstId,lateId,duelId,catalog));Assert.Equal(beforeReject,JsonSerializer.Serialize(room.Capture()));
        while(room.Elapsed.TotalSeconds<(duel.StartedAt-Epoch).TotalSeconds+.8||room.GetPlayer(lateId).Combat.StunRemaining>TimeSpan.Zero)Step(room);
        var late=PlayWeakest(room,lateId,firstId,duelId,catalog);
        trace.WriteLine(JsonSerializer.Serialize(new {kind="cast-late",scenario.Id,seconds=room.Elapsed.TotalSeconds,cards=late.Cards,result=late.Result,snapshot=room.Capture()}));
        Assert.Equal(JsonSerializer.Serialize(firstBefore.Pve!.Monsters),JsonSerializer.Serialize(room.CapturePlayer(firstId).Pve!.Monsters));Assert.Equal(JsonSerializer.Serialize(lateBefore.Pve!.Monsters),JsonSerializer.Serialize(room.CapturePlayer(lateId).Pve!.Monsters));
        var disconnected=scenario.DisconnectRole=="First"?firstId:lateId;room.MarkPlayerDisconnected(disconnected);
        var frozenFirst=JsonSerializer.Serialize(room.GetPlayer(firstId).Combat.Capture());var frozenLate=JsonSerializer.Serialize(room.GetPlayer(lateId).Combat.Capture());
        beforeReject=JsonSerializer.Serialize(room.Capture());
        Assert.Throws<DomainValidationException>(()=>PlayWeakest(room,lateId,firstId,duelId,catalog));Assert.Equal(beforeReject,JsonSerializer.Serialize(room.Capture()));
        for(var i=0;i<20;i++)Step(room);
        var snapshot=room.Capture();var raw=JsonSerializer.Serialize(snapshot);room=BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(raw)!,catalog,scenario.Seed);
        Assert.Equivalent(snapshot,room.Capture(),strict:true);
        trace.WriteLine(JsonSerializer.Serialize(new {kind="restored-disconnected",scenario.Id,seconds=room.Elapsed.TotalSeconds,snapshot=room.Capture()}));
        var beforeReplay=JsonSerializer.Serialize(room.Capture());var replay=room.ReplayCombatAction(firstId,firstReceipt.CombatActionId,duelId,lateId.ToString("D"),firstCards);
        Assert.True(replay.ActionReplayed);Assert.Equal(beforeReplay,JsonSerializer.Serialize(room.Capture()));
        trace.WriteLine(JsonSerializer.Serialize(new {kind="action-replay",scenario.Id,result=replay,unchanged_snapshot=true}));
        if(scenario.Outcome=="Reconnect")
        {
            Assert.Equal(frozenFirst,JsonSerializer.Serialize(room.GetPlayer(firstId).Combat.Capture()));Assert.Equal(frozenLate,JsonSerializer.Serialize(room.GetPlayer(lateId).Combat.Capture()));
            room.MarkPlayerConnected(disconnected);Step(room);
            Assert.False(room.RequestDuelLeave(duelId,firstId,Epoch+room.Elapsed));Assert.True(room.RequestDuelLeave(duelId,lateId,Epoch+room.Elapsed));
            Assert.Equal(JsonSerializer.Serialize(firstBefore.Combat),JsonSerializer.Serialize(room.CapturePlayer(firstId).Combat));Assert.Equal(JsonSerializer.Serialize(lateBefore.Combat),JsonSerializer.Serialize(room.CapturePlayer(lateId).Combat));
            Assert.Equal(JsonSerializer.Serialize(firstBefore.Pve),JsonSerializer.Serialize(room.CapturePlayer(firstId).Pve));Assert.Equal(JsonSerializer.Serialize(lateBefore.Pve),JsonSerializer.Serialize(room.CapturePlayer(lateId).Pve));
            Assert.Equal(RoomPlayerPhase.Pve,room.GetPlayer(firstId).Phase);Assert.Equal(RoomPlayerPhase.Pve,room.GetPlayer(lateId).Phase);
        }
        else
        {
            for(var i=0;i<129;i++)Step(room); // 14.9s since disconnect, including the 2s before JSON recovery.
            Assert.Equal(RoomPlayerPhase.Pvp,room.GetPlayer(disconnected).Phase);
            Assert.Equal(frozenFirst,JsonSerializer.Serialize(room.GetPlayer(firstId).Combat.Capture()));Assert.Equal(frozenLate,JsonSerializer.Serialize(room.GetPlayer(lateId).Combat.Capture()));
            trace.WriteLine(JsonSerializer.Serialize(new {kind="before-expiry",scenario.Id,remaining=room.CapturePlayer(disconnected).DisconnectedRemaining,snapshot=room.Capture()}));Step(room);
            var winner=disconnected==firstId?lateId:firstId;
            // Expiry restores PVE before Advance executes this tick's ordinary PVE work.
            var control=BattleRoom.Restore(beforeDuel,catalog,scenario.Seed);Step(control);var prior=control.CapturePlayer(winner);
            trace.WriteLine(JsonSerializer.Serialize(new {kind="expiry-resume-control",scenario.Id,snapshot=room.Capture(),expectedWinner=prior,expected_pve_ticks_after_restore=1}));
            Assert.Equal(RoomPlayerPhase.Dead,room.GetPlayer(disconnected).Phase);Assert.Equal(0,room.GetPlayer(disconnected).Combat.Hp);Assert.Null(room.GetPlayer(disconnected).Pve);
            Assert.Equal(JsonSerializer.Serialize(prior.Combat),JsonSerializer.Serialize(room.CapturePlayer(winner).Combat));Assert.Equal(JsonSerializer.Serialize(prior.Pve),JsonSerializer.Serialize(room.CapturePlayer(winner).Pve));
            Assert.Equal(RoomPlayerPhase.Pve,room.GetPlayer(winner).Phase);
            var deadBefore=disconnected==firstId?firstBefore:lateBefore;var pile=Assert.Single(room.Capture().RelicPiles!,x=>x.VictimId==disconnected.ToString("D"));
            foreach(var item in deadBefore.WornArmor!)Assert.Contains(pile.Items,x=>x.ItemId==item.ItemId&&x.Equipment==item.Equipment);
        }
        var final=room.Capture();Assert.Empty(final.Duels);
        var result=new {scenario,seconds=room.Elapsed.TotalSeconds,firstCast=firstReceipt,lateCast=late.Result,firstSequence=room.GetCombatActionStatus(firstId).NextSequence,lateSequence=room.GetCombatActionStatus(lateId).NextSequence,snapshot=final,original_frozen_pve_preserved=true,replay_preserved=true,disconnect_deadline_verified=true};
        trace.WriteLine(JsonSerializer.Serialize(new {kind="end",result}));results.WriteLine(JsonSerializer.Serialize(result));
    }

    private static (CombatResolution Result,Guid[] Cards) PlayWeakest(BattleRoom room,Guid playerId,Guid targetId,Guid duelId,CombatCardCatalog catalog)
    {
        var player=room.GetPlayer(playerId);var target=room.GetPlayer(targetId);
        var card=player.Combat.Deck.Hand.OrderBy(x=>CombatResolver.Resolve([catalog.Get(x.CardId,x.Level,x.ElementOverride)],player.Combat,target.Combat.ElementalResistance).Damage).First();
        var ids=new[]{card.InstanceId};return(room.PlayCards(playerId,duelId,targetId.ToString("D"),ids,room.Revision,Epoch+room.Elapsed,room.NewCombatActionId(playerId)),ids);
    }
    private static void Step(BattleRoom room)=>room.Advance(Tick,Epoch+room.Elapsed+Tick);
    private static string[] Deck(HeroClass hero)=>Core.Concat(new[]{hero==HeroClass.Mage?"MAG-09":hero==HeroClass.Priest?"PRI-09":"GUA-09",hero==HeroClass.Mage?"MAG-10":hero==HeroClass.Priest?"PRI-10":"GUA-10"}).Concat(Tail).ToArray();
    private static ExplorationItem[] Armor(int difficulty)=>Slots.Select((slot,i)=>new ExplorationItem(Guid.NewGuid().ToString("D"),ExplorationItemKind.Equipment,Equipment:new(slot,difficulty==0?"Blue":i==0?"Orange":"Purple",i<3?"Fire":"Metal",difficulty==0?null:i<2?"Piercing":"Vitality","DrawInterval",3,StatsVersion:"season-equipment-v1"),IsGenerated:false)).ToArray();
}
