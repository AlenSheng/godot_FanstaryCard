using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Continuation of observed cohort banks, without initial-kit grants after death.</summary>
public sealed class SeasonCohortTrajectoryTests
{
    private static readonly string[] RebuildSlots=["Head","Chest","Hands","Legs","Feet"];
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_TRAJECTORIES")=="1";
    private sealed record Track(string Id,string Source,string Sha256,string SourceCase,int NextSeed,int Steps,string? Checkpoint);
    private static Track[] Plan()
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_TRAJECTORY_PLAN")??throw new InvalidOperationException("Frozen trajectory plan required.")));
        var prior=document.RootElement.GetProperty("prior_used").GetInt32();var rows=document.RootElement.GetProperty("tracks").EnumerateArray().Select(x=>new Track(x.GetProperty("id").GetString()!,x.GetProperty("source").GetString()!,x.GetProperty("sha256").GetString()!,x.GetProperty("source_case").GetString()!,x.GetProperty("next_seed").GetInt32(),x.GetProperty("steps").GetInt32(),x.TryGetProperty("checkpoint",out var p)?p.GetString():null)).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Sum(x=>x.Steps),1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());
        foreach(var row in rows){Assert.InRange(row.Steps,1,25);Assert.True(File.Exists(row.Source));Assert.Equal(row.Sha256,Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(row.Source))));}
        return rows;
    }
    private static SeasonCohortBank Load(Track row)
    {
        if(row.Checkpoint is not null)
        {
            var bank=JsonSerializer.Deserialize<SeasonCohortBank>(File.ReadAllText(row.Source))!;Assert.Equal(row.Id,bank.Id);bank.Check();return bank;
        }
        var records=File.ReadAllLines(row.Source).Select(line=>JsonDocument.Parse(line)).ToArray();
        try{return SeasonCohortBank.Import(records.Single(x=>x.RootElement.GetProperty("scenario").GetProperty("Id").GetString()==row.SourceCase).RootElement,row.Sha256);}
        finally{foreach(var record in records)record.Dispose();}
    }

    [Fact(Skip="Explicit D03 bank-continuation preflight, no match clock.",SkipUnless=nameof(Enabled))]
    public void ObservedBanksPreserveLossesAndDoNotRecreateStartingGear()
    {
        var rows=Plan();var summary=new List<object>();
        foreach(var row in rows)
        {
            var bank=Load(row);var json=JsonSerializer.Serialize(bank);var decoded=JsonSerializer.Deserialize<SeasonCohortBank>(json)!;Assert.Equal(json,JsonSerializer.Serialize(decoded));decoded.Check();
            if(bank.Deaths==bank.Attempts)Assert.Empty(bank.Items);
            var difficulty=bank.Difficulty(GameConfigCatalog.Current);var gear=bank.Select(GameConfigCatalog.Current,difficulty);Assert.All(gear,x=>Assert.DoesNotContain(x.ItemId,bank.LostIds));
            summary.Add(new {bank.Id,bank.Attempts,bank.Deaths,bank.Gold,bank.Fragments,owned=bank.Items.Count,difficulty,worn=gear.Length});
        }
        VerifyBankRebuildControls();
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_TRAJECTORY_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New proof path required."),JsonSerializer.Serialize(new {summary,new_matches=0,rebuild66_and_missingbody_controls=true}));
    }

    [Fact(Skip="Explicit budgeted D03 bank continuation, not independent kit resets.",SkipUnless=nameof(Enabled))]
    public void DeclaredTrajectoriesCarryOnlyRealItemsAndPayActualLobbyCosts()
    {
        var rows=Plan();var root=Environment.GetEnvironmentVariable("FANTASYCARD_D03_TRAJECTORY_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(root));Directory.CreateDirectory(root);var config=GameConfigCatalog.Current;
        using var attempts=new StreamWriter(Path.Combine(root,"attempts.original.jsonl"));using var trace=new StreamWriter(Path.Combine(root,"events.original.jsonl"));using var results=new StreamWriter(Path.Combine(root,"routes.original.jsonl"));
        foreach(var row in rows)
        {
            var bank=Load(row);var directory=Path.Combine(root,row.Id);Directory.CreateDirectory(directory);File.WriteAllText(Path.Combine(directory,"bank-import.original.json"),JsonSerializer.Serialize(bank));
            for(var step=0;step<row.Steps&&bank.StopReason is null;step++)
            {
                var number=bank.Attempts+1;File.WriteAllText(Path.Combine(directory,$"before-lobby-{number:D2}.original.json"),JsonSerializer.Serialize(bank));bank.Lobby(config,trace);
                if(bank.StopReason is not null){File.WriteAllText(Path.Combine(directory,$"censored-{number:D2}.original.json"),JsonSerializer.Serialize(bank));break;}
                var difficulty=bank.Difficulty(config);var selected=bank.Select(config,difficulty);var deployed=bank.Deploy(selected);bank.Check();
                File.WriteAllText(Path.Combine(directory,$"before-match-{number:D2}.original.json"),JsonSerializer.Serialize(new {bank,difficulty,deployed}));
                var scenario=new SeasonCohortRouteTests.Scenario($"{bank.Id}-A{number:D2}",bank.Hero,bank.Cohort,row.NextSeed+step,difficulty,"natural-shortest",difficulty==0&&selected.Length<3,true);
                attempts.WriteLine(JsonSerializer.Serialize(new {track=row.Id,number,scenario,difficulty,owned_worn_ids=selected.Select(x=>x.ItemId)}));attempts.Flush();
                var snapshot=SeasonCohortRouteTests.Run(scenario,trace,results,selected);bank.Settle(snapshot,deployed,config,trace);bank.Check();
                trace.Flush();results.Flush();File.WriteAllText(Path.Combine(directory,$"checkpoint-{number:D2}.original.json"),JsonSerializer.Serialize(bank));
            }
            File.WriteAllText(Path.Combine(directory,"bank-final.original.json"),JsonSerializer.Serialize(bank));
        }
    }
    private static void VerifyBankRebuildControls()
    {
        var bank=new SeasonCohortBank{Id="bank-control",Hero="Mage",Cohort="skilled",Fragments=66,FragmentsEarned=66};
        foreach(var slot in RebuildSlots)
        {
            var quality=slot=="Head"?"Orange":"Purple";var element=slot is "Head" or "Chest" or "Hands"?"Water":"Fire";var effect=slot is "Head" or "Chest"?"Piercing":"Vitality";
            bank.Recipes.Add(new(quality,slot,element,effect,"DrawInterval","known-template-"+slot));var id=Guid.NewGuid().ToString("D");bank.SeenIds.Add(id);
            bank.Items.Add(new(new(id,FantasyCard.Domain.Rooms.ExplorationItemKind.Equipment,Equipment:new("Feet",quality,"Metal","Bulwark","DrawInterval",StatsVersion:"season-equipment-v1"),IsGenerated:false),"NaturalDrop"));
        }
        var ids=bank.Items.Select(x=>x.Item.ItemId).Order().ToArray();using var trace=new StreamWriter(new MemoryStream());bank.Lobby(GameConfigCatalog.Current,trace);bank.Check();
        Assert.Equal(0,bank.Fragments);Assert.Equal(66,bank.FragmentsSpent);Assert.Equal(ids,bank.Items.Select(x=>x.Item.ItemId).Order());Assert.All(bank.Items,x=>Assert.Equal(3,x.Item.Equipment!.Level));
        var empty=new SeasonCohortBank{Id="missing-body-control",Hero="Mage",Cohort="skilled",Fragments=66,FragmentsEarned=66,Recipes=bank.Recipes.ToList()};empty.Lobby(GameConfigCatalog.Current,trace);Assert.Empty(empty.Items);Assert.Equal(66,empty.Fragments);
    }
}
