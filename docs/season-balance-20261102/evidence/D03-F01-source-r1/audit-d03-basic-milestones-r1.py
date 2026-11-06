from pathlib import Path
import json,hashlib,collections,math,datetime
base=Path(__file__).parent;ctx=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());slots={'Head','Chest','Hands','Legs','Feet'};rank={'White':0,'Green':1,'Blue':2,'Purple':3,'Orange':4,'Red':5};records=collections.defaultdict(list);pins=[]
stages=['d03-trajectory-r1','d03-trajectory-salvage-r1','d03-trajectory-entry16-r1','d03-trajectory-entry16-longrun-r1','d03-maintenance-routes-r1']
for stage in stages:
 folder=base/stage/'observations';assert folder.is_dir(),str(folder)
 files=list(folder.glob('*/checkpoint-*.original.json'))+list(folder.glob('*/bank-import.original.json'))+list(folder.glob('*/bank-final.original.json'))
 assert files,stage
 for p in files:
  raw=p.read_bytes();d=json.loads(raw);identifier=d['Id'];assert identifier in {r['id'] for r in ctx['D03_latest_banks']}
  ids=[o['Item']['ItemId'] for o in d['Items']];assert len(set(ids))==len(ids) and not (set(ids)&set(d['LostIds']))
  # A complete basic inventory is an availability observation, not an equipping or combat verdict.
  def available(minimum,maximum,exclude_initial):
   choices={s:[] for s in slots}
   for o in d['Items']:
    e=o['Item']['Equipment']
    if minimum<=rank[e['Quality']]<=maximum and (not exclude_initial or o['Source']!='InitialFixture'):choices[e['Slot']].append(o)
   if any(not x for x in choices.values()):return None
   picks=[min(v,key=lambda o:(rank[o['Item']['Equipment']['Quality']],o['Item']['ItemId'])) for s,v in sorted(choices.items())]
   if sum(rank[o['Item']['Equipment']['Quality']]>=4 for o in picks)>1:return None
   return [o['Item']['ItemId'] for o in picks]
  row={'source':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'attempts':d['Attempts'],'hero':d['Hero'],'cohort':d['Cohort'],'initial_fixture_items':sum(o['Source']=='InitialFixture' for o in d['Items']),'D0_green_blue_available_ids':available(1,2,False),'D0_newly_earned_green_blue_ids':available(1,2,True),'at_least_green_available_ids':available(1,4,False),'FirstQualityAttempt_original':d.get('FirstQualityAttempt'),'FirstReadyAttempt_original':d.get('FirstReadyAttempt')}
  records[identifier].append(row);pins.append({'path':str(p),'sha256':row['sha256']})
profiles=[]
for item in ctx['D03_latest_banks']:
 p=Path(item['source']);assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'];d=json.loads(p.read_bytes());rows=records[d['Id']];assert rows and all(r['hero']==d['Hero'] and r['cohort']==d['Cohort'] for r in rows)
 assert max(r['attempts'] for r in rows)==d['Attempts']
 def first(field):
  found=sorted((r for r in rows if r[field]),key=lambda r:(r['attempts'],r['source']))
  return found[0] if found else None
 profiles.append({'id':d['Id'],'hero':d['Hero'],'cohort':d['Cohort'],'observed_through_attempt':d['Attempts'],'first_D0_green_blue_observed':first('D0_green_blue_available_ids'),'first_D0_newly_earned_green_blue_observed':first('D0_newly_earned_green_blue_ids'),'first_at_least_green_observed':first('at_least_green_available_ids'),'original_quality_one_orange_four_purple':d['FirstQualityAttempt'],'original_ready_two_effect_sets_plus3':d['FirstReadyAttempt'],'original_strict_target':d['FirstTargetAttempt']})
groups=[]
for cohort in ['novice','returning','skilled']:
 people=[r for r in profiles if r['cohort']==cohort];g={'cohort':cohort,'people':3,'interpretation':'Named simulated strategies across three classes, not a human population sample.'}
 for field in ['first_D0_green_blue_observed','first_D0_newly_earned_green_blue_observed','first_at_least_green_observed']:
  vals=[r[field]['attempts'] if r[field] else None for r in people];g[field]={'observations':vals,'all_observed':None not in vals,'P50':sorted(vals)[math.ceil(.5*3)-1] if None not in vals else None,'P90':sorted(vals)[math.ceil(.9*3)-1] if None not in vals else None,'missing_rule':'If any subject remains censored, no complete empirical percentile is asserted.'}
 groups.append(g)
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'new_matches':0,'source_files':pins,'profiles':profiles,'groups':groups,'definition_scope':'First observation in retained real simulation bank checkpoints. Availability of five legal slots, not proof of first actual equipping/kill or wall-clock/calendar timing. Initial fixture equipment is separately flagged. One-orange/four-purple and strict target markers are unchanged.','version_scope':'Original mixed15/16 lineage, not current17 season acceptance.','D03_complete':False,'F01_complete':False,'budget_unchanged':True}
p=base/'d03-basic-milestones-r1.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'source_files':len(pins),'groups':groups}))
