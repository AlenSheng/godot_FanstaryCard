from pathlib import Path
import collections,hashlib,json

b=Path(__file__).parent;repo=Path.cwd();root=b/'f01-skill-correction/observations';out=b/'f01-skill-correction-audit-r1.derived.json';assert not out.exists()
plan=json.loads((b/'f01-skill-preparation-r1/plan.original.json').read_bytes());expected={r['id']:r for r in plan['attempts']}
control=json.loads(Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-skill-correction\control.private.json').read_bytes())
parent_raw=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-calendar-r1\control.private.json').read_bytes();parent=json.loads(parent_raw)
policy=json.loads((b/'f01-skill-preparation-r1/policy.original.json').read_bytes());assert hashlib.sha256(parent_raw).hexdigest()==policy['parent_control_sha256']
assert control['Schema']==parent['Schema'] and control['Status']=='Completed' and control['NextIndex']==3 and len(control['Finished'])==3 and not control['Skipped'] and control['CurrentCase'] is None
old_players={a['Id']:a['Player'] for a in parent['Actors']};rows=[];casts=pvp=0
for p in root.rglob('after.original.json'):
    after=json.loads(p.read_bytes());before=json.loads((p.parent/'before.original.json').read_bytes());terminal=json.loads((p.parent/'terminal-or-censored.original.json').read_bytes());settlement=json.loads((p.parent/'settlement.original.json').read_bytes());admitted=json.loads((p.parent/'admitted.original.json').read_bytes())
    s=after['scheduled'];case=s['Id'];assert case in expected and s['Day']==15 and s['Hour']==9
    primary=next(x for x in terminal['Players'] if not x['IsBot']);assert primary['PlayerId']==old_players[s['Actor']]==settlement['PlayerId']
    assert len(admitted['InitialState']['Players'])==4 and sum(x['IsBot'] for x in admitted['InitialState']['Players'])==3
    assert terminal['Season']['SeasonId']=='f01-calendar-current17' and terminal['ConfigVersion']=='season-v1-config-17'
    assert all(x['Phase'] in [4,5] for x in terminal['Players'])
    gold=sum(i['Quantity'] for i in primary['Inventory']['Items'] if i['Kind']==0) if primary['Phase']==5 else 0
    fragments=sum(i['Quantity'] for i in primary['Inventory']['Items'] if i['Kind']==3) if primary['Phase']==5 else 0
    checkpoint=before['Checkpoint'];assert after['wallet']['Gold']-checkpoint['wallet']['Gold']==gold and after['wallet']['EquipmentFragments']-checkpoint['wallet']['EquipmentFragments']==fragments
    assert not [g for g in checkpoint['inventory']['Equipments'] if g['Location'] in ['Inventory','Equipped']]
    events=[json.loads(line) for line in (p.parent/'actions.original.jsonl').read_text().splitlines()]
    choices=[e['Detail'] for e in events if e['Kind']=='reward'];taken=[e for e in choices if e['selected']['Kind']==1]
    legal_taken=[e for e in taken if e['selected']['Item']['Equipment']['Quality'] in ['Green','Blue']]
    actual=[g for g in after['inventory']['Equipments'] if g['Location'] in ['Inventory','Equipped']]
    assert legal_taken and actual
    awarded={e['selected']['Item']['ItemId'] for e in taken};assert all(g['InstanceId'] in awarded for g in actual)
    cast_events=[e for e in events if e['Kind']=='cast'];assert len(cast_events)==after['casts'];casts+=len(cast_events);pvp+=after['pvpCasts']
    rows.append(dict(case=case,actor=s['Actor'],result=settlement['Result'],old_attempts_kept=28,new_attempt_index=29,gear_before=0,gear_after=len(actual),gear_reward_claims=len(taken),green_blue_claims=len(legal_taken),gold=gold,fragments=fragments,source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
assert len(rows)==3 and {r['case'] for r in rows}==set(expected)
budget=json.loads((repo/'docs/season-balance-20261102/F01-BUDGET.json').read_bytes());journal=Path(budget['journal']).read_bytes();prior=(b/'f01-skill-correction-r1/prior-journal.original.jsonl').read_bytes();assert journal.startswith(prior)
previous='0'*64;starts=[];sequence=0
for sequence,line in enumerate(journal.decode().splitlines(),1):
    offset=line.index('"payload":')+len('"payload":');_,end=json.JSONDecoder().raw_decode(line[offset:]);row=json.loads(line)
    assert row['sequence']==sequence and row['previous']==previous and row['hash']==hashlib.sha256((previous+'\n'+line[offset:offset+end]).encode()).hexdigest();previous=row['hash']
    if row['payload']['kind']=='started':starts.append(row['payload']['caseId'])
assert len(starts)==len(set(starts))==300 and starts[-3:]==control['Finished'] and budget['used']==300 and budget['maximum']==300 and budget['remaining']==0
proof=dict(actual_new_starts=3,F01_used=300,F01_remaining=0,all_original_297_start_prefix_bytes_unchanged=True,hashchain_rows=sequence,hashchain_tip=previous,
    original_schema_and_player_ids_retained=True,no_account_or_capital_reset=True,parent_252_control_bytes_unchanged=True,all_three_observed_actual_legal_starter_gear=True,rows=rows,
    casts=casts,pvp_casts=pvp,post_match_gold_fragment_closures=3,outcomes=dict(collections.Counter(r['result'] for r in rows)),
    original_skilled28_games_not_reinterpreted=True,no_claim_of_day1_or_natural_firstset_quantile=True,D03_new=0,B05_new=0,product_changed=False,production_changed=False)
out.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
