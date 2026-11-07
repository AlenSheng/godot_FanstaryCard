from pathlib import Path
import datetime,hashlib,importlib.util,json,os,subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-paired-route-preflight-r1';private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\d03-paired-route-preflight-r1')
assert not out.exists() and not private.exists();out.mkdir();private.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/tests/fixture_runtime.py']).decode().split('\0')
pin={n:sha(repo/n) for n in names if n and (repo/n).is_file()};(out/'source-pin.original.json').write_text(json.dumps(pin,indent=2)+'\n')
budgets={n:sha(repo/f'docs/season-balance-20261102/{n}-BUDGET.json') for n in ['D03','F01','B05']}
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ)
for key in list(env):
    if key.startswith('FANTASYCARD_'):env[key]=''
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1')
command=['dotnet','build',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'-c','Release','--artifacts-path',str(private),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']
(out/'started.original.json').write_text(json.dumps(dict(parent_pid=os.getpid(),command=command,reserve_GiB=2,startup_GiB=1,actual_gameplay_starts=0,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')
r=guard.guarded_run(command,env=env,timeout=240,wait_seconds=30);(out/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-2200:]
binary=private/'bin/FantasyCard.Server.Tests/release';(out/'binary-manifest.original.json').write_text(json.dumps({p.relative_to(binary).as_posix():sha(p) for p in binary.rglob('*') if p.is_file()},indent=2)+'\n')
env.update(FANTASYCARD_RUN_D03_PAIRED_ROUTES='1',FANTASYCARD_D03_PAIRED_INPUTS=str(out/'inputs.original.json'))
method='FantasyCard.Server.Tests.Config.SeasonPairedRouteComparisonTests.PrepareLegalIndependentR1MapsAndMatchedMatureD2Inputs'
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-method',method,'-trx',str(out/'inputs.trx'),'-xml',str(out/'inputs.xml')]
r=guard.guarded_run(command,env=env,timeout=60,wait_seconds=30);(out/'inputs.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-2000:]
assert all(sha(repo/n)==h for n,h in pin.items()) and all(sha(repo/f'docs/season-balance-20261102/{n}-BUDGET.json')==h for n,h in budgets.items())
inputs=json.loads((out/'inputs.original.json').read_bytes());assert len(inputs['cases'])==9 and not inputs['execution_authorized_by_preflight']
proof=dict(exit=0,private_build=str(private),inputs_fact_passed=True,planned_cases=9,planned_seeds=sorted({r['seed'] for r in inputs['cases']}),actual_gameplay_starts=0,source_unchanged=True,source_entries=len(pin),budget_bytes_unchanged=True,actual_D03_maximum=308,proposed_maximum=317,no_user_authorization_inferred=True,production_changed=False)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
