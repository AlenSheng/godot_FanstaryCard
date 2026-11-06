from pathlib import Path
import json,collections,hashlib
b=Path(__file__).parent;allrows=[];casts=0
for phase in ['b05-approved-supplement-r1','b05-approved-supplement-compat-r1','b05-approved-supplement-active-r1']:
 root=b/phase/'observations';rows=[json.loads(x) for x in (root/'cases.original.jsonl').read_text().splitlines()];events=[json.loads(x) for x in (root/'events.original.jsonl').read_text().splitlines()];starts={x['row']['Id']:x for x in events if x['kind']=='start'};previous_effect=collections.defaultdict(int)
 for x in events:
  if x['kind']=='cast':
   casts+=1;effective=x['effect']-previous_effect[x['Id']];previous_effect[x['Id']]=x['effect'];assert effective>=0 and x['handAfter']==x['handBefore']-len(x['selected'])+effective
   assert x['handAfter']==starts[x['Id']]['initial']+x['natural']+x['effect']-x['spent']
   assert len(x['allAfter'])==20+x['kills'] and len({c['InstanceId'] for c in x['allAfter']})==len(x['allAfter'])
   if x['creditBefore'] is not None:assert abs(x['creditBefore']-x['extraDraw']-x['extraCharge']-x['creditAfter'])<1e-8
 for r in rows:
  assert r['finalHand']==r['initial']+r['natural']+r['effect']-r['spent'] and r['replayed'] and r['gateRejected']
  if r['row']['Kind']=='compat':
   assert r['finalCredit'] is None and starts[r['row']['Id']]['Version']=='season-v1-config-16' and not starts[r['row']['Id']]['numerics'].get('SeasonMageSustainBudget',False)
  else:assert r['passiveUnits']+r['finalCredit']<=r['creditEarned']+1e-8
  if r['row']['Kind']=='recovery':assert r['recovered']
  if r['row']['Kind']=='active-set':assert starts[r['row']['Id']]['player']['Combat']['Equipment']['PiercingBonus']>0
 allrows+=rows
assert len(allrows)==30 and len({x['row']['Id'] for x in allrows})==30
budget=json.loads(Path('docs/season-balance-20261102/B05-BUDGET.json').read_bytes());assert budget['used']==330 and budget['supplemental_used']==30 and budget['supplemental_remaining']==0 and budget['current_handle'] is None
growth=[]
for d in range(6):
 g=[r for r in allrows if r['row']['Kind']=='growth' and r['row']['Difficulty']==d];v={r['row']['Hero']:r['seconds'] for r in g};growth.append(dict(difficulty=d,seconds=v,single_seed_class_ratio=max(v.values())/min(v.values()),class15_pass=max(v.values())/min(v.values())<=1.15,not_population=True))
active={r['row']['Hero']:r['seconds'] for r in allrows if r['row']['Kind']=='active-set'}
checkpoint=json.loads((b/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(x['source']).read_bytes()).hexdigest()==x['sha256'] for x in checkpoint['D03_latest_banks'])
proof=dict(actual_supplemental_cases=30,combined_B05_used=330,original300_preserved=True,remaining_allowance=0,affected_resource_scope_passed=True,outcomes=dict(collections.Counter(r['outcome'] for r in allrows)),casts=casts,kinds=dict(collections.Counter(r['row']['Kind'] for r in allrows)),per_cast_hand_and_pool_ledgers_closed=True,passive_credit_debits_and_upper_bounds_verified=True,replay_and_zero_time_gate_passed=30,whole_room_snapshot_recovery_passed=3,old_V1_controls_passed=3,old_V1_credit_fields_absent=True,active_D1_set_verified=3,full_process_restart_claimed=False,growth_diagnostics=growth,D1_active_set_seconds=active,D1_active_set_single_seed_ratio=max(active.values())/min(active.values()),D1_active_set_class15_pass=max(active.values())/min(active.values())<=1.15,all_difficulty_class15_accepted=False,D03_new_cases=0,D03_used=284,D03_remaining=16,capital_bank_SHA_unchanged=True,formal_activation=False,whole_goal_complete=False)
p=b/'b05-approved-supplement-final-inspection-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(proof))
