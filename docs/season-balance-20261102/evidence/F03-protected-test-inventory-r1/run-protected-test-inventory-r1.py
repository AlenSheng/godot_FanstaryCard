from pathlib import Path
import hashlib,importlib.util,json,os,shutil

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-protected-test-inventory-r1';private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f03-test-metadata-r1')
assert not out.exists() and not private.exists();out.mkdir();private.mkdir()
source=b/'protected-test-metadata-inventory.cs';shutil.copyfile(source,private/'Program.cs');shutil.copyfile(source,out/'Program.cs')
(private/'Inventory.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
report=json.loads((b/'f03-protected-build-r2/result.json').read_bytes());suites=[Path(p) for p in report['test_assemblies']]
pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in suites};(out/'assembly-input-hashes.original.json').write_text(json.dumps(pins,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en')
r=guard.guarded_run(['dotnet','build',str(private/'Inventory.csproj'),'-c','Release','-m:1','-p:UseSharedCompilation=false','--verbosity','minimal'],env=env,timeout=120,wait_seconds=30)
(out/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-2000:]
r=guard.guarded_run(['dotnet',str(private/'bin/Release/net10.0/Inventory.dll'),str(out/'inventory.original.json'),*map(str,suites)],env=env,timeout=45,wait_seconds=30)
(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-1500:]
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in pins.items())
inventory=json.loads((out/'inventory.original.json').read_bytes());rows=inventory['rows'];assert rows and all(r['error'] is None for r in rows)
summary=dict(metadata_method_definitions=len(rows),skipUnless_definitions=sum('SkipUnless' in r['named'] for r in rows),skipWhen_definitions=sum('SkipWhen' in r['named'] for r in rows),
    unconditional_skip_definitions=sum('Skip' in r['named'] and 'SkipUnless' not in r['named'] and 'SkipWhen' not in r['named'] for r in rows),
    assembly_hashes_unchanged=True,attribute_instances_created=0,test_methods_invoked=0,new_gameplay_starts=0,
    method_definitions_not_discovered_theory_cases=True,production_changed=False)
(out/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
