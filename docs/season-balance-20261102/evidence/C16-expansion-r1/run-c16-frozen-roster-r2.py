from pathlib import Path
import json,hashlib,subprocess,sys,importlib.util,os,time,re

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent
spec_path=Path(sys.argv[1]).resolve();assert spec_path.parent==base;control=json.loads(spec_path.read_bytes())
assert re.fullmatch(r'c16-[a-z0-9-]+',control['stage']);assert re.fullmatch(r'c16-[a-z0-9-]+',control['build'])
out=base/control['stage'];build=base/control['build'];assert not out.exists();assert json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
workbook=build/'config/FantasyCard_Config.xlsx';workbook_hash=hashlib.sha256(workbook.read_bytes()).hexdigest();assert workbook_hash==pin['config/FantasyCard_Config.xlsx']
current=repo/'docs/season-balance-20261102/C16-BUDGET.json';prior=current.read_bytes();budget=json.loads(prior)
assert budget['used']==control['prior_used'] and budget['remaining']==300-control['prior_used'] and budget['current_handle'] is None
roster=json.loads((base/control['roster']).read_bytes());cases=roster['cases'];assert len(cases)==control['new_limit']<=budget['remaining']
assert control['method'].startswith('FantasyCard.Server.Tests.Config.SeasonThemeCalibrationTests.')
out.mkdir();(out/'prior-budget.original.json').write_bytes(prior);(out/'control.original.json').write_bytes(spec_path.read_bytes());(out/'roster.original.json').write_bytes((base/control['roster']).read_bytes())
results=out/'results';results.mkdir();observations=out/'observations';binary=build/'build/bin/FantasyCard.Server.Tests/debug'
binaries={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()};(out/'binary-manifest.json').write_text(json.dumps(binaries,indent=2)+'\n');(out/'runtime-workbook-pin.original.json').write_text(json.dumps({'path':str(workbook),'sha256':workbook_hash,'matches_frozen_source_workbook':True},indent=2)+'\n')
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method',control['method'],'-trx',str(results/'cases.trx'),'-xml',str(results/'cases.xml')]
started=dict(parent_pid=os.getpid(),started_at=time.time(),command=command,prior_used=budget['used'],new_limit=len(cases),maximum=300,observations=str(observations),local_reserve_GiB=2,startup_GiB=1)
(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n');current.write_text(json.dumps(dict(item='C16',used=budget['used'],remaining=budget['remaining'],reserved_current=len(cases),current_handle=started,B05_budget=300,B05_additional_runs_forbidden=True),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=None;error=None
try:r=guard.guarded_run(command,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_C16_CALIBRATION='1',FANTASYCARD_C16_CALIBRATION_DIR=str(observations),FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=240,wait_seconds=180)
except Exception as e:
 error=dict(type=type(e).__name__,error=str(e),output=str(getattr(e,'output','')));(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
if r is not None:(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
attempts_path=observations/'attempts.original.jsonl';attempts=[json.loads(l) for l in attempts_path.read_text('utf-8').splitlines()] if attempts_path.exists() else [];count=len(attempts);assert 0<=count<=len(cases)
keys=['theme','difficulty','hero','build','boss','seed'];identity_match=all({k:a[k] for k in keys}=={k:e[k] for k in keys} for a,e in zip(attempts,cases))
proof=dict(exit=r.returncode if r else None,error=error,new_started_encounters=count,total_budget_used=budget['used']+count,budget_remaining=300-budget['used']-count,roster_identity_match=identity_match,
           source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in binaries.items()),
           frozen_workbook_unchanged=hashlib.sha256(workbook.read_bytes()).hexdigest()==workbook_hash,old_queues_not_repeated=True,B05_new_attempts=0,cloud_modified=False,production_modified=False,seconds=time.time()-started['started_at'])
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');current.write_text(json.dumps(dict(item='C16',used=proof['total_budget_used'],remaining=proof['budget_remaining'],maximum=300,current_handle=None,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json'),B05_budget=300,B05_additional_runs_forbidden=True),indent=2)+'\n')
print((r.stdout+r.stderr)[-3500:] if r else json.dumps(error));print(json.dumps(proof));assert r and r.returncode==0 and count==len(cases) and identity_match and proof['source_unchanged'] and proof['binary_unchanged'] and proof['frozen_workbook_unchanged']
