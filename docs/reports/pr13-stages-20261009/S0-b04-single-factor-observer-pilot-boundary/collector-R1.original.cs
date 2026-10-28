using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

return DeckSingleFactor.Run(args);

internal static class DeckSingleFactor
{
    public static int Run(string[] args)
    {
        string Option(string name) { var i=Array.IndexOf(args,name); return i>=0 && i+1<args.Length ? args[i+1] : throw new ArgumentException(name); }
        var hero=Enum.Parse<HeroClass>(Option("--hero")); var group=Option("--group"); var strategy=Option("--strategy");
        var block=int.Parse(Option("--block"),CultureInfo.InvariantCulture); var samples=int.Parse(Option("--samples"),CultureInfo.InvariantCulture);
        var offset=int.Parse(Option("--offset"),CultureInfo.InvariantCulture); var source=Option("--source-sha"); var output=Path.GetFullPath(Option("--output"));
        if (!Enum.IsDefined(hero) || !new[]{"O1","O6","E1","BOSS"}.Contains(group) ||
            !new[]{"baseline_all_hand","basic","build"}.Contains(strategy) || block is <0 or >2 || samples is <1 or >1000 ||
            offset<0 || offset+samples>1000 || source.Length!=40 || source.Any(c=>!Uri.IsHexDigit(c)) || Directory.Exists(output))
            throw new ArgumentException("Exact full-matrix identity and new bounded part required");
        var config=GameConfigCatalog.Current; var catalog=CombatCardCatalog.CreatePrototype();
        if (config.Numerics.CardsSpentDraw || config.Numerics.FractionalGuardian || config.Numerics.OptionalMonsterPool ||
            config.Numerics.BudgetedBotLoot || config.Numerics.MortalBotPve) throw new InvalidOperationException("Formal default candidates changed");
        var decks=CombatExperience.CreateDecks(config,hero);
        if (!decks.ContainsKey("default") || !decks.ContainsKey("theme_single_swap") || decks.Count!=2)
            throw new InvalidOperationException("Expected actual published default and a legal one-card candidate");
        var baseline=decks["default"]; var candidate=decks["theme_single_swap"];
        FantasyCard.Domain.Cards.PairedDeckBudget.Validate(config,hero,baseline,candidate);
        var start=450001+block*1000+offset; Directory.CreateDirectory(output);
        var manifest=new { schema="actual_default_deck_single_factor_diagnostic_v1",source_sha=source,hero=hero.ToString(),group,strategy,
            block,seed_start=start,samples,offset,cutoff_seconds=600,tick_ms=100,action_interval_seconds=.4,
            weapon_level=0,card_level=0,equipment="Empty",baseline_deck=baseline,candidate_deck=candidate,
            baseline_budget=CombatExperience.Budget(config,baseline),candidate_budget=CombatExperience.Budget(config,candidate),
            config_version=config.Version,config_sha256=Hash(JsonSerializer.SerializeToUtf8Bytes(config)),actual_card_definitions=config.Cards,
            fixed_effective_rules=config.Numerics,only_changed_factor="one same-quality same-level same-cost card",
            candidates_production_activation=false,full_required_encounters=216000,required_independent_blocks=3,
            required_paired_seeds_per_stratum=3000,scope="Same real Domain simulated encounter entry; first battle and card diagnostics, not natural full expedition or capacity" };
        File.WriteAllText(Path.Combine(output,"manifest.original.json"),JsonSerializer.Serialize(manifest)+"\n");
        using var events=new DiagnosticEvents(output,256L*1024*1024);
        using var file=new FileStream(Path.Combine(output,"encounters.original.jsonl.gz"),FileMode.CreateNew);
        using var gzip=new GZipStream(file,CompressionLevel.Fastest);
        using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);var rows=0;var errors=0;long rawBytes=0;
        var outcomes=new Dictionary<string,int>();
        for(var seed=start;seed<start+samples;seed++)
        foreach(var changed in new[]{false,true})
        {
            var observer=new DeckDiagnosticObserver(catalog,events.Write);
            var row=CombatExperience.Simulate(config,catalog,hero,changed?"theme_single_swap":"default",changed?candidate:baseline,
                group,strategy,changed?"SingleCardCandidate":"ActualPublishedDefault",config.Numerics,seed,block,600,0,
                marginalAudit:true,deckObserver:observer);
            var bytes=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(row)+"\n");gzip.Write(bytes);hash.AppendData(bytes);rawBytes+=bytes.Length;rows++;
            outcomes[row.Outcome]=outcomes.GetValueOrDefault(row.Outcome)+1;if(row.Outcome=="Error")errors++;
        }
        gzip.Dispose();events.Dispose();var path=Path.Combine(output,"encounters.original.jsonl.gz");
        var summary=new {passed=rows==samples*2 && errors==0,source_sha=source,hero=hero.ToString(),group,strategy,block,seed_start=start,samples,
            actual_encounters=rows,actual_errors=errors,outcomes,original_raw_bytes=rawBytes,original_raw_sha256=Convert.ToHexStringLower(hash.GetHashAndReset()),
            stored_bytes=new FileInfo(path).Length,stored_sha256=Hash(File.ReadAllBytes(path)),observer_events=events.Count,
            observer_parts=events.Parts,formal_acceptance=false,MAIN_accepted=false};
        File.WriteAllText(Path.Combine(output,"summary.original.json"),JsonSerializer.Serialize(summary)+"\n");
        Console.WriteLine(JsonSerializer.Serialize(summary));return summary.passed?0:1;
    }
    private static string Hash(byte[] b)=>Convert.ToHexStringLower(SHA256.HashData(b));
}

internal sealed class DiagnosticEvents(string directory,long rawBudget) : IDisposable
{
    private FileStream? _file;private GZipStream? _gzip;private IncrementalHash? _hash;private string _name="";private long _raw;private long _all;private long _count;
    public long Count{get;private set;}public List<object> Parts{get;}=[];
    public void Write(object value)
    {
        var bytes=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value)+"\n");
        if (_all+bytes.Length>rawBudget)throw new InvalidOperationException("Frozen diagnostic raw budget reached; existing originals retained");
        if (_gzip is null || _raw+bytes.Length>16*1024*1024){ClosePart();_name="diagnostic-"+Parts.Count.ToString("D4")+".original.jsonl.gz";_file=new FileStream(Path.Combine(directory,_name),FileMode.CreateNew);_gzip=new GZipStream(_file,CompressionLevel.Fastest);_hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);_raw=0;_count=0;}
        _gzip.Write(bytes);_hash!.AppendData(bytes);_raw+=bytes.Length;_all+=bytes.Length;_count++;Count++;
    }
    private void ClosePart()
    {
        if(_gzip is null)return;_gzip.Dispose();_file!.Dispose();var p=Path.Combine(directory,_name);Parts.Add(new {file=_name,rows=_count,raw_bytes=_raw,raw_sha256=Convert.ToHexStringLower(_hash!.GetHashAndReset()),stored_bytes=new FileInfo(p).Length,stored_sha256=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(p)))});_hash.Dispose();_gzip=null;_file=null;_hash=null;
    }
    public void Dispose()=>ClosePart();
}
