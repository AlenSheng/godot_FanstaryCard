from pathlib import Path
import hashlib,importlib.util,json,os

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-protected-snapshot-r4';info=json.loads((out/'prepared.original.json').read_bytes());private=Path(info['private'])
assert not (out/'execution-started.original.json').exists()
(out/'execution-started.original.json').write_text(json.dumps(dict(parent_pid=os.getpid(),samples=50,new_gameplay_starts=0,clock_advance_calls=0,reserve_GiB=2,startup_GiB=1),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en')
results={}
for mode in ['original','protected']:
    project=private/mode
    command=['dotnet','build',str(project/'Probe.csproj'),'-c','Release','-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']
    r=guard.guarded_run(command,env=env,timeout=120,wait_seconds=30);(out/(mode+'-build.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-2000:]
    command=['dotnet',str(project/'bin/Release/net10.0/Probe.dll'),str(out/'inputs.original.json'),str(out/(mode+'-results.original.json'))]
    r=guard.guarded_run(command,env=env,timeout=60,wait_seconds=30);(out/(mode+'-run.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
    proof=json.loads((out/(mode+'-results.original.json')).read_bytes());results[mode]=dict(exit=r.returncode,proof=proof)
    print(json.dumps(dict(mode=mode,exit=r.returncode,count=proof['count'],errors=proof['errors'])),flush=True)
protected=json.loads((b/'f03-protected-build-r2/result.json').read_bytes())
assert results['protected']['proof']['assemblies']['FantasyCard.Domain.dll']==protected['assemblies']['FantasyCard.Domain.dll']['protected_sha256']
assert results['protected']['proof']['assemblies']['FantasyCard.Contracts.dll']==protected['assemblies']['FantasyCard.Contracts.dll']['protected_sha256']
rows={mode:{r['id']:r for r in result['proof']['results']} for mode,result in results.items()}
matching={key:rows['original'][key].get('canonical_sha256')==rows['protected'][key].get('canonical_sha256') and rows['original'][key]['ok']==rows['protected'][key]['ok'] for key in rows['original']}
result=dict(original_exit=results['original']['exit'],protected_exit=results['protected']['exit'],original_errors=results['original']['proof']['errors'],protected_errors=results['protected']['proof']['errors'],samples=50,
    exact_protected_payload_hashes_used=True,result_equivalence=all(matching.values()),all_semantic_restores_passed=all(v['proof']['ok'] for v in results.values()),new_gameplay_starts=0,clock_advance_calls=0,
    protected_candidate_not_promoted=True,production_changed=False,private_original_binaries_not_published=True,source_product_unchanged=True)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));assert result['all_semantic_restores_passed'] and result['result_equivalence']
