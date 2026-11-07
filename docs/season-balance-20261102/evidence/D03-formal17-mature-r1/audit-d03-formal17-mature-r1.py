from pathlib import Path
import collections, hashlib, json, math, statistics

b=Path(__file__).parent; out=b/'d03-formal17-mature-r1'
plan=json.loads((out/'plan.original.json').read_bytes())
rows=[json.loads(x) for x in (out/'observations/encounters.original.jsonl').read_text().splitlines()]
events=[json.loads(x) for x in (out/'observations/events.original.jsonl').read_text().splitlines()]
starts={e['row']['Id']:e for e in events if e['kind']=='start'}
assert len(rows)==len(starts)==6
catalog=json.loads(Path('client/data/catalog.json').read_bytes())
cards={c['id']:c for c in catalog['tables']['Cards']}
groups=[]; passive=collections.defaultdict(float)
for r in rows:
    key=r['row']['Id']; start=starts[key]; combat=start['player']['Combat']
    assert start['Version']==plan['config_version'] and start['ContentHash']==plan['content_hash']
    assert combat['FenxianPolicy']==4 and combat['FenxianReturnRateBasisPoints']==500
    assert combat['MaximumHp']=={'Mage':70,'Priest':80,'Guardian':100}[r['row']['Hero']]
    assert r['damage']==r['initialHp']+r['initialShield']+r['addedHp']+r['addedShield']-r['otherHpLoss']-r['discardedShield']-r['remainingHp']-r['remainingShield']
    assert len(start['cards'])==len(set(start['cards']))==20
    armor=[x['Equipment'] for x in start['gear']]
    assert len(armor)==5 and sum(x['Quality']=='Orange' for x in armor)==1 and all(x['Level']==3 and x['Quality'] in ('Purple','Orange') for x in armor)
    casts=[e for e in events if e['kind']=='cast' and e['Id']==key]
    assert len(casts)==r['casts'] and all(v['seconds']-u['seconds']>=.5-1e-8 for u,v in zip(casts,casts[1:]))
    for e in casts:
        written_draw=sum(cards[c['CardId']]['immediate_draw'] for c in e['selected'])
        written_charge=sum(cards[c['CardId']]['draw_charge'] for c in e['selected'])
        assert e['result']['ImmediateDraw']>=written_draw and e['result']['DrawCharge']>=written_charge-1e-8
        passive[key]+=e['result']['ImmediateDraw']-written_draw+e['result']['DrawCharge']-written_charge
    if r['row']['Hero']=='Mage':
        profile=combat['Equipment']; interval=max(profile['MinimumDrawInterval'],min(profile['MaximumDrawInterval'],4*(1+profile['DrawIntervalModifier'])))
        assert passive[key]<=r['seconds']/interval*.05+1e-8
    else:assert abs(passive[key])<1e-8
for variant in (1,2):
    group=[r for r in rows if f'MATURE-{variant}-' in r['row']['Id']]
    assert len(group)==3 and {r['row']['Hero'] for r in group}=={'Mage','Priest','Guardian'}
    configurations=[[{k:v for k,v in x['Equipment'].items()} for x in starts[r['row']['Id']]['gear']] for r in group]
    assert configurations[0]==configurations[1]==configurations[2]
    times={r['row']['Hero']:r['seconds'] for r in group}; ratio=max(times.values())/min(times.values())
    groups.append(dict(variant=variant,deck=group[0]['row']['Deck'],armor=group[0]['row']['Armor'],seed=1061,seconds=times,
        class_ratio=ratio,class15_pass=ratio<=1.15,all_win=all(r['outcome']=='Win' for r in group),
        original75_120_all_pass=all(75<=t<=120 for t in times.values()),preregistered63_75_120_all_pass=all(63.75<=t<=120 for t in times.values()),
        armor_elements=dict(collections.Counter(x['Element'] for x in configurations[0])),armor_effects=dict(collections.Counter(x['EffectAffix'] for x in configurations[0])),
        individual_resource_growth={r['row']['Hero']:dict(added_hp=r['addedHp'],added_shield=r['addedShield']) for r in group}))
f01=json.loads((b/'f01-calendar-evidence-audit-r2.derived.json').read_bytes())
novices=[dict(actor=p['actor'],first_basic_availability_observed_attempt=p['first_basic_availability_observed_attempt'],
    right_censored_after_attempt=p['right_censored_after_attempt'],final_day=p['final']['day'],final_unlocked=p['final']['unlocked'],
    final_gold=p['final']['wallet']['Gold'],final_fragments=p['final']['wallet']['EquipmentFragments']) for p in f01['profiles'] if p['cohort']=='novice']
proof=dict(scope='Current formal17 two-build six original Boss encounters, no route/yield claim',D03_used=299,D03_remaining=1,
    outcomes=dict(collections.Counter(r['outcome'] for r in rows)),casts=sum(r['casts'] for r in rows),resource_events=sum(e['kind']=='resource' for e in events),
    independent_resource_closures=6,groups=groups,all_class_targets_pass=all(g['class15_pass'] for g in groups),D03_accepted=False,
    ordinary_build_is_legal_but_elementally_different_from_old_B05_water3_fire2=True,
    diagnosis='Balanced helper uses Fire3/Metal2 with Water flow deck; this is a legal negative configuration, not the previous Water3/Fire2 twoPiercing/threeVitality positive control. Different draws/windup crossings yield different amounts of real shield; no monster resource anomaly or class-base-HP anomaly.',
    no_population_claim=True,no_general_server_defect_inferred=True,no_posthoc_pacing_relaxation=True,
    F01_evidence_novice_growth=novices,F01_is_not_D03_budget_reset=True,B05_new=0,F01_new=0,production_changed=False,
    next_action='Do not spend the single remaining case as an incomplete class comparison. A new matched Water3/Fire2 twoPiercing/threeVitality triad requires an explicit additional D03 budget; keep all historical failures.',
    original_hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()})
target=b/'d03-formal17-mature-audit-r1.derived.json';assert not target.exists();target.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:proof[k] for k in ['D03_used','D03_remaining','outcomes','casts','resource_events','groups','D03_accepted']},ensure_ascii=False))
