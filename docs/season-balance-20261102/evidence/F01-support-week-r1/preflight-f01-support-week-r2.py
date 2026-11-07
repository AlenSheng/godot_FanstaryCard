from pathlib import Path
import datetime,hashlib,importlib.util,json,os,subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'f01-support-week-preflight-r2';private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-support-week-preflight-r2')
assert not out.exists() and not private.exists();out.mkdir();private.mkdir()
names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/tests/fixture_runtime.py']).decode().split('\0');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pin={n:sha(repo/n) for n in names if n and (repo/n).is_file()};(out/'source-pin.original.json').write_text(json.dumps(pin,indent=2)+'\n')
budget_paths=[repo/f'docs/season-balance-20261102/{item}-BUDGET.json' for item in ['F01','D03','B05']];budget_hashes={str(p):sha(p) for p in budget_paths}
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ)
for key in list(env):
    if key.startswith('FANTASYCARD_'):env[key]=''
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en')
command=['dotnet','build',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'-c','Release','--artifacts-path',str(private),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']
(out/'started.original.json').write_text(json.dumps(dict(parent_pid=os.getpid(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,reserve_GiB=2,startup_GiB=1,new_gameplay_cases=0),indent=2)+'\n')
r=guard.guarded_run(command,env=env,timeout=240,wait_seconds=30);(out/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-2400:]
binary=private/'bin/FantasyCard.Server.Tests/release';(out/'binary-manifest.original.json').write_text(json.dumps({p.relative_to(binary).as_posix():sha(p) for p in binary.rglob('*') if p.is_file()},indent=2)+'\n')
env.update(FANTASYCARD_RUN_F01_INPUTS='1',FANTASYCARD_F01_INPUT_OUTPUT=str(out),FANTASYCARD_RUN_D03_EFFICIENCY='1',FANTASYCARD_D03_PLAN=str(b/'d03-matched-armor-preflight-r2/plan.original.json'),FANTASYCARD_D03_PREFLIGHT_OUTPUT=str(out/'d03-inputs.original.json'))
methods=['SeasonFirstFortnightInputsTests.SupportedNovicesReorganizeOnlyAlreadyOwnedInitialCards','SeasonClassEfficiencyPilotTests.CandidateInputsAreLegalAndBothSpeedLayersAreValued','SeasonClassEfficiencyPilotTests.ExtendedBudgetRequiresExplicitMatchingApproval']
results=[]
for method in methods:
    command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.'+method,'-trx',str(out/(method+'.trx')),'-xml',str(out/(method+'.xml'))]
    r=guard.guarded_run(command,env=env,timeout=45,wait_seconds=30);(out/(method+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');results.append(dict(method=method,exit=r.returncode));assert r.returncode==0,(r.stdout+r.stderr)[-2000:]
assert all(sha(repo/n)==h for n,h in pin.items()) and all(sha(Path(p))==h for p,h in budget_hashes.items())
proof=dict(exit=0,build_exit=0,tests=results,actual_new_encounters=0,source_entries=len(pin),source_unchanged=True,budget_bytes_unchanged=True,private_build=str(private),no_product_files_changed=True,F01_used=255,D03_used=299,B05_used=330)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))

