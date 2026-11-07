from pathlib import Path
import collections,hashlib,json,math,statistics

b=Path(__file__).parent;root=b/'f01-calendar-r1/observations';out=b/'f01-existing-same-tier-efficiency-r2.derived.json';assert not out.exists()
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
assert len(rows)==84
non_class_keys=[k for k in signatures[0] if k not in ['deck','potions']]
assert all(all(s[k]==signatures[0][k] for k in non_class_keys) for s in signatures)
class_decks={}
for actor in sorted({r['actor'] for r in rows}):
    own=[s for r,s in zip(rows,signatures) if r['actor']==actor]
    assert all(s['deck']==own[0]['deck'] for s in own)
    class_decks[actor]=own[0]['deck']
for row,sig in zip(rows,signatures):row['initial_potions']=sig['potions']
potion_counts={actor:dict(collections.Counter(r['initial_potions'] for r in rows if r['actor']==actor)) for actor in class_decks}
assert all(v==next(iter(potion_counts.values())) for v in potion_counts.values())
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
    non_class_gear_level_inputs_matched=True,class_specific_decklists=class_decks,initial_potion_counts_matched=potion_counts,normalized_input=signatures[0],original_policy_has_growth_bias_but_D0_inputs_are_matched=True,
    map_seeds_are_independent_not_paired=True,not_population_or_all_tiers_proof=True,
    median_time_and_gold_fragment_efficiency_within15=all(r<=1.15 for r in ratios.values()),player_terminal_clock_used=True,room_bot_wait_separated=True,
    raw_rows=rows,new_gameplay_starts=0,D03_budget_not_reset=True,D03_accepted_not_inferred=True)
strata=[]
for potions in sorted({r['initial_potions'] for r in rows}):
    values=[]
    for actor in class_decks:
        own=[r for r in rows if r['actor']==actor and r['initial_potions']==potions];duration=sum(r['active_seconds'] for r in own)
        values.append(dict(actor=actor,n=len(own),median_seconds=statistics.median(r['active_seconds'] for r in own),gold_per_hour=sum(r['gold'] for r in own)/duration*3600,fragments_per_hour=sum(r['fragments'] for r in own)/duration*3600))
    strata.append(dict(potions=potions,groups=values,ratios={k:max(v[k] for v in values)/min(v[k] for v in values) for k in ['median_seconds','gold_per_hour','fragments_per_hour']}))
proof['all_potion_strata']=strata
proof['not_exact_same_deck_or_paired_route_causal_proof']=True
proof['checker_r1_extra_common_deck_identity_assumption_withdrawn']=True
proof['remaining_other_tiers_and_mature_route_yield_not_inferred']=True
out.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k not in ['normalized_input','raw_rows','class_specific_decklists']}))
