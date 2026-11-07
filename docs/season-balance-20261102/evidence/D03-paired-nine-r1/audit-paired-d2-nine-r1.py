from pathlib import Path
import collections, datetime, hashlib, json, math, statistics

b=Path(__file__).parent;root=b/'d03-paired-routes-approved-r1';out=b/'d03-paired-d2-audit-r1';assert not out.exists();out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(path):
    text=path.read_text('utf-8-sig');decoder=json.JSONDecoder();index=0;rows=[]
    while index<len(text):
        while index<len(text) and text[index].isspace():index+=1
        if index==len(text):break
        row,index=decoder.raw_decode(text,index);rows.append(row)
    return rows
inputs=json.loads((root/'inputs.original.json').read_bytes());routes=load(root/'observations/routes.original.jsonl');events=load(root/'observations/events.original.jsonl')
expected={r['id']:r for r in inputs['cases']};assert len(routes)==9 and {r['scenario']['Id'] for r in routes}==set(expected)
starts={};ends={};encounters={};durations=collections.defaultdict(list);resource_closures=[];hp_values=collections.defaultdict(set)
for event in events:
    kind=event['kind']
    if kind=='start':
        key=event['scenario']['Id'];starts[key]=event;assert event['Version']=='season-v1-config-17' and event['ContentHash']==inputs['ContentHash']
    elif kind=='encounter-start':encounters[(event['Id'],event['pathIndex'])]=event
    elif kind=='encounter-end':
        start=encounters[(event['Id'],event['pathIndex'])];parent=starts[event['Id']]
        cell=next(c for c in parent['map']['Cells'] if c['Position']==start['position'])
        tier='Boss' if cell['IsBoss'] else 'Elite' if cell['MonsterGroupId'].startswith('E') else 'Normal'
        duration=round(event['seconds']-start['seconds'],8);assert duration>0 and event['outcome']=='Clear'
        work=event['initialHp']+event['hpAdded']-event['hpOtherLoss']-event['remainingHp']+event['initialShield']+event['shieldAdded']-event['shieldDiscarded']-event['remainingShield']
        assert event['remainingHp']==event['remainingShield']==0 and work==event['damage']
        resource_closures.append(dict(id=event['Id'],pathIndex=event['pathIndex'],tier=tier,seconds=duration,actual_damage=event['damage'],resource_work=work))
        durations[tier].append(duration)
    elif kind=='end':ends[event['result']['scenario']['Id']]=event['result']
assert len(starts)==len(ends)==9 and len(resource_closures)==72
for row in routes:
    key=row['scenario']['Id'];assert row==ends[key]
    assert row['scenario']['Seed']==expected[key]['seed'] and row['scenario']['Hero']==expected[key]['hero']
    assert row['outcome']=='Extracted' and row['clears']==8 and row['pathIndex']==7 and row['original_map_unchanged']
    assert row['recoveredAction'] and row['recoveredExtraction'] and row['potions']==row['springs']==0
    player=row['snapshot']['Players'][0];assert player['Phase']==5 and player['ExtractionRemaining'] is None
    assert player['ExtractionCompletedAt']==row['expectedExtraction'] and player['Combat']['WeaponLevel']==2
    assert row['snapshot']['Map']==starts[key]['map']
    armor=player['WornArmor'];assert len(armor)==5 and collections.Counter(x['Equipment']['Element'] for x in armor)=={'Water':3,'Fire':2}
    assert collections.Counter(x['Equipment']['EffectAffix'] for x in armor)=={'Piercing':2,'Vitality':3}
    assert collections.Counter(x['Equipment']['Quality'] for x in armor)=={'Orange':1,'Purple':4}
    assert all(x['Equipment']['Level']==3 for x in armor)
    items=player['Inventory']['Items'];assert sum(x['Quantity'] for x in items if x['ItemId']=='gold')==row['realizedGold']
    assert sum(x['Quantity'] for x in items if x['ItemId']=='equipment_fragments')==row['realizedFragments']
    hp_values[row['scenario']['Hero']].add(player['Combat']['Hp'])
    readings=[e for e in events if e['kind']=='extraction-reading' and e['Id']==key];assert len(readings)==1 and readings[0]['duration']=='00:00:03'
