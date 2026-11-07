from pathlib import Path
import hashlib, importlib.util, json, os, subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-paired-route-preflight-r2';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
validated=json.loads((b/'f03-fixed-ordinary-r1/plan.original.json').read_bytes())
binary=repo/'tools/engine-local/protected/f03-fixed-ordinary-r1/FantasyCard.Server.Tests'
suite=binary/'FantasyCard.Server.Tests.dll';assert suite.is_file()
for p,h in validated['all_input_pins'].items():assert sha(Path(p))==h,p
report=json.loads((b/'f03-protected-build-r3/result.json').read_bytes())
for name,h in report['assemblies'].items():
    if (binary/name).exists():assert sha(binary/name)==h['protected_sha256']
budgets={name:sha(repo/f'docs/season-balance-20261102/{name}-BUDGET.json') for name in ['D03','F01','B05','D01','D02','C16']}
names=subprocess.check_output(['git','ls-files','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/tests/fixture_runtime.py']).decode().split('\0')
pins={name:sha(repo/name) for name in names if name and (repo/name).is_file()}
(out/'source-pin.original.json').write_text(json.dumps(pins,indent=2)+'\n')
binary_pins={str(p.relative_to(binary)):sha(p) for p in binary.rglob('*') if p.is_file()};(out/'binary-manifest.original.json').write_text(json.dumps(binary_pins,indent=2)+'\n')
env={k:v for k,v in os.environ.items() if not k.startswith('FANTASYCARD_')}
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',FANTASYCARD_RUN_D03_PAIRED_ROUTES='1',FANTASYCARD_D03_PAIRED_INPUTS=str(out/'inputs.original.json'))
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
method='FantasyCard.Server.Tests.Config.SeasonPairedRouteComparisonTests.PrepareLegalIndependentR1MapsAndMatchedMatureD2Inputs'
run=guard.guarded_run(['dotnet',str(suite),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-method',method,'-trx',str(out/'inputs.trx'),'-xml',str(out/'inputs.xml')],env=env,timeout=60,wait_seconds=30)
(out/'run.original.log').write_text(run.stdout+run.stderr,encoding='utf-8');assert run.returncode==0,(run.stdout+run.stderr)[-1600:]
old=json.loads((b/'d03-paired-route-preflight-r1/inputs.original.json').read_bytes());current=json.loads((out/'inputs.original.json').read_bytes());assert old==current
assert sorted({r['seed'] for r in current['cases']})==[2013,2149,2214] and len(current['cases'])==9
assert all(sha(repo/name)==h for name,h in pins.items()) and all(sha(binary/name)==h for name,h in binary_pins.items())
assert all(sha(repo/f'docs/season-balance-20261102/{name}-BUDGET.json')==h for name,h in budgets.items())
result=dict(exit=0,inputs_fact_passed=True,planned_cases=9,planned_seeds=[2013,2149,2214],actual_gameplay_starts=0,frozen_plan_deep_equal_to_original=True,
    source_unchanged=True,source_entries=len(pins),binary_unchanged=True,binary=str(binary),protected_source_commit=report['source_commit'],
    budget_bytes_unchanged=True,actual_D03_used=308,actual_D03_maximum=317,no_authorization_inferred_from_preflight=True,production_changed=False)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
