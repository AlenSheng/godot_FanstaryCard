from pathlib import Path
import hashlib, importlib.util, json, os

repo=Path.cwd(); base=Path(__file__).parent; root=base/'e01-discard-wire-r1'; assert not (root/'result.json').exists()
binary=base/'e01-discard-api-build-r1/build/bin/FantasyCard.Server.Tests/debug'
pins={n:hashlib.sha256((binary/n).read_bytes()).hexdigest() for n in ['FantasyCard.Domain.dll','FantasyCard.Contracts.dll','Google.Protobuf.dll']}
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py'); guard=importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1')
for label,command in [('build',['dotnet','build',str(root/'ConfigWire.csproj'),'--artifacts-path',str(root/'build'),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']),('run',['dotnet',str(root/'build/bin/ConfigWire/debug/ConfigWire.dll'),str(root/'data')])]:
    result=guard.guarded_run(command,env=env,timeout=120,wait_seconds=180);(root/(label+'.original.log')).write_text(result.stdout+result.stderr,encoding='utf-8');print((result.stdout+result.stderr)[-1500:]);assert result.returncode==0
cases=json.loads((root/'data/cases.json').read_bytes());assert [x['name'] for x in cases]==['active','legacy']
for case in cases:
    for suffix in ['request','response']:assert hashlib.sha256((root/'data'/(case['name']+'.'+suffix)).read_bytes()).hexdigest()==case[suffix+'_sha256']
assert all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in pins.items())
(root/'result.json').write_text(json.dumps(dict(exit=0,actual_CSharp_typed_discard_cases=cases,binary_inputs=pins,real_HTTP_network_claimed=False,new_game_matches=0),indent=2)+'\n')
