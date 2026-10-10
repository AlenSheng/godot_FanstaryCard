using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

internal static class TuningRecoveryExperiment
{
    private static readonly string[] Alternatives=["ET-WOOD-G","ET-EARTH-G","ET-METAL-G"];
    private static readonly string[] Groups=["O1","O6","E1","BOSS"];
    private static readonly string[] Common=["C01","C02","C03","C04","C05","C06","C07","C08","C09","C10","C11","C15","ET-FIRE-G","ET-WATER-G"];
    public static int Run(string[] args)
    {
        string Option(string name,string fallback) { var index=Array.IndexOf(args,name);return index>=0 && index+1<args.Length ? args[index+1] : fallback; }
        var sha=Option("--source-sha","");var output=Path.GetFullPath(Option("--output",""));var hero=Enum.Parse<HeroClass>(Option("--hero","Mage"));
        var group=Option("--group","O1");var alternative=Option("--replacement","ET-WOOD-G");var block=int.Parse(Option("--block-index","0"),CultureInfo.InvariantCulture);var samples=int.Parse(Option("--samples","3"),CultureInfo.InvariantCulture);
        if (!Regex.IsMatch(sha,"^[0-9a-f]{40}$") || Directory.Exists(output) || !Enum.IsDefined(hero) || !Groups.Contains(group) || !Alternatives.Contains(alternative) || block is <0 or >2 || samples is <3 or >1000)
            throw new ArgumentException("Exact source, frozen bounded stratum and new output required.");
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.CreatePrototype();var prefix=hero switch { HeroClass.Mage=>"MAG",HeroClass.Priest=>"PRI",_=>"GUA" };
        var baseline=Common.Concat(Enumerable.Range(1,6).Select(i=>$"{prefix}-{i:D2}")).ToArray();var candidate=baseline.Select(id=>id=="ET-WATER-G" ? alternative : id).ToArray();
        CombatExperience.ValidateDeck(config,hero,baseline);
        CombatExperience.ValidateDeck(config,hero,candidate);
        PairedDeckBudget.Validate(config,hero,baseline,candidate);Directory.CreateDirectory(output);var start=420001+1000*block;
        File.WriteAllText(Path.Combine(output,"manifest.json"),JsonSerializer.Serialize(new { schema="actual_tuning_recovery_experiment_v1",source_sha=sha,hero=hero.ToString(),group,alternative,block_index=block,seed_start=start,samples,baseline_deck=baseline,candidate_deck=candidate,weapon_level=0,card_level=0,equipment="Empty",strategy="basic",cutoff_seconds=600,candidate_activation=false,config_version=config.Version,config_sha256=Hash(JsonSerializer.SerializeToUtf8Bytes(config)),card_definitions=config.Cards,paired_budget_guard_passed=true }));
        using var events=new EventParts(output);var counters=new Dictionary<string,long>(StringComparer.Ordinal);var rows=0;var errors=0;long rawBytes=0;using var rawHash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var rawPath=Path.Combine(output,"encounters.jsonl.gz");
        using (var file=new FileStream(rawPath,FileMode.CreateNew))
        using (var gzip=new GZipStream(file,CompressionLevel.Fastest))
        for (var seed=start;seed<start+samples;seed++)
        foreach (var changed in new[] {false,true})
        {
            var row=CombatExperience.Simulate(config,catalog,hero,alternative,changed ? candidate : baseline,group,"basic",changed ? "SingleGreenReplacement" : "BaselineGreenWater",config.Numerics,seed,block,600,0,marginalAudit:true,tuningObserver:cast=>
            {
                events.Write(cast);var arm=cast.Profile+"/";Increment(counters,arm+"all_casts");
                Increment(counters,arm+"T01_"+(cast.Oracle.FirstEligibleIsTuning ? "applicable" : "not_applicable"));
                Increment(counters,arm+"T02_"+(cast.Oracle.SameCoreTuningWithCounter ? "applicable" : "not_applicable"));
                Increment(counters,arm+"T03_"+(cast.Oracle.RawConflictHeal>0 ? "applicable" : "not_applicable"));
                if (cast.Oracle.OrdinaryAndConflict) Increment(counters,arm+"ordinary_and_conflict");
                if (cast.Oracle.IncorrectPriestConflictHeal!=cast.Oracle.ConflictHeal) Increment(counters,arm+"incorrect_priest_multiplier_counterexample");
                if (!cast.Passed) Increment(counters,arm+"mismatches");
            });
            if (row.Outcome=="Error")errors++;
            if (events.BudgetExceeded)throw new InvalidOperationException("Event budget reached; all existing original evidence retained.");
            var bytes=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(row)+"\n");rawBytes+=bytes.Length;
            if (rawBytes>128*1024*1024)throw new InvalidOperationException("Encounter raw budget exceeded; partial evidence retained.");
            gzip.Write(bytes);rawHash.AppendData(bytes);rows++;
        }
        events.Dispose();var passed=errors==0 && rows==samples*2 && !counters.Keys.Any(k=>k.EndsWith("mismatches",StringComparison.Ordinal));
        var summary=new {passed,source_sha=sha,rows,errors,hero=hero.ToString(),group,alternative,block_index=block,seed_start=start,samples,raw_bytes=rawBytes,raw_sha256=Convert.ToHexStringLower(rawHash.GetHashAndReset()),stored_bytes=new FileInfo(rawPath).Length,stored_sha256=Hash(File.ReadAllBytes(rawPath)),case_denominators=counters,event_parts=events.Parts,actual_casts=events.Count,full_experiment=samples==1000,required_cases_accepted=false,main_acceptance_granted=false};
        File.WriteAllText(Path.Combine(output,"summary.json"),JsonSerializer.Serialize(summary));Console.WriteLine(JsonSerializer.Serialize(summary));return passed ? 0 : 1;
    }
    private static void Increment(Dictionary<string,long> counters,string key)=>counters[key]=counters.GetValueOrDefault(key)+1;
    private static string Hash(byte[] bytes)=>Convert.ToHexStringLower(SHA256.HashData(bytes));

    private sealed class EventParts(string output) : IDisposable
    {
        public List<object> Parts {get;}=[];
        public long Count {get;private set;}
        public bool BudgetExceeded {get;private set;}
        private long _totalBytes;
        private long _partBytes;
        private long _partCount;
        private string? _path;
        private GZipStream? _gzip;
        private IncrementalHash? _hash;
        public void Write(TuningRecoveryCast value)
        {
            var bytes=Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value)+"\n");
            if (_totalBytes+bytes.Length>2147483648L)
            {
                BudgetExceeded=true;
                throw new InvalidOperationException("Event raw budget exceeded; original partial parts retained.");
            }
            if (_gzip is null || _partBytes+bytes.Length>128*1024*1024)
            {
                Close();_path=Path.Combine(output,$"contract-events-{Parts.Count:D3}.jsonl.gz");_gzip=new(new FileStream(_path,FileMode.CreateNew),CompressionLevel.Fastest);_hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);_partBytes=0;_partCount=0;
            }
            _gzip.Write(bytes);_hash!.AppendData(bytes);_partBytes+=bytes.Length;_totalBytes+=bytes.Length;_partCount++;Count++;
        }
        private void Close()
        {
            if (_gzip is null)return;_gzip.Dispose();_gzip=null;var hash=Convert.ToHexStringLower(_hash!.GetHashAndReset());_hash.Dispose();_hash=null;
            Parts.Add(new {path=Path.GetFileName(_path),events=_partCount,raw_bytes=_partBytes,raw_sha256=hash,stored_bytes=new FileInfo(_path!).Length,stored_sha256=Hash(File.ReadAllBytes(_path!))});
        }
        public void Dispose()=>Close();
    }
}