groups={hero:[r for r in routes if r['scenario']['Hero']==hero] for hero in ['Mage','Priest','Guardian']}
medians={h:statistics.median(r['seconds'] for r in rs) for h,rs in groups.items()}
class_time_ratio=max(medians.values())/min(medians.values());assert class_time_ratio<=1.15
by_seed=[]
for seed in [2013,2149,2214]:
    rows=[r for r in routes if r['scenario']['Seed']==seed];assert len(rows)==3
    ratio=max(r['seconds'] for r in rows)/min(r['seconds'] for r in rows)
    assert ratio<=1.15 and len({r['realizedGold'] for r in rows})==len({r['realizedFragments'] for r in rows})==1
    by_seed.append(dict(seed=seed,time_ratio=ratio,gold_each=rows[0]['realizedGold'],fragments_each=rows[0]['realizedFragments']))
hours={h:dict(total_seconds=sum(r['seconds'] for r in rs),gold=sum(r['realizedGold'] for r in rs),fragments=sum(r['realizedFragments'] for r in rs)) for h,rs in groups.items()}
for h,row in hours.items():row.update(gold_per_domain_hour=row['gold']*3600/row['total_seconds'],fragments_per_domain_hour=row['fragments']*3600/row['total_seconds'])
income_ratios={name:max(row[name] for row in hours.values())/min(row[name] for row in hours.values()) for name in ['gold_per_domain_hour','fragments_per_domain_hour']};assert all(v<=1.15 for v in income_ratios.values())
targets={'Normal':(25,40),'Elite':(50,80),'Boss':(75,120)};pacing={}
for tier,values in durations.items():
    low,high=targets[tier];pacing[tier]=dict(n=len(values),minimum=min(values),median=statistics.median(values),maximum=max(values),original_target=[low,high],below=sum(x<low for x in values),within=sum(low<=x<=high for x in values),above=sum(x>high for x in values))
result=dict(scope='Actual nine pairedD2 full routes; fixed class15percent criterion unchanged',cases=9,extracted=9,cleared_cells=72,
    successful_casts=sum(r['casts'] for r in routes),resource_events=sum(e['kind']=='resource' for e in events),resource_closures=resource_closures,
    class_median_seconds=medians,class_median_time_ratio=class_time_ratio,paired_seed_results=by_seed,class_efficiency_passed=True,
    actual_carried_income=hours,income_per_domain_hour_ratios=income_ratios,carried_income_efficiency_passed=True,
    extraction_and_action_recovery_passed=True,original_maps_unchanged=True,no_red_equipment=True,
    pacing=pacing,pacing_original_targets_all_met=all(v['below']==v['above']==0 for v in pacing.values()),
    legal_vitality_overcap_final_hp={h:sorted(v) for h,v in hp_values.items()},
    limitations=['Three frozen geometry-selected maps,not population guarantee','PvE-only domain route,not native/multiplayer capacity','Red quota exhausted fixture,not new PG mint validation','Carried inventory and domain-clock income,not new account PG settlement or operating-net proof','No long-run or first-set quantiles inferred from these9'],
    D03_used=317,D03_maximum=317,new_B05_F01=0,source_and_binary_pins_unchanged=True,whole_D03_acceptance_requires_review=True,
    source_routes_sha256=sha(root/'observations/routes.original.jsonl'),source_events_sha256=sha(root/'observations/events.original.jsonl'))
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['cases','extracted','class_median_seconds','class_median_time_ratio','income_per_domain_hour_ratios','pacing','legal_vitality_overcap_final_hp']}))
