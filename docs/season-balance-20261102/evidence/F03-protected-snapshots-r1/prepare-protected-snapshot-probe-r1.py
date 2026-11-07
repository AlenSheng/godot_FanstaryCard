from pathlib import Path
import hashlib,json,subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-protected-snapshot-r1';assert not out.exists();out.mkdir();inputs=out/'inputs';inputs.mkdir()
assert not subprocess.check_output(['git','diff','--name-only','075d0c4eb47ab834c300aa45347e00c30444dd56','HEAD','--','server/src/FantasyCard.Domain','server/src/FantasyCard.Contracts','server/src/FantasyCard.Server'])
protected=json.loads((b/'f03-protected-build-r2/result.json').read_bytes());package=Path(protected['output'])
assert all(hashlib.sha256((package/n).read_bytes()).hexdigest()==v['sha256'] for n,v in protected['package_files'].items())
selected=[];coverage=set()
def add(snapshot,source,kind,seed,line=None):
    primary=next(p for p in snapshot['Players'] if not p['IsBot'])
    key=(snapshot['Season']['Difficulty'],primary['HeroClass'],kind,primary['Phase'])
    if key in coverage:return
    coverage.add(key);selected.append(dict(snapshot=snapshot,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_line=line,kind=kind,seed=seed,
        primary_hero=primary['HeroClass'],primary_phase=primary['Phase'],difficulty=snapshot['Season']['Difficulty']))
root=b/'f01-calendar-r1/observations'
for p in sorted(root.rglob('admitted.original.json')):
    admission=json.loads(p.read_bytes());initial=admission['InitialState'];add(initial,p,'initial',admission['ActualSeed'])
    terminal=p.parent/'terminal-or-censored.original.json';add(json.loads(terminal.read_bytes()),terminal,'terminal',admission['ActualSeed'])
events=b/'d03-formal17-continuation-r1/observations/events.original.jsonl'
for n,line in enumerate(events.read_text('utf-8').splitlines(),1):
    e=json.loads(line)
    if e.get('kind')=='recovered':add(e['snapshot'],events,'inflight-'+e['stage'],0,n)
assert 20<=len(selected)<=100
selected=selected[:50]
manifest=[]
for index,item in enumerate(selected):
    snapshot=item.pop('snapshot');path=inputs/f'{index:03}.json';raw=json.dumps(snapshot,separators=(',',':')).encode();path.write_bytes(raw)
    item.update(id=f'{index:03}',path=str(path),sha256=hashlib.sha256(raw).hexdigest(),extracted_input_not_a_new_game_save=True);manifest.append(item)
(out/'inputs.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
source='''using System.Text.Json;
using System.Text.Json.Nodes;
using System.Security.Cryptography;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

var inputs=JsonDocument.Parse(File.ReadAllText(args[0])).RootElement;
var config=GameConfigCatalog.Current;
var catalog=CombatCardCatalog.Create(config);
var results=new List<object>();
var errors=0;
foreach(var input in inputs.EnumerateArray())
{
    var id=input.GetProperty("id").GetString();
    try
    {
        var raw=File.ReadAllBytes(input.GetProperty("path").GetString()!);
        if(Convert.ToHexStringLower(SHA256.HashData(raw))!=input.GetProperty("sha256").GetString()) throw new InvalidOperationException("Input SHA mismatch");
        var snapshot=JsonSerializer.Deserialize<BattleRoomSnapshot>(raw) ?? throw new InvalidOperationException("Null snapshot");
        var typed=JsonSerializer.Serialize(snapshot);
        if(!JsonNode.DeepEquals(JsonNode.Parse(raw),JsonNode.Parse(typed))) throw new InvalidOperationException("Typed JSON surface differs from source snapshot");
        var room=BattleRoom.Restore(snapshot,catalog,input.GetProperty("seed").GetInt32());
        var restored=room.Capture();
        var json=JsonSerializer.Serialize(restored);
        if(!JsonNode.DeepEquals(JsonNode.Parse(typed),JsonNode.Parse(json))) throw new InvalidOperationException("Restored capture differs from original snapshot");
        if(room.Elapsed!=snapshot.Elapsed || room.Revision!=snapshot.Revision) throw new InvalidOperationException("Restore advanced state");
        results.Add(new{id,ok=true,revision=room.Revision,elapsed=room.Elapsed,canonical_sha256=Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(json)))});
    }
    catch(Exception error)
    {
        errors++;
        results.Add(new{id,ok=false,type=error.GetType().FullName,message=error.Message});
    }
}
var assemblies=new Dictionary<string,string>();
foreach(var assembly in new[]{typeof(BattleRoom).Assembly,typeof(FantasyCard.Contracts.Players.HeroClassDto).Assembly})
    assemblies[Path.GetFileName(assembly.Location)]=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(assembly.Location)));
File.WriteAllText(args[1],JsonSerializer.Serialize(new{ok=errors==0,errors,count=results.Count,config.Version,config.ContentHash,assemblies,results,new_gameplay_starts=0,clock_advance_calls=0},new JsonSerializerOptions{WriteIndented=true}));
return errors==0?0:1;
'''
(out/'Program.cs').write_text(source,encoding='utf-8')
private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f03-snapshot-probe-r1');assert not private.exists();private.mkdir()
baseline=Path(json.loads((b/'d03-paired-route-preflight-r1/result.json').read_bytes())['private_build'])/'bin/FantasyCard.Server.Tests/release'
for mode,reference in [('original',baseline),('protected',package)]:
    project=private/mode;project.mkdir();(project/'Program.cs').write_text(source,encoding='utf-8')
    refs=''.join(f'<Reference Include="{name[:-4]}"><HintPath>{(reference/name).as_posix()}</HintPath><Private>true</Private></Reference>' for name in ['FantasyCard.Contracts.dll','FantasyCard.Domain.dll','Google.Protobuf.dll'])
    (project/'Probe.csproj').write_text(f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup>{refs}</ItemGroup></Project>')
proof=dict(private=str(private),package=str(package),original_reference=str(baseline),samples=len(manifest),input_surface_coverage=[dict(difficulty=r['difficulty'],hero=r['primary_hero'],kind=r['kind'],phase=r['primary_phase']) for r in manifest],
    product_source_unchanged_since_protected_build=True,package_hashes_verified=True,new_gameplay_starts=0,no_clock_advance=True,no_PG_or_cloud_operations=True)
(out/'prepared.original.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k!='input_surface_coverage'}))
