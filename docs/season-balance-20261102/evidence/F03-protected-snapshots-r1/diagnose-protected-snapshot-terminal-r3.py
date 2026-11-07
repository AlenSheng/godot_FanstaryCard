from pathlib import Path
import importlib.util,json,os,shutil

b=Path(__file__).parent;repo=Path.cwd();old=b/'f03-protected-snapshot-r2';out=b/'f03-snapshot-terminal-diagnostic-r3';assert not out.exists();out.mkdir()
info=json.loads((old/'prepared.original.json').read_bytes());previous=Path(info['private'])/'original';private=Path(info['private']).with_name('f03-snapshot-terminal-diagnostic-r3');assert not private.exists();private.mkdir()
results=json.loads((old/'original-results.original.json').read_bytes());failed={r['id'] for r in results['results'] if not r['ok']};manifest=[r for r in json.loads((old/'inputs.original.json').read_bytes()) if r['id'] in failed];assert len(manifest)==11
(out/'inputs.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
source=(old/'Program.cs').read_text('utf-8');needle='if(!JsonNode.DeepEquals(JsonNode.Parse(typed),JsonNode.Parse(json))) throw new InvalidOperationException("Restored capture differs from original snapshot");'
replacement='''if(!JsonNode.DeepEquals(JsonNode.Parse(typed),JsonNode.Parse(json)))
        {
            var directory=Path.GetDirectoryName(args[1])!;
            File.WriteAllText(Path.Combine(directory,id+".before.json"),typed);
            File.WriteAllText(Path.Combine(directory,id+".after.json"),json);
            throw new InvalidOperationException("Restored capture differs from original snapshot");
        }'''
assert needle in source;source=source.replace(needle,replacement);(out/'Program.cs').write_text(source,encoding='utf-8');(private/'Program.cs').write_text(source,encoding='utf-8');shutil.copyfile(previous/'Probe.csproj',private/'Probe.csproj')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en')
command=['dotnet','build',str(private/'Probe.csproj'),'-c','Release','-m:1','-p:UseSharedCompilation=false','--verbosity','minimal'];r=guard.guarded_run(command,env=env,timeout=120,wait_seconds=30);(out/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-1600:]
command=['dotnet',str(private/'bin/Release/net10.0/Probe.dll'),str(out/'inputs.original.json'),str(out/'results.original.json')];r=guard.guarded_run(command,env=env,timeout=60,wait_seconds=30);(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==1
def diff(a,z,path=''):
    if isinstance(a,dict) and isinstance(z,dict):
        return [change for key in sorted(a.keys()|z.keys()) for change in (diff(a[key],z[key],path+'/'+key) if key in a and key in z else [dict(path=path+'/'+key,before=a.get(key),after=z.get(key))])]
    if isinstance(a,list) and isinstance(z,list) and len(a)==len(z):return [change for i,(v,w) in enumerate(zip(a,z)) for change in diff(v,w,path+'/'+str(i))]
    return [] if a==z else [dict(path=path,before=a,after=z)]
deltas=[]
for item in manifest:
    changes=diff(json.loads((out/(item['id']+'.before.json')).read_bytes()),json.loads((out/(item['id']+'.after.json')).read_bytes()))
    deltas.append(dict(id=item['id'],hero=item['primary_hero'],difficulty=item['difficulty'],changes=changes))
(out/'field-differences.derived.json').write_text(json.dumps(deltas,indent=2)+'\n');print(json.dumps(deltas))
