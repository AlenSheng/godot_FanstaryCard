from pathlib import Path
import json,hashlib,subprocess,sys,importlib.util,os,time

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;build=base/'c16-calibration-build-r4';out=base/'c16-calibration-pilot-r2';assert not out.exists()
assert json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
current=repo/'docs/season-balance-20261102/C16-BUDGET.json';assert current.exists();current_budget=json.loads(current.read_bytes());assert current_budget['used']==121 and current_budget['remaining']==179 and current_budget['current_handle'] is None
prior=json.loads((base/'c16-calibration-pilot-r1/result.json').read_bytes());assert prior['exit']==1 and prior['new_started_encounters']==0
budget=json.loads((repo/'docs/season-balance-20261102/evidence/C16-themes/comparison/budget-checkpoint.json').read_bytes());assert budget['attempts_committed']==121 and budget['remaining']==179
out.mkdir();results=out/'results';results.mkdir();observations=out/'observations';assert not observations.exists()
binary=build/'build/bin/FantasyCard.Server.Tests/debug';binaries={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()};(out/'binary-manifest.json').write_text(json.dumps(binaries,indent=2)+'\n')
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonThemeCalibrationTests.SameFormalThemeSixDifficultiesThreeClassesRecordAllActualResources','-trx',str(results/'pilot.trx'),'-xml',str(results/'pilot.xml')]
started=dict(parent_pid=os.getpid(),started_at=time.time(),command=command,prior_used=121,pilot_limit=18,maximum=300,observations=str(observations),local_reserve_GiB=2,startup_GiB=1)
(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n')
current.write_text(json.dumps(dict(item='C16',used=121,remaining=179,reserved_current_pilot=18,current_handle=started,prior_budget='evidence/C16-themes/comparison/budget-checkpoint.json',B05_budget=300,B05_additional_runs_forbidden=True),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=None;error=None
try:r=guard.guarded_run(command,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_C16_CALIBRATION='1',FANTASYCARD_C16_CALIBRATION_DIR=str(observations),FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=240,wait_seconds=180)
except Exception as e:
 error={'type':type(e).__name__,'error':str(e),'output':str(getattr(e,'output',''))};(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
if r is not None:(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
attempts=observations/'attempts.original.jsonl';count=len(attempts.read_text('utf-8').splitlines()) if attempts.exists() else 0;assert 0<=count<=18
proof=dict(exit=r.returncode if r else None,error=error,new_started_encounters=count,total_budget_used=121+count,budget_remaining=179-count,
           source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in binaries.items()),
           old_comparison_not_repeated=True,B05_new_attempts=0,cloud_modified=False,production_modified=False,seconds=time.time()-started['started_at'])
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
current.write_text(json.dumps(dict(item='C16',used=121+count,remaining=179-count,maximum=300,current_handle=None,pilot_result=str(out/'result.json'),prior_121_immutable='evidence/C16-themes/comparison/budget-checkpoint.json',B05_budget=300,B05_additional_runs_forbidden=True),indent=2)+'\n')
print((r.stdout+r.stderr)[-4200:] if r else json.dumps(error));print(json.dumps(proof));assert r and r.returncode==0 and count==18 and proof['source_unchanged'] and proof['binary_unchanged']
