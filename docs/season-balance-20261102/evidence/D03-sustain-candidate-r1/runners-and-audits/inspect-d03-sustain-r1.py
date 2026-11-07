from pathlib import Path
import json,statistics,collections,hashlib
b=Path(__file__).parent;repo=Path.cwd();cards={x['id']:x for x in json.loads((repo/'client/data/catalog.json').read_bytes())['tables']['Cards']};reports=[]
for label,rate,prior in [('sustain',.10,239),('sustain-half',.05,245)]:
 root=b/('d03-'+label+'-pilot-r1/observations');rows=[json.loads(x) for x in (root/'encounters.original.jsonl').read_text().splitlines()];events=[json.loads(x) for x in (root/'events.original.jsonl').read_text().splitlines()];assert len(rows)==6;starts={x['row']['Id']:x for x in events if x['kind']=='start'};passive=collections.defaultdict(float)
 for x in events:
  if x['kind']=='cast':
   draws=sum(cards[c['CardId']]['immediate_draw'] for c in x['selected']);charge=sum(cards[c['CardId']]['draw_charge'] for c in x['selected']);r=x['result'];assert r['ImmediateDraw']>=draws and r['DrawCharge']>=charge-1e-9;passive[x['Id']]+=r['ImmediateDraw']-draws+r['DrawCharge']-charge
 limits=[]
 for r in rows:
  assert r['damage']==r['initialHp']+r['initialShield']+r['addedHp']+r['addedShield']-r['otherHpLoss']-r['discardedShield']-r['remainingHp']-r['remainingShield']
  c=starts[r['row']['Id']]['player']['Combat'];assert c['FenxianPolicy']==4 and c['FenxianReturnCredit']==0
  if label=='sustain-half':assert c['FenxianReturnRateBasisPoints']==500
  if r['row']['Hero']=='Mage':
   e=c['Equipment'];interval=max(e['MinimumDrawInterval'],min(e['MaximumDrawInterval'],4*(1+e['DrawIntervalModifier'])));upper=r['seconds']/interval*rate;assert 0<=passive[r['row']['Id']]<=upper+1e-8;limits.append(dict(id=r['row']['Id'],passive=passive[r['row']['Id']],elapsed_time_upper_bound=upper))
  else:assert abs(passive[r['row']['Id']])<1e-8
 medians={h:statistics.median(r['seconds'] for r in rows if r['row']['Hero']==h and r['outcome']=='Win') for h in ['Mage','Priest','Guardian']};allwin=all(x['outcome']=='Win' for x in rows);ratio=max(medians.values())/min(medians.values());reports.append(dict(candidate=label,rate=rate,outcomes=dict(collections.Counter(r['outcome'] for r in rows)),medians=medians,class_ratio=ratio,class15_pass=allwin and ratio<=1.15,Boss75_120_pass=allwin and all(75<=x<=120 for x in medians.values()),casts=sum(x['kind']=='cast' for x in events),resource_events=sum(x['kind']=='resource' for x in events),independent_closures=6,printed_card_draw_preserved=True,passive_budget_bounds=limits))
checkpoint=json.loads((b/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(x['source']).read_bytes()).hexdigest()==x['sha256'] for x in checkpoint['D03_latest_banks'])
proof=dict(new_D03_encounters=12,D03_used=251,D03_remaining=49,reports=reports,old_9banks_byte_unchanged=True,formal_activation=False,heldout_validation=False,D03_accepted=False,B05_supplemental_used=0)
p=b/'d03-sustain-combined-inspection-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(proof))
