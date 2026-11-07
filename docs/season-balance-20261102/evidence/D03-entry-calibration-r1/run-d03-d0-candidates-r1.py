from pathlib import Path
import hashlib,importlib.util,json,os,sys,time

sys.stdout.reconfigure(encoding='utf-8');base=Path(__file__).parent;repo=Path.cwd();label='pilot'
build=base/'d03-d0-preflight-r1';assert json.loads((build/'result.json').read_bytes())['exit']==0
pin=json.loads((build/'source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
roster_path=base/'d03-d0-candidate-roster-r1.original.json';roster=json.loads(roster_path.read_bytes());cases=roster['cases']
budget_path=repo/'docs/season-balance-20261102/D03-BUDGET.json';prior=budget_path.read_bytes();budget=json.loads(prior);assert budget['used']==roster['prior_used'] and budget['current_handle'] is None and len(cases)<=300-budget['used']
for item,n in [('B05',300),('C16',298),('D01',297),('D02',100)]:assert json.loads((repo/'docs/season-balance-20261102'/f'{item}-BUDGET.json').read_bytes())['used']==n
out=base/'d03-d0-candidates-r1';assert not out.exists();out.mkdir();(out/'roster.original.json').write_bytes(roster_path.read_bytes());(out/'prior-budget.original.json').write_bytes(prior)
binary=build/'build/bin/FantasyCard.Server.Tests/debug';binaries={p.relative_to(binary).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.rglob('*') if p.is_file()};(out/'binary-manifest.original.json').write_text(json.dumps(binaries,indent=2)+'\n')
workbook=build/'config/FantasyCard_Config.xlsx';wh=hashlib.sha256(workbook.read_bytes()).hexdigest();assert wh==pin['config/FantasyCard_Config.xlsx']
results=out/'results';results.mkdir();observations=out/'observations'
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonD0EntryCandidateTests.CandidateD0RunsUseCompiledRealDifficultyAndOriginalGeneratedMaps','-trx',str(results/'cases.trx'),'-xml',str(results/'cases.xml')]
started=dict(parent_pid=os.getpid(),started_at=time.time(),command=command,prior_used=budget['used'],planned=len(cases),local_reserve_GiB=2,startup_GiB=1)
(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n');budget_path.write_text(json.dumps(dict(item='D03',used=budget['used'],remaining=300-budget['used'],maximum=300,reserved_current=len(cases),current_handle=started),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);r=None;error=None
try:r=guard.guarded_run(command,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_D02_DUELS='',FANTASYCARD_RUN_D02_ROUTES='',FANTASYCARD_RUN_D03_EFFICIENCY='',FANTASYCARD_RUN_D03_COHORTS='',FANTASYCARD_RUN_D03_STARTER_SUPPORT='',FANTASYCARD_RUN_D03_D0_CANDIDATES='1',FANTASYCARD_D03_D0_PLAN=str(out/'roster.original.json'),FANTASYCARD_D03_D0_OUTPUT=str(observations),FANTASYCARD_D03_DIFFICULTY_WORKBOOK=str(workbook),FANTASYCARD_RUN_D01_BOUNDARIES='',FANTASYCARD_RUN_C16_CALIBRATION='',FANTASYCARD_C16_REUSE_PREFLIGHT='',FANTASYCARD_RUN_THEME_COMPARISON='',FANTASYCARD_RUN_B05_MATRIX='',FANTASYCARD_RUN_B05_FINAL_NINE='',FANTASYCARD_TEST_POSTGRES=''),timeout=300,wait_seconds=180)
except Exception as e:error=dict(type=type(e).__name__,error=str(e),output=str(getattr(e,'output','')));(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
if r is not None:(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
p=observations/'attempts.original.jsonl';attempts=[json.loads(x) for x in p.read_text('utf-8').splitlines()] if p.exists() else [];assert len(attempts)<=len(cases)
heroes={'Priest':1,'Mage':2,'Guardian':3}
expected=[dict(Id=c['id'],Hero=c['hero'],Seed=c['seed'],Basis=c['basis']) for c in cases]
identity=all(a==e for a,e in zip(attempts,expected))
proof=dict(exit=r.returncode if r else None,error=error,actual_started=len(attempts),planned=len(cases),total_D03_used=budget['used']+len(attempts),remaining=300-budget['used']-len(attempts),roster_identity_match=identity,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),binary_unchanged=all(hashlib.sha256((binary/n).read_bytes()).hexdigest()==h for n,h in binaries.items()),workbook_unchanged=hashlib.sha256(workbook.read_bytes()).hexdigest()==wh,new_B05=0,new_C16=0,new_D01=0,new_D02=0,cloud_modified=False,production_modified=False,seconds=time.time()-started['started_at'])
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');budget_path.write_text(json.dumps(dict(item='D03',used=proof['total_D03_used'],remaining=proof['remaining'],maximum=300,current_handle=None,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json')),indent=2)+'\n')
print((r.stdout+r.stderr)[-5000:] if r else json.dumps(error));print(json.dumps(proof));assert r and r.returncode==0 and len(attempts)==len(cases) and identity and proof['source_unchanged'] and proof['binary_unchanged'] and proof['workbook_unchanged']
