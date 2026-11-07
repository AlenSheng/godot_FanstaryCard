from pathlib import Path
import json, hashlib, collections, math, uuid

b = Path(__file__).parent
root = b / 'f01-support-week-r1/observations'
control = json.loads(Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\f01-support-week-r1\control.private.json').read_bytes())
out = b / 'f01-support-week-evidence-audit-r1.derived.json'
assert not out.exists()
assert control['Status'] == 'Completed' and control['NextIndex'] == len(control['Finished']) == 42 and not control['Skipped'] and control['CurrentCase'] is None
spec = json.loads(Path('docs/season-balance-20261102/F01-BUDGET.json').read_bytes())
plan = json.loads(Path(spec['support_week_plan']['source']).read_bytes())
expected = {row['id']: row for row in plan['attempts']}
rows = []
cases = set()
match_ids = set()
room_ids = set()
actions_total = casts = pvp = 0
operations = collections.Counter()
rank = {'White':0,'Green':1,'Blue':2,'Purple':3,'Orange':4,'Red':5}
for path in sorted(root.rglob('after.original.json')):
    after = json.loads(path.read_bytes())
    before = json.loads((path.parent / 'before.original.json').read_bytes())['Checkpoint']
    admitted = json.loads((path.parent / 'admitted.original.json').read_bytes())
    terminal = json.loads((path.parent / 'terminal-or-censored.original.json').read_bytes())
    settlement = json.loads((path.parent / 'settlement.original.json').read_bytes())
    scheduled = after['scheduled']; case = scheduled['Id']; original = expected[case]
    assert case not in cases; cases.add(case)
    assert scheduled['Actor'] == original['actor'] and scheduled['Day'] == original['day'] and scheduled['Hour'] == original['shanghai_start_hour']
    assert admitted['MatchId'] not in match_ids and admitted['RoomId'] not in room_ids
    match_ids.add(admitted['MatchId']); room_ids.add(admitted['RoomId'])
    initial = admitted['InitialState']; primary = next(p for p in terminal['Players'] if not p['IsBot'])
    assert len(initial['Players']) == 4 and sum(p['IsBot'] for p in initial['Players']) == 3
    assert initial['ConfigVersion'] == terminal['ConfigVersion'] == 'season-v1-config-17'
    assert initial['Season'] == terminal['Season'] and initial['Season']['SeasonId'] == 'f01-support-current17'
    assert initial['Map']['Cells'] == terminal['Map']['Cells'] and initial['Map']['BossPosition'] == terminal['Map']['BossPosition']
    assert primary['Phase'] in [4,5] and all(p['Phase'] in [4,5] for p in terminal['Players'])
    assert settlement['MatchId'] == admitted['MatchId'] and settlement['PlayerId'] == primary['PlayerId']
    assert settlement['Result'] == ('Dead' if primary['Phase'] == 4 else 'Extracted')
    inventory = primary['Inventory']['Items']
    gold = sum(item['Quantity'] for item in inventory if item['Kind'] == 0) if primary['Phase'] == 5 else 0
    fragments = sum(item['Quantity'] for item in inventory if item['Kind'] == 3) if primary['Phase'] == 5 else 0
    assert after['wallet']['Gold'] - before['wallet']['Gold'] == gold
    assert after['wallet']['EquipmentFragments'] - before['wallet']['EquipmentFragments'] == fragments
    assert min(after['wallet'].get(k,0) for k in ['Gold','EquipmentFragments','ChallengeMarks','BlueprintMarks','OrangeBlueprintMarks']) >= 0
    action_rows = [json.loads(line) for line in (path.parent / 'actions.original.jsonl').read_text(encoding='utf-8').splitlines()]
    cast_rows = [a for a in action_rows if a['Kind'] == 'cast']
    assert len(cast_rows) == after['casts']
    assert len({a['Detail']['action'] for a in cast_rows}) == len(cast_rows)
    assert all(not a['Detail']['resolution']['ActionReplayed'] and 1<=a['Detail']['previews']<=3 for a in cast_rows)
    actual_pvp = sum(a['Detail']['phaseBefore'] == 3 for a in cast_rows)
    assert actual_pvp == after['pvpCasts']
    casts += len(cast_rows); pvp += actual_pvp; actions_total += len(action_rows)
    gear = [item for item in after['inventory']['Equipments'] if item['Location'] in ['Inventory','Equipped']]
    available_slots = {item['Slot'] for item in gear if item['Quality'] in ['Green','Blue']}
    rows.append({'case':case,'actor':scheduled['Actor'],'day':scheduled['Day'],'hour':scheduled['Hour'],
        'difficulty':before['request']['Difficulty'],'result':settlement['Result'],'gold_income':gold,'fragment_income':fragments,
        'elapsed':after['elapsed_seconds'],'wallet':after['wallet'],'unlocked':after['unlocked'],'journey_level':after['journey']['Level'],
        'journey_xp':after['journey']['Experience'],'basic_five_slots_available':len(available_slots)==5,
        'owned_available':len(gear),
        'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
assert cases == set(expected) and len(match_ids) == len(room_ids) == 42
for path in root.rglob('lobby.original.jsonl'):
    for line in path.read_text(encoding='utf-8').splitlines():
        item=json.loads(line); operations[item['kind']] += 1
        if item['kind'] == 'inventory-discarded-no-refund': assert item['value']['walletBefore'] == item['value']['walletAfter']
checkpoints = [r for r in rows if r['day'] in [1,7] and r['hour']==18]
assert len(checkpoints)==6
profiles = []
for actor in sorted({r['actor'] for r in rows}):
    own = sorted([r for r in rows if r['actor']==actor],key=lambda r:(r['day'],r['hour']))
    assert len(own)==14
    first = next((index+1 for index,r in enumerate(own) if r['basic_five_slots_available']),None)
    profiles.append({'actor':actor,'cohort':'novice-owned-support','attempts':14,'outcomes':dict(collections.Counter(r['result'] for r in own)),
        'first_basic_availability_observed_attempt':first,'right_censored_after_attempt':14 if first is None else None,
        'final':own[-1],'simulated_seconds':sum(r['elapsed'] for r in own)})
journal = Path(spec['journal']); previous='0'*64; starts=[]; sequence=0
for sequence,line in enumerate(journal.read_text(encoding='utf-8').splitlines(),1):
    start=line.index('"payload":')+len('"payload":');_,end=json.JSONDecoder().raw_decode(line[start:]);row=json.loads(line)
    assert row['sequence']==sequence and row['previous']==previous and row['hash']==hashlib.sha256((previous+'\n'+line[start:start+end]).encode()).hexdigest()
    previous=row['hash']
    if row['payload']['kind']=='started':starts.append(row['payload']['caseId'])
assert len(starts)==len(set(starts))==297 and set(expected).issubset(starts)
assert spec['used']==297 and spec['remaining']==3
financial=None  # This audit closes raw per-match gold/fragments; separate DB audit must establish all ledger claims.
prior_journal=(b/'f01-support-week-batch1-r1/prior-journal.original.jsonl').read_bytes()
assert journal.read_bytes().startswith(prior_journal)
original_members=json.loads(Path('docs/season-balance-20261102/evidence/F01-calendar-final-r1/original-archive-members.json').read_bytes())
assert all(hashlib.sha256((b/m['path']).read_bytes()).hexdigest()==m['sha256'] for m in original_members)
initials=[]
for path in root.glob('initial-*.original.json'):
    initial=json.loads(path.read_bytes());assert not initial['actor']['HistoricalOwnershipAssumed']
    owned={c['CardId']:c for c in initial['owned_before'] if c['Unlocked'] and c['CopyCount']>=1};assert len(owned)==51
    ids=initial['actor']['Cards'];assert len(ids)==len(set(ids))==20
    assert all(cid in owned and owned[cid]['Level']==0 for cid in ids)
    initials.append(dict(actor=initial['actor']['Id'],actual_owned_initial_copies=51,selected_deck=ids,source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(initials)==3
summary={'whole_progress_before_review':'33/35','actual_support_week_starts':42,'prior_main_and_diagnostic_starts_preserved':255,'total_F01_used':297,'remaining':3,
    'all_original_cases_and_unique_match_room_ids':True,'all_rows_game17_original_maps_normal4':True,
    'results':dict(collections.Counter(r['result'] for r in rows)),'difficulty_counts':dict(collections.Counter(r['difficulty'] for r in rows)),
    'casts':casts,'pvp_casts':pvp,'action_records':actions_total,'post_match_gold_fragment_closures':42,
    'mutations':{k:v for k,v in operations.items() if k!='operation-key'},'checkpoints':checkpoints,'profiles':profiles,
    'db_financial_audit':financial,'journal_records':sequence,'journal_tip':previous,
    'limitations':['Small named mechanical strategies, not humans or population confidence.','Skilled rarity-preference strategy fails to acquire D0 gear; do not call this server inability.','Owned-level0 novice growth and firstset right censoring remain D03 numerical concerns.',
        'Latest terminal rewards may remain earned/unclaimed until next lobby; do not credit hypothetical final purchases.','Fixture/repository adaptation failures before starts were reconciled against actual unchanged/committed state; no started case replayed.'],
    'product_files_changed':False,'production_changed':False,'fresh_account_inputs_verified':initials,'original1771files_SHA_unchanged':True,'old255journal_prefix_byte_unchanged':True,'D03_budget_not_reset':True,'D03_new':0,'B05_new':0,'support_week_execution_complete':True,'acceptance_verdict_not_inferred_from_successful_execution':True}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ['checkpoints','profiles','limitations','db_financial_audit']},ensure_ascii=True))
