from pathlib import Path
import collections,hashlib,json,math,statistics

b=Path(__file__).parent;root=b/'f01-calendar-r1/observations';out=b/'f01-existing-same-tier-efficiency-r1.derived.json';assert not out.exists()
def seconds(value):
    h,m,s=value.split(':');return int(h)*3600+int(m)*60+float(s)
rows=[];signatures=[]
for p in root.rglob('after.original.json'):
    after=json.loads(p.read_bytes());s=after['scheduled']
    if not s['Actor'].startswith('F01-skilled-'):continue
    before=json.loads((p.parent/'before.original.json').read_bytes())['Checkpoint'];initial=json.loads((p.parent/'admitted.original.json').read_bytes())['InitialState'];terminal=json.loads((p.parent/'terminal-or-censored.original.json').read_bytes())
    player=next(x for x in initial['Players'] if not x['IsBot']);end=next(x for x in terminal['Players'] if not x['IsBot']);combat=player['Combat']
    assert before['request']['Difficulty']=='D0' and initial['Season']['Difficulty']==0 and initial['ConfigVersion']=='season-v1-config-17'
    assert player['WornArmor']==[] and combat['WeaponLevel']==0 and combat['Hp']==combat['MaximumHp']
    all_cards=[card for location in ['Hand','Library','Discard'] for card in combat['Deck'][location]]
    assert len(all_cards)==20 and all(c['Level']==0 for c in all_cards)
    deck=sorted((('CLASS-'+c['CardId'].split('-')[1]) if c['CardId'].startswith(('MAG-','PRI-','GUA-')) else c['CardId']) for c in all_cards)
    signature=dict(deck=deck,equipment=combat['Equipment'],weapon=0,difficulty=0,backpack=before['request']['BackpackTier'],safe=before['request']['SafeSlotIndexes'],potions=before['request']['PotionCount'])
    signatures.append(signature)
    active=seconds(end['TerminalRoomElapsed']);room=seconds(terminal['Elapsed']);assert 0<active<=room+1e-8
    gold=after['wallet']['Gold']-before['wallet']['Gold'];fragments=after['wallet']['EquipmentFragments']-before['wallet']['EquipmentFragments']
    actual_gold=sum(i['Quantity'] for i in end['Inventory']['Items'] if i['Kind']==0) if end['Phase']==5 else 0
    actual_fragments=sum(i['Quantity'] for i in end['Inventory']['Items'] if i['Kind']==3) if end['Phase']==5 else 0
    assert gold==actual_gold and fragments==actual_fragments
    rows.append(dict(actor=s['Actor'],case=s['Id'],day=s['Day'],hour=s['Hour'],active_seconds=active,room_seconds=room,post_terminal_bot_wait_seconds=room-active,gold=gold,fragments=fragments,result='Extracted' if end['Phase']==5 else 'Dead',source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
assert len(rows)==84 and all(s==signatures[0] for s in signatures)
groups=[]
for actor in sorted({r['actor'] for r in rows}):
    own=[r for r in rows if r['actor']==actor];assert len(own)==28
    elapsed=sum(r['active_seconds'] for r in own);gold=sum(r['gold'] for r in own);fragments=sum(r['fragments'] for r in own)
    groups.append(dict(actor=actor,n=28,outcomes=dict(collections.Counter(r['result'] for r in own)),active_seconds=elapsed,room_seconds=sum(r['room_seconds'] for r in own),
        median_active_seconds=statistics.median(r['active_seconds'] for r in own),mean_gold=gold/28,mean_fragments=fragments/28,actual_gold=gold,actual_fragments=fragments,
        actual_carried_gold_per_active_hour=gold/elapsed*3600,actual_carried_fragments_per_active_hour=fragments/elapsed*3600))
ratio=lambda key:max(g[key] for g in groups)/min(g[key] for g in groups)
ratios={key:ratio(key) for key in ['median_active_seconds','mean_gold','mean_fragments','actual_carried_gold_per_active_hour','actual_carried_fragments_per_active_hour']}
proof=dict(scope='Reanalysis only of current17 actual84 D0 matches under the original fixed policy; not new gameplay, not a rerun',groups=groups,ratios=ratios,
    all_selected_inputs_equal_after_class_identity_normalization=True,normalized_input=signatures[0],original_policy_has_growth_bias_but_D0_inputs_are_matched=True,
    map_seeds_are_independent_not_paired=True,not_population_or_all_tiers_proof=True,
    median_time_and_gold_fragment_efficiency_within15=all(r<=1.15 for r in ratios.values()),player_terminal_clock_used=True,room_bot_wait_separated=True,
    raw_rows=rows,new_gameplay_starts=0,D03_budget_not_reset=True,D03_accepted_not_inferred=True)
out.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k not in ['normalized_input','raw_rows']}))
