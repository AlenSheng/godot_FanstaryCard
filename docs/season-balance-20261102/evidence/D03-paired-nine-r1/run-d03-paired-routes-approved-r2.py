"""Prepared only. Explicit new D03317 paired-route authorization is required before allocation."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,os,time

b=Path(__file__).parent;repo=Path.cwd();build=b/'d03-paired-route-preflight-r2'
budget_path=repo/'docs/season-balance-20261102/D03-BUDGET.json';prior=budget_path.read_bytes();budget=json.loads(prior)
assert budget['used']==308 and budget['maximum']==317 and budget.get('paired_routes_user_reply_received') is True, 'Additional D03 paired-route budget has not been explicitly approved.'
assert budget.get('paired_routes_authorization_reference') and budget['current_handle'] is None
result=json.loads((build/'result.json').read_bytes());assert result['exit']==0 and result['actual_gameplay_starts']==0
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();pin=json.loads((build/'source-pin.original.json').read_bytes());assert all(sha(repo/n)==h for n,h in pin.items())
binary=Path(result['binary']);binary_pin=json.loads((build/'binary-manifest.original.json').read_bytes());assert all(sha(binary/n)==h for n,h in binary_pin.items())
for item,used in [('F01',300),('B05',330),('D01',297),('D02',112),('C16',298)]:
    other=json.loads((repo/f'docs/season-balance-20261102/{item}-BUDGET.json').read_bytes());assert other['used']==used and other.get('current_handle') is None
inputs=json.loads((build/'inputs.original.json').read_bytes());assert len(inputs['cases'])==9 and inputs['maximum']==317 and inputs['prior_used']==308
out=b/'d03-paired-routes-approved-r1';assert not out.exists();out.mkdir();(out/'prior-budget.original.json').write_bytes(prior);(out/'inputs.original.json').write_bytes((build/'inputs.original.json').read_bytes())
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method','FantasyCard.Server.Tests.Config.SeasonPairedRouteComparisonTests.RunExplicitlyAuthorizedMatchedD2FullRoutes','-trx',str(out/'routes.trx'),'-xml',str(out/'routes.xml')]
started=dict(parent_pid=os.getpid(),command=command,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),planned_cases=9,reserve_GiB=2,startup_GiB=1)
(out/'started.original.json').write_text(json.dumps(started,indent=2)+'\n');budget_path.write_text(json.dumps(dict(budget,current_handle=started,reserved_current=9),indent=2)+'\n')
env=dict(os.environ)
for key in list(env):
    if key.startswith('FANTASYCARD_'):env[key]=''
env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',FANTASYCARD_RUN_D03_PAIRED_ROUTES='1',FANTASYCARD_D03_PAIRED_INPUTS=str(out/'inputs.original.json'),FANTASYCARD_D03_BUDGET_FILE=str(budget_path),FANTASYCARD_D03_PAIRED_OUTPUT=str(out/'observations'))
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=None;error=None;began=time.monotonic()
try:
    r=guard.guarded_run(command,env=env,timeout=300,wait_seconds=30);(out/'run.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
except Exception as e:
    error=dict(type=type(e).__name__,message=str(e),output=str(getattr(e,'output','')));(out/'interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
finally:
    path=out/'observations/attempts.original.jsonl';actual=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    assert len(actual)<=9 and actual==inputs['cases'][:len(actual)]
    proof=dict(exit=r.returncode if r else None,error=error,actual_started=len(actual),D03_used=308+len(actual),D03_maximum=317,D03_remaining=9-len(actual),seconds=time.monotonic()-began,
        source_unchanged=all(sha(repo/n)==h for n,h in pin.items()),binary_unchanged=all(sha(binary/n)==h for n,h in binary_pin.items()),F01_new=0,B05_new=0,production_changed=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');budget_path.write_text(json.dumps(dict(budget,used=proof['D03_used'],remaining=proof['D03_remaining'],current_handle=None,reserved_current=0,last_result=str(out/'result.json'),prior_budget=str(out/'prior-budget.original.json')),indent=2)+'\n')
print(json.dumps(proof));assert r and r.returncode==0 and len(actual)==9 and proof['source_unchanged'] and proof['binary_unchanged']
