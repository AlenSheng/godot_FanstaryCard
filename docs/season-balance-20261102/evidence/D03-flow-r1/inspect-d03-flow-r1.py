from pathlib import Path
import json,statistics,collections
b=Path(__file__).parent;root=b/'d03-flow-pilot-r1/observations'
rows=[json.loads(x) for x in (root/'encounters.original.jsonl').read_text().splitlines()]
events=[json.loads(x) for x in (root/'events.original.jsonl').read_text().splitlines()]
assert len(rows)==12 and len({x['row']['Id'] for x in rows})==12
for x in rows:
 assert x['damage']==x['initialHp']+x['initialShield']+x['addedHp']+x['addedShield']-x['otherHpLoss']-x['discardedShield']-x['remainingHp']-x['remainingShield']
starts=[x for x in events if x['kind']=='start'];assert len(starts)==12 and all(x['Version']=='season-v1-config-16' for x in starts)
comparisons=[]
for deck in ['flow-counter','flow-loop']:
 group=[x for x in rows if x['row']['Deck']==deck];medians={};failures=[]
 for hero in ['Mage','Priest','Guardian']:
  cases=[x for x in group if x['row']['Hero']==hero];assert len(cases)==2
  successes=[x['seconds'] for x in cases if x['outcome']=='Win'];failures.extend(x['row']['Id'] for x in cases if x['outcome']!='Win')
  medians[hero]=statistics.median(successes) if successes else None
 complete=not failures and all(x is not None for x in medians.values());ratio=max(medians.values())/min(medians.values()) if complete else None
 comparisons.append(dict(deck=deck,medians=medians,failed_or_censored=failures,all_six_won=complete,class_ratio=ratio,original_15_percent_pass=complete and ratio<=1.15,original_Boss75_120_pass=complete and all(75<=x<=120 for x in medians.values()),development_only=True))
proof=dict(new_D03_encounters=12,total_D03=239,remaining=61,outcomes=dict(collections.Counter(x['outcome'] for x in rows)),casts=sum(x['kind']=='cast' for x in events),resource_events=sum(x['kind']=='resource' for x in events),independent_resource_closure_cases=12,comparisons=comparisons,no_income_merged_to_banks=True,D03_accepted=False,heldout_seeds_tested=False)
p=b/'d03-flow-inspection-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+chr(10));print(json.dumps(proof))
