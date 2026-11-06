from pathlib import Path
import json,statistics,collections,hashlib
b=Path(__file__).parent;root=b/'d03-sustain-holdout-r1/observations';rows=[json.loads(x) for x in (root/'encounters.original.jsonl').read_text().splitlines()];events=[json.loads(x) for x in (root/'events.original.jsonl').read_text().splitlines()];assert len(rows)==9
starts={x['row']['Id']:x for x in events if x['kind']=='start'};cards={x['id']:x for x in json.loads(Path('client/data/catalog.json').read_bytes())['tables']['Cards']};passive=collections.defaultdict(float)
for x in events:
 if x['kind']=='cast':
  printed_draw=sum(cards[c['CardId']]['immediate_draw'] for c in x['selected']);printed_charge=sum(cards[c['CardId']]['draw_charge'] for c in x['selected']);r=x['result'];assert r['ImmediateDraw']>=printed_draw and r['DrawCharge']>=printed_charge-1e-9;passive[x['Id']]+=r['ImmediateDraw']-printed_draw+r['DrawCharge']-printed_charge
for r in rows:
 assert r['damage']==r['initialHp']+r['initialShield']+r['addedHp']+r['addedShield']-r['otherHpLoss']-r['discardedShield']-r['remainingHp']-r['remainingShield']
 c=starts[r['row']['Id']]['player']['Combat'];assert c['FenxianPolicy']==4 and c['FenxianReturnRateBasisPoints']==500 and c['FenxianReturnCredit']==0
 if r['row']['Hero']=='Mage':
  e=c['Equipment'];t=max(e['MinimumDrawInterval'],min(e['MaximumDrawInterval'],4*(1+e['DrawIntervalModifier'])));assert passive[r['row']['Id']]<=r['seconds']/t*.05+1e-8
 else:assert abs(passive[r['row']['Id']])<1e-8
medians={};distribution={}
for hero in ['Mage','Priest','Guardian']:
 group=[r for r in rows if r['row']['Hero']==hero];assert len(group)==3
 wins=sorted(r['seconds'] for r in group if r['outcome']=='Win');medians[hero]=statistics.median(wins) if wins else None
 distribution[hero]=dict(attempts=3,win=len(wins),success_conditional_P10=wins[0] if wins else None,success_conditional_P50=medians[hero],success_conditional_P90=wins[-1] if wins else None,not_population=True)
allwin=all(r['outcome']=='Win' for r in rows);ratio=max(medians.values())/min(medians.values()) if allwin else None
seed_ratios={str(s):max(r['seconds'] for r in rows if r['row']['Seed']==s)/min(r['seconds'] for r in rows if r['row']['Seed']==s) for s in [419,503,601] if all(r['outcome']=='Win' for r in rows if r['row']['Seed']==s)}
checkpoint=json.loads((b/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(x['source']).read_bytes()).hexdigest()==x['sha256'] for x in checkpoint['D03_latest_banks'])
proof=dict(heldout_new_encounters=9,D03_used=260,D03_remaining=40,outcomes=dict(collections.Counter(r['outcome'] for r in rows)),heldout_medians=medians,heldout_class_ratio=ratio,class15_pass=allwin and ratio<=1.15,Boss75_120_pass=allwin and all(75<=x<=120 for x in medians.values()),per_seed_ratios=seed_ratios,distribution=distribution,development_pooling=False,casts=sum(x['kind']=='cast' for x in events),resource_events=sum(x['kind']=='resource' for x in events),independent_closures=9,printed_card_draw_preserved=True,passive_budget_upper_bound_verified=True,capital_banks_byte_unchanged=True,B05_supplemental_used=0,D03_complete=False,formal_activation=False)
p=b/'d03-sustain-holdout-inspection-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(proof))
