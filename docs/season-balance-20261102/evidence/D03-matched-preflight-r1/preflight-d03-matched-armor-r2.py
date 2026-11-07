from pathlib import Path
import datetime,hashlib,importlib.util,json,os,subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-matched-armor-preflight-r2'
private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\d03-matched-armor-preflight-r2')
assert not out.exists() and not private.exists();out.mkdir();private.mkdir()
proposal=json.loads((b/'d03-matched-armor-proposal-r1.original.json').read_bytes())
budget_path=repo/'docs/season-balance-20261102/D03-BUDGET.json';before=budget_path.read_bytes();budget=json.loads(before)
assert budget['used']==299 and budget['maximum']==300 and budget['current_handle'] is None
(out/'budget.original.json').write_bytes(before)
cases=[dict(id=f'D03-MATCHED17-{hero}-{seed}',hero=hero,deck='flow-loop',armor='counter-balanced',seed=seed,policy='rate-budget-half-v1') for hero in proposal['heroes'] for seed in proposal['seeds']]
plan=dict(prior_used=299,maximum=308,config_version='season-v1-config-17',cases=cases,execution_approved=False,
    original_boss_seconds=[75,120],effective_boss_seconds=[63.75,120],class_ratio_limit=1.15,source_proposal_sha256=hashlib.sha256((b/'d03-matched-armor-proposal-r1.original.json').read_bytes()).hexdigest(),
    preflight_only=True,no_encounter_method_selected=True,approval_required_before_actual_execution=True)
(out/'plan.original.json').write_text(json.dumps(plan,indent=2)+'\n')
names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/tests/fixture_runtime.py']).decode().split('\0')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pin={n:sha(repo/n) for n in names if n and (repo/n).is_file()};(out/'source-pin.original.json').write_text(json.dumps(pin,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
env=dict(os.environ)
for key in list(env):
    if key.startswith('FANTASYCARD_'):env[key]=''
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1')
command=['dotnet','build',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'-c','Release','--artifacts-path',str(private),'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal']
(out/'started.original.json').write_text(json.dumps(dict(parent_pid=os.getpid(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,new_gameplay_cases=0,reserve_GiB=2,startup_GiB=1),indent=2)+'\n')
r=guard.guarded_run(command,env=env,timeout=240,wait_seconds=30);(out/'build.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout+r.stderr)[-1800:]
binary=private/'bin/FantasyCard.Server.Tests/release';dll=binary/'FantasyCard.Server.Tests.dll'
(out/'binary-manifest.original.json').write_text(json.dumps({p.relative_to(binary).as_posix():sha(p) for p in binary.rglob('*') if p.is_file()},indent=2)+'\n')
env.update(FANTASYCARD_RUN_D03_EFFICIENCY='1',FANTASYCARD_D03_PLAN=str(out/'plan.original.json'),FANTASYCARD_D03_PREFLIGHT_OUTPUT=str(out/'inputs.original.json'),FANTASYCARD_D03_BUDGET_FILE=str(budget_path))
results=[]
for method in ['CandidateInputsAreLegalAndBothSpeedLayersAreValued','ExtendedBudgetRequiresExplicitMatchingApproval']:
    command=['dotnet',str(dll),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method',f'FantasyCard.Server.Tests.Config.SeasonClassEfficiencyPilotTests.{method}','-trx',str(out/(method+'.trx')),'-xml',str(out/(method+'.xml'))]
    r=guard.guarded_run(command,env=env,timeout=45,wait_seconds=30);(out/(method+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');results.append(dict(method=method,exit=r.returncode));assert r.returncode==0,(r.stdout+r.stderr)[-1800:]
assert budget_path.read_bytes()==before and all(sha(repo/n)==h for n,h in pin.items())
assert not (out/'observations').exists()
proof=dict(build_exit=0,tests=results,declared_unstarted_cases=9,actual_new_encounters=0,source_entries=len(pin),source_unchanged=True,budget_bytes_unchanged=True,D03_used=299,D03_maximum=300,D03_remaining=1,
    B05_new=0,F01_new=0,execution_authorization_granted=False,production_changed=False,private_build=str(private),no_product_files_changed=True)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))

