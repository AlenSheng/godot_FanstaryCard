from pathlib import Path
import collections,hashlib,json,math,statistics

b=Path(__file__).parent;root=b/'d03-matched-armor-approved-r1';plan=json.loads((root/'plan.original.json').read_bytes())
rows=[json.loads(line) for line in (root/'observations/encounters.original.jsonl').read_text().splitlines()]
events=[json.loads(line) for line in (root/'observations/events.original.jsonl').read_text().splitlines()]
starts={e['row']['Id']:e for e in events if e['kind']=='start'};assert len(rows)==len(starts)==len(plan['cases'])==9
cards={c['id']:c for c in json.loads(Path('client/data/catalog.json').read_bytes())['tables']['Cards']}
passive=collections.defaultdict(float);gear_profiles=[];legal_caps={};cast_count=0
for row in rows:
    key=row['row']['Id'];start=starts[key];c=start['player']['Combat'];hero=row['row']['Hero'];expected_hp={'Mage':70,'Priest':80,'Guardian':100}[hero]
    assert start['Version']=='season-v1-config-17' and start['ContentHash']=='3e4efc7f04d2acc0d70f1ef3ba7f2ce9cc4b675543b443606880a10b6cc1e490'
    assert c['MaximumHp']==expected_hp and c['FenxianPolicy']==4 and c['FenxianReturnRateBasisPoints']==500
    armor=[g['Equipment'] for g in start['gear']];assert [g['Element'] for g in armor]==['Water','Water','Water','Fire','Fire']
    assert [g['EffectAffix'] for g in armor]==['Piercing','Piercing','Vitality','Vitality','Vitality']
    assert all(g['Level']==3 for g in armor) and sum(g['Quality']=='Orange' for g in armor)==1 and sum(g['Quality']=='Purple' for g in armor)==4
    gear_profiles.append(armor)
    hp_cap=max(1,math.floor(expected_hp*(1+c['Equipment']['VitalityOvercapBonus'])+1e-8));legal_caps[hero]=hp_cap
    assert 0<row['endingHp']<=hp_cap
    assert row['damage']==row['initialHp']+row['initialShield']+row['addedHp']+row['addedShield']-row['otherHpLoss']-row['discardedShield']-row['remainingHp']-row['remainingShield']
    casts=[e for e in events if e['kind']=='cast' and e['Id']==key];assert len(casts)==row['casts']
    assert all(v['seconds']-u['seconds']>=.5-1e-8 for u,v in zip(casts,casts[1:]))
    for event in casts:
        assert 0<=event['hpAfter']<=hp_cap and 0<=event['shield']<=expected_hp//2
        draw=sum(cards[c['CardId']]['immediate_draw'] for c in event['selected']);charge=sum(cards[c['CardId']]['draw_charge'] for c in event['selected'])
        assert event['result']['ImmediateDraw']>=draw and event['result']['DrawCharge']>=charge-1e-8
        passive[key]+=event['result']['ImmediateDraw']-draw+event['result']['DrawCharge']-charge
    if hero=='Mage':
        p=c['Equipment'];natural=max(p['MinimumDrawInterval'],min(p['MaximumDrawInterval'],4*(1+p['DrawIntervalModifier'])))
        assert passive[key]<=row['seconds']/natural*.05+1e-8
    else:assert abs(passive[key])<1e-8
    cast_count+=len(casts)
assert all(g==gear_profiles[0] for g in gear_profiles)
medians={hero:statistics.median(r['seconds'] for r in rows if r['row']['Hero']==hero) for hero in ['Mage','Priest','Guardian']}
ratio=max(medians.values())/min(medians.values());seed_ratios={str(seed):max(r['seconds'] for r in rows if r['row']['Seed']==seed)/min(r['seconds'] for r in rows if r['row']['Seed']==seed) for seed in [1553,1601,1699]}
all_win=all(r['outcome']=='Win' for r in rows);assert all_win and ratio<=1.15 and all(r<=1.15 for r in seed_ratios.values())
proof=dict(actual_new_encounters=9,D03_used=308,D03_maximum=308,D03_remaining=0,all_win=all_win,class_medians=medians,median_class_ratio=ratio,per_seed_class_ratios=seed_ratios,class15_pass=True,
    original75_120_medians_pass=all(75<=v<=120 for v in medians.values()),original75_120_individual_outliers=[dict(id=r['row']['Id'],seconds=r['seconds']) for r in rows if not 75<=r['seconds']<=120],
    preregistered63_75_120_all_individuals_pass=all(63.75<=r['seconds']<=120 for r in rows),casts=cast_count,resource_events=sum(e['kind']=='resource' for e in events),independent_resource_closures=9,
    natural_time_passive_budget_verified=True,legal_hp_caps_with_vitality=legal_caps,legal_overcap_not_reported_as_error=True,
    corresponding_mature_D5_Boss_scope_only=True,not_route_yield_or_population_proof=True,D03_accepted=False,other_growth_yield_sustainability_gaps_not_waived=True,
    B05_new=0,F01_new=0,production_changed=False,original_source_proposal_sha256=plan['source_proposal_sha256'],
    original_file_hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()})
out=b/'d03-approved-matched-audit-r1.derived.json';assert not out.exists();out.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items() if k!='original_file_hashes'}))
