using System.Text.Json;
using FantasyCard.ConfigExporter;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Unpublished versioned D0 curve experiments; never damages monsters directly or changes formal workbooks.</summary>
public sealed class SeasonD0EntryCandidateTests
{
    public static bool Enabled=>Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_D0_CANDIDATES")=="1";
    private static readonly Dictionary<int,GameConfigCatalog> Candidates=[];
    private sealed record Case(string Id,string Hero,int Seed,int Basis);
    private static Case[] Plan()
    {
        using var doc=JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_D0_PLAN")??throw new InvalidOperationException("Frozen candidate plan required.")));
        var prior=doc.RootElement.GetProperty("prior_used").GetInt32();var rows=doc.RootElement.GetProperty("cases").EnumerateArray().Select(x=>new Case(x.GetProperty("id").GetString()!,x.GetProperty("hero").GetString()!,x.GetProperty("seed").GetInt32(),x.GetProperty("basis").GetInt32())).ToArray();
        Assert.InRange(prior,0,299);Assert.InRange(rows.Length,1,300-prior);Assert.Equal(rows.Length,rows.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count());Assert.All(rows,x=>Assert.True(x.Basis is 7000 or 5000));return rows;
    }
    private static GameConfigCatalog Candidate(int basis)
    {
        if(Candidates.TryGetValue(basis,out var cached))return cached;
        var workbook=Environment.GetEnvironmentVariable("FANTASYCARD_D03_DIFFICULTY_WORKBOOK")??throw new InvalidOperationException("Pinned workbook required.");var tables=XlsxConfigReader.Read(workbook);
        var table=tables.Single(x=>x.Name=="SeasonDifficulty");var rowIndex=table.Rows.Select((r,i)=>(r,i)).Single(x=>Equals(x.r[0].Value,"D0")).i;var rows=table.Rows.ToArray();var row=rows[rowIndex].ToArray();
        foreach(var field in new[]{"hp_scale","shield_scale"}){var index=table.Columns.Select((c,i)=>(c,i)).Single(x=>x.c.Name==field).i;row[index]=new(ConfigValueType.FloatingPoint,basis/10000d);}rows[rowIndex]=row;
        var changed=tables.Select(x=>x==table?x with {Rows=rows}:x).ToArray();var config=GameConfigCatalog.Load(ConfigCompiler.Compile($"d03-d0-hp-shield-{basis}-dev-v1",changed,out _));Candidates.Add(basis,config);return config;
    }
    [Fact(Skip="Versioned unpublished D0 curve input proof, no clock.",SkipUnless=nameof(Enabled))]
    public void CandidateChangesOnlyD0HpAndShieldInItsOwnVersion()
    {
        var rows=Plan();var original=GameConfigCatalog.Current;var proof=new List<object>();
        foreach(var basis in rows.Select(x=>x.Basis).Distinct())
        {
            var config=Candidate(basis);Assert.NotEqual(original.Version,config.Version);Assert.Equal(original.SeasonDifficulty(0) with {HpBasisPoints=basis,ShieldBasisPoints=basis},config.SeasonDifficulty(0));
            for(var d=1;d<6;d++)Assert.Equal(original.SeasonDifficulty(d),config.SeasonDifficulty(d));
            Assert.Equal(JsonSerializer.Serialize(original.Cards),JsonSerializer.Serialize(config.Cards));Assert.Equal(JsonSerializer.Serialize(original.CardLevels),JsonSerializer.Serialize(config.CardLevels));Assert.Equal(JsonSerializer.Serialize(original.SeasonEquipment),JsonSerializer.Serialize(config.SeasonEquipment));Assert.Equal(original.Numerics,config.Numerics);
            proof.Add(new {basis,config.Version,config.ContentHash,originalVersion=original.Version,originalHash=original.ContentHash,D1to5_unchanged=true,damage_interval_rewards_and_caps_unchanged=true});
        }
        File.WriteAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_D0_PREFLIGHT_OUTPUT")??throw new InvalidOperationException("New proof output required."),JsonSerializer.Serialize(new {proof,new_matches=0,formal_workbook_edited=false}));
    }
    [Fact(Skip="Budgeted D03 unpublished curve development branches only.",SkipUnless=nameof(Enabled))]
    public void CandidateD0RunsUseCompiledRealDifficultyAndOriginalGeneratedMaps()
    {
        var rows=Plan();var root=Environment.GetEnvironmentVariable("FANTASYCARD_D03_D0_OUTPUT")??throw new InvalidOperationException("Owned output required.");Assert.False(Directory.Exists(root));Directory.CreateDirectory(root);
        using var attempts=new StreamWriter(Path.Combine(root,"attempts.original.jsonl"));using var trace=new StreamWriter(Path.Combine(root,"events.original.jsonl"));using var results=new StreamWriter(Path.Combine(root,"routes.original.jsonl"));
        foreach(var row in rows)
        {
            attempts.WriteLine(JsonSerializer.Serialize(row));attempts.Flush();var scenario=new SeasonCohortRouteTests.Scenario(row.Id,row.Hero,"novice",row.Seed,0,"natural-shortest",true,true,"support-guard");
            SeasonCohortRouteTests.Run(scenario,trace,results,Array.Empty<ExplorationItem>(),Candidate(row.Basis));trace.Flush();results.Flush();
        }
    }
}
