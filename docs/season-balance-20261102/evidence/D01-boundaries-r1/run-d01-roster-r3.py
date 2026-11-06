from pathlib import Path
import hashlib, importlib.util, json, os, re, subprocess, sys, time

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent
family=sys.argv[1];assert family in ['growth','groups','effects','boxelements']
build=base/'d01-preflight-r2';assert json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
roster_path=base/('d01-'+family+'-roster-r1.original.json');roster=json.loads(roster_path.read_bytes());cases=roster['cases']
budget_path=repo/'docs/season-balance-20261102/D01-BUDGET.json';prior=budget_path.read_bytes();budget=json.loads(prior)
assert budget['used']==roster['prior_used'] and budget['current_handle'] is None and len(cases)<=300-budget['used']
assert json.loads((repo/'docs/season-balance-20261102/B05-BUDGET.json').read_bytes())['used']==300
assert json.loads((repo/'docs/season-balance-20261102/C16-BUDGET.json').read_bytes())['used']==298
out=base/('d01-'+family+'-r1');assert not out.exists();out.mkdir()
(out/'prior-budget.original.json').write_bytes(prior);(out/'roster.original.json').write_bytes(roster_path.read_bytes())
binary=build/'build/bin/FantasyCard.Server.Tests/debug';binaries={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()}
(out/'binary-manifest.original.json').write_text(json.dumps(binaries,indent=2)+'\n');results=out/'results';results.mkdir()
workbook=build/'config/FantasyCard_Config.xlsx';workbook_hash=hashlib.sha256(workbook.read_bytes()).hexdigest();assert workbook_hash==pin['config/FantasyCard_Config.xlsx']
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonCombatBoundaryMatrixTests.DeclaredBoundaryEncountersPreserveCombatResourcesAndMonsterCards','-trx',str(results/'cases.trx'),'-xml',str(results/'cases.xml')]
observations=out/'observations';started=dict(parent_pid=os.getpid(),started_at=time.time(),command=command,prior_used=budget['used'],planned=len(cases),local_reserve_GiB=2,startup_GiB=1)
(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n');budget_path.write_text(json.dumps(dict(item='D01',used=budget['used'],remaining=300-budget['used'],maximum=300,reserved_current=len(cases),current_handle=started),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=None;error=None
try:
 r=guard.guarded_run(command,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_D01_BOUNDARIES='1',FANTASYCARD_D01_PLAN=str(out/'roster.original.json'),FANTASYCARD_D01_OUTPUT=str(observations),FANTASYCARD_RUN_C16_CALIBRATION='',FANTASYCARD_C16_REUSE_PREFLIGHT='',FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=300,wait_seconds=180)
except Exception as e:
 error=dict(type=type(e).__name__,error=str(e),output=str(getattr(e,'output','')));(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
if r is not None:(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
attempts_path=observations/'attempts.original.jsonl';attempts=[json.loads(x) for x in attempts_path.read_text('utf-8').splitlines()] if attempts_path.exists() else []
expected=[dict(zip(['Id','Family','Hero','Growth','Difficulty','Group','Element','MonsterCards','HpPercent','Variant','Seed'],[c[k] for k in ['id','family','hero','growth','difficulty','group','element','monster_cards','hp_percent','variant','seed']])) for c in cases]
assert 0<=len(attempts)<=len(cases);identity=all(a==e for a,e in zip(attempts,expected))
proof=dict(exit=r.returncode if r else None,error=error,started_encounters=len(attempts),planned_encounters=len(cases),total_D01_used=budget['used']+len(attempts),remaining=300-budget['used']-len(attempts),roster_identity_match=identity,
 source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in binaries.items()),workbook_unchanged=hashlib.sha256(workbook.read_bytes()).hexdigest()==workbook_hash,
 new_B05_encounters=0,new_C16_encounters=0,capacity100_retest=False,cloud_modified=False,production_modified=False,seconds=time.time()-started['started_at'])
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');budget_path.write_text(json.dumps(dict(item='D01',used=proof['total_D01_used'],remaining=proof['remaining'],maximum=300,current_handle=None,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json')),indent=2)+'\n')
print((r.stdout+r.stderr)[-5000:] if r else json.dumps(error));print(json.dumps(proof))
assert r and r.returncode==0 and len(attempts)==len(cases) and identity and proof['source_unchanged'] and proof['binary_unchanged'] and proof['workbook_unchanged']
