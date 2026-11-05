from pathlib import Path
import json,hashlib,importlib.util,os,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;root=base/'d03-entry-wire-r1';assert not (root/'result.json').exists();binary=base/'d03-formal16-server-r2/build/bin/FantasyCard.Server.Tests/debug'
pins={n:hashlib.sha256((binary/n).read_bytes()).hexdigest() for n in ['FantasyCard.Domain.dll','FantasyCard.Contracts.dll','Google.Protobuf.dll']};spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1');os.chdir(repo/'server')
r=guard.guarded_run(['dotnet','build',str(root/'ConfigWire.csproj'),'--artifacts-path',str(root/'build'),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal'],env=env,timeout=120,wait_seconds=180);(root/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print((r.stdout+r.stderr)[-1500:]);assert r.returncode==0
r=guard.guarded_run(['dotnet',str(root/'build/bin/ConfigWire/debug/ConfigWire.dll'),str(root/'data'),str(repo/'server/config/archive/season-v1-config-15/fantasycard.config.bytes')],env=env,timeout=60,wait_seconds=180);(root/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
cases=json.loads((root/'data/cases.json').read_bytes());assert [c['version'] for c in cases]==['season-v1-config-15','season-v1-config-16']
for c in cases:
 for suffix,key in [('.bundle','bundle_sha256'),('.envelope','envelope_sha256')]:assert hashlib.sha256((root/'data'/(c['name']+suffix)).read_bytes()).hexdigest()==c[key]
assert all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in pins.items());(root/'result.json').write_text(json.dumps({'exit':0,'cases':cases,'actual_typed_CSharp_serialization':True,'HTTP_network_claimed':False,'binary_inputs':pins,'new_C16_encounters':0},indent=2)+'\n');print('Original15/current16 real typed C# packets pinned')
