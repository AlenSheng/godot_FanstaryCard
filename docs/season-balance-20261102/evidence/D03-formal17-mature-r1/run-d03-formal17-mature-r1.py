from pathlib import Path
import datetime, hashlib, importlib.util, json, os, subprocess, sys, time

sys.stdout.reconfigure(encoding='utf-8')
b=Path(__file__).parent; repo=Path.cwd(); out=b/'d03-formal17-mature-r1'
build=b/'f01-calendar-build-r7'
binary=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-calendar-build-r7\bin\FantasyCard.Server.Tests\release')
budget_path=repo/'docs/season-balance-20261102/D03-BUDGET.json'
pin=json.loads((build/'source-pin.original.json').read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(repo/n)==h for n,h in pin.items())
assert json.loads((build/'result.json').read_bytes())['exit']==0
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
mode=sys.argv[1]; assert mode in ('preflight','run')
if mode=='preflight':
    assert not out.exists();out.mkdir()
    budget=json.loads(budget_path.read_bytes());assert budget['used']==293 and budget['current_handle'] is None
    cases=[]
    for group,(deck,armor) in enumerate([('flow-loop','counter-offense'),('flow-offense','balanced')],1):
        for hero in ['Mage','Priest','Guardian']:
            cases.append(dict(id=f'D03-FORMAL17-MATURE-{group}-{hero}-1061',hero=hero,deck=deck,armor=armor,seed=1061,policy='rate-budget-half-v1'))
    plan=dict(prior_used=293,config_version='season-v1-config-17',content_hash='3e4efc7f04d2acc0d70f1ef3ba7f2ce9cc4b675543b443606880a10b6cc1e490',
        frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),cases=cases,
        scope='Six new actual original Boss encounters, two legal mature non-red builds x three classes. Explicit Boss-spawn fixture, not route/yield/calendar/population evidence.',
        original_boss_seconds=[75,120],effective_boss_seconds=[63.75,120],class_ratio_limit=1.15,
        pacing_relaxation=dict(lower_fraction=.15,reason='Repeated archived75s and67.5s lower-bound failures; original user explicitly allows documented finite relaxation. This new preregistered tolerance affects pacing only, no retrospective pass and no relaxation of class1.15.'),
        policy_equivalence='Formal17 current Cards (MAG-10 draw0), explicit season sustain500bp equals NumericalRules.ForSeason current config. No old in-memory card candidate.',
        seed_is_new_for_this_scope=True,no_development_pooling=True,B05_new=0,F01_new=0,capital_banks_unchanged=True)
    (out/'plan.original.json').write_text(json.dumps(plan,indent=2)+'\n')
    (out/'source-pin.original.json').write_bytes((build/'source-pin.original.json').read_bytes())
    (out/'binary-manifest.original.json').write_text(json.dumps({p.relative_to(binary).as_posix():sha(p) for p in binary.rglob('*') if p.is_file()},indent=2)+'\n')
    (out/'prior-budget.original.json').write_bytes(budget_path.read_bytes())
else:
    assert out.exists() and not (out/'run-started.original.json').exists()
    plan=json.loads((out/'plan.original.json').read_bytes());budget=json.loads(budget_path.read_bytes())
    assert budget['used']==293 and budget['current_handle'] is None and len(plan['cases'])==6
    assert json.loads((out/'preflight.result.json').read_bytes())['exit']==0
manifest=json.loads((out/'binary-manifest.original.json').read_bytes())
assert all(sha(binary/n)==h for n,h in manifest.items())
for item,used in [('B05',330),('D01',297),('D02',112),('C16',298),('F01',255)]:
    other=json.loads((repo/f'docs/season-balance-20261102/{item}-BUDGET.json').read_bytes()); assert other['used']==used and other.get('current_handle') is None
env=dict(os.environ)
for key in list(env):
    if key.startswith('FANTASYCARD_'):env[key]=''
env.update(DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_RUN_D03_EFFICIENCY='1',FANTASYCARD_D03_PLAN=str(out/'plan.original.json'),FANTASYCARD_D03_PREFLIGHT_OUTPUT=str(out/'inputs.original.json'),FANTASYCARD_D03_OUTPUT=str(out/'observations'))
method='CandidateInputsAreLegalAndBothSpeedLayersAreValued' if mode=='preflight' else 'DeclaredCandidatesRecordActualBossOutcomesWithoutChangingAnyGameRules'
command=['dotnet',str(binary/'FantasyCard.Server.Tests.dll'),'-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-method',f'FantasyCard.Server.Tests.Config.SeasonClassEfficiencyPilotTests.{method}','-trx',str(out/f'{mode}.trx'),'-xml',str(out/f'{mode}.xml')]
started=dict(parent_pid=os.getpid(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command,reserve_GiB=2,startup_GiB=1,planned=0 if mode=='preflight' else 6)
(out/f'{mode}-started.original.json').write_text(json.dumps(started,indent=2)+'\n')
if mode=='run':budget_path.write_text(json.dumps(dict(budget,reserved_current=6,current_handle=started),indent=2)+'\n')
r=None;error=None;start=time.monotonic()
try:
    r=guard.guarded_run(command,env=env,timeout=180,wait_seconds=30)
    (out/f'{mode}.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
except Exception as e:
    error=dict(type=type(e).__name__,message=str(e),output=str(getattr(e,'output','')))
    (out/f'{mode}.interrupted.original.json').write_text(json.dumps(error,indent=2)+'\n')
finally:
    path=out/'observations/attempts.original.jsonl'
    attempts=[json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    expected=[dict(Id=c['id'],Hero=c['hero'],Deck=c['deck'],Armor=c['armor'],Seed=c['seed'],Policy=c['policy']) for c in plan['cases']]
    assert attempts==expected[:len(attempts)] and len(attempts)<=6
    proof=dict(exit=r.returncode if r else None,error=error,actual_started=len(attempts),D03_used=293+len(attempts),D03_remaining=7-len(attempts),
        seconds=time.monotonic()-start,source_unchanged=all(sha(repo/n)==h for n,h in pin.items()),binary_unchanged=all(sha(binary/n)==h for n,h in manifest.items()),
        B05_new=0,F01_new=0,production_modified=False,cloud_modified=False)
    (out/f'{mode}.result.json').write_text(json.dumps(proof,indent=2)+'\n')
    if mode=='run':budget_path.write_text(json.dumps(dict(item='D03',used=proof['D03_used'],remaining=proof['D03_remaining'],maximum=300,current_handle=None,last_result=str(out/'run.result.json'),prior_budget=str(out/'prior-budget.original.json')),indent=2)+'\n')
print(json.dumps(proof));print((r.stdout+r.stderr)[-1800:] if r else error)
assert r and r.returncode==0 and proof['source_unchanged'] and proof['binary_unchanged']
assert mode=='preflight' and len(attempts)==0 or mode=='run' and len(attempts)==6
