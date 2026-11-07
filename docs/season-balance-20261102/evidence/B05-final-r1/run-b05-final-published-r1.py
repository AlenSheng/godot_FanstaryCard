from pathlib import Path
import json,hashlib,subprocess,sys,importlib.util,os,time

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;build=base/'b05-final-local-build-r1';out=base/'b05-final-published-r1'
assert not out.exists();assert json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
budget=json.loads((repo/'docs/season-balance-20261102/evidence/B05/test-budget.json').read_bytes());assert budget['used']==291 and budget['remaining']==9
assert not (base/'b05-final-published-started.original.json').exists(),'Follow the existing final-nine handle; never start another full queue.'
out.mkdir();results=out/'results';results.mkdir();observations=out/'observations';assert not observations.exists()
binary=build/'build/bin/FantasyCard.Domain.Tests/debug';files={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()}
(out/'binary-manifest.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
command=['dotnet',str(binary/'FantasyCard.Domain.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Domain.Tests.Combat.SeasonResourceLoopTests.FinalNinePublishedR1RoutesKeepEveryDrawWithinItsPrintedAndPassiveBudget','-trx',str(results/'final-nine.trx'),'-xml',str(results/'final-nine.xml')]
started=dict(parent_pid=os.getpid(),started_at=time.time(),command=command,case_limit=9,prior_budget_used=291,maximum_budget=300,observations=str(observations),
             resource_guard_sha256=hashlib.sha256((repo/'client/tests/fixture_runtime.py').read_bytes()).hexdigest(),local_reserve_GiB=2,startup_GiB=1)
(base/'b05-final-published-started.original.json').write_text(json.dumps(started,indent=2)+'\n',encoding='utf-8');(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
error=None;r=None
try:r=guard.guarded_run(command,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='1',FANTASYCARD_B05_FINAL_DIR=str(observations)),timeout=240,wait_seconds=180)
except Exception as e:
 error={'type':type(e).__name__,'error':str(e),'output':str(getattr(e,'output',''))};(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n',encoding='utf-8')
if r is not None:(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
attempts=observations/'attempts.original.jsonl';count=len(attempts.read_text('utf-8').splitlines()) if attempts.exists() else 0;assert 0<=count<=9
proof=dict(exit=r.returncode if r is not None else None,error=error,new_started_routes=count,total_budget_used=291+count,budget_remaining=9-count,old_291_not_reset=True,
           source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in files.items()),
           full_old_matrix_started=False,capacity100_retest=False,cloud_modified=False,seconds=time.time()-started['started_at'])
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print((r.stdout+r.stderr)[-4000:] if r is not None else json.dumps(error));print(json.dumps(proof));assert r is not None and r.returncode==0 and count==9 and proof['source_unchanged'] and proof['binary_unchanged']
