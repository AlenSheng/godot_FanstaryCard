"""Prepared runner: it refuses to create a run or reserve attempts without the explicit extra D03 budget."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,os,subprocess,time

b=Path(__file__).parent;repo=Path.cwd();build=b/'d03-matched-armor-preflight-r2'
budget_path=repo/'docs/season-balance-20261102/D03-BUDGET.json';before=budget_path.read_bytes();budget=json.loads(before)
assert budget['item']=='D03' and budget['used']==299 and budget['maximum']==308 and budget.get('additional_user_reply_received') is True, 'D03 additional user budget reply has not been granted.'
assert budget.get('additional_authorization_reference') and budget['current_handle'] is None
preflight=json.loads((build/'result.json').read_bytes());assert preflight['build_exit']==0 and all(t['exit']==0 for t in preflight['tests']) and preflight['actual_new_encounters']==0
pin=json.loads((build/'source-pin.original.json').read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert all(sha(repo/n)==h for n,h in pin.items())
binary=Path(preflight['private_build'])/'bin/FantasyCard.Server.Tests/release';manifest=json.loads((build/'binary-manifest.original.json').read_bytes());assert all(sha(binary/n)==h for n,h in manifest.items())
for item,used in [('B05',330),('F01',255),('D01',297),('D02',112),('C16',298)]:
    other=json.loads((repo/f'docs/season-balance-20261102/{item}-BUDGET.json').read_bytes());assert other['used']==used and other.get('current_handle') is None
plan=json.loads((build/'plan.original.json').read_bytes());assert plan['prior_used']==299 and plan['maximum']==308 and len(plan['cases'])==9
plan.update(preflight_only=False,execution_approved=True,additional_authorization_reference=budget['additional_authorization_reference'],no_encounter_method_selected=False)
out=b/'d03-matched-armor-approved-r1';assert not out.exists();out.mkdir();(out/'prior-budget.original.json').write_bytes(before)
(out/'plan.original.json').write_text(json.dumps(plan,indent=2)+'\n')
env=dict(os.environ)
for key in list(env):
    if key.startswith('FANTASYCARD_'):env[key]=''
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',FANTASYCARD_RUN_D03_EFFICIENCY='1',FANTASYCARD_D03_PLAN=str(out/'plan.original.json'),FANTASYCARD_D03_OUTPUT=str(out/'observations'),FANTASYCARD_D03_BUDGET_FILE=str(budget_path))
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonClassEfficiencyPilotTests.DeclaredCandidatesRecordActualBossOutcomesWithoutChangingAnyGameRules','-trx',str(out/'run.trx'),'-xml',str(out/'run.xml')]
started=dict(parent_pid=os.getpid(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,planned_new_attempts=9,reserve_GiB=2,startup_GiB=1)
(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n')
budget_path.write_text(json.dumps(dict(budget,reserved_current=9,current_handle=started),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=None;error=None;start=time.monotonic()
try:
    r=guard.guarded_run(command,env=env,timeout=180,wait_seconds=30)
    (out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
except Exception as e:
    error=dict(type=type(e).__name__,message=str(e),output=str(getattr(e,'output','')));(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
finally:
    path=out/'observations/attempts.original.jsonl';attempts=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    expected=[dict(Id=c['id'],Hero=c['hero'],Deck=c['deck'],Armor=c['armor'],Seed=c['seed'],Policy=c['policy']) for c in plan['cases']]
    assert len(attempts)<=9 and attempts==expected[:len(attempts)]
    proof=dict(exit=r.returncode if r else None,error=error,actual_started=len(attempts),D03_used=299+len(attempts),D03_remaining=308-299-len(attempts),maximum=308,source_unchanged=all(sha(repo/n)==h for n,h in pin.items()),binary_unchanged=all(sha(binary/n)==h for n,h in manifest.items()),seconds=time.monotonic()-start,B05_new=0,F01_new=0,production_changed=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    budget_path.write_text(json.dumps(dict(budget,used=proof['D03_used'],remaining=proof['D03_remaining'],reserved_current=0,current_handle=None,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json')),indent=2)+'\n')
print(json.dumps(proof));assert r and r.returncode==0 and len(attempts)==9 and proof['source_unchanged'] and proof['binary_unchanged']
