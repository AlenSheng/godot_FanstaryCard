"""Bounded Tencent-only descriptive coverage audit; no new native trial."""
import collections,hashlib,json,os,resource,sys,time
from pathlib import Path
assert sys.platform=='linux';resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,128*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(30,30));start=time.monotonic();memory=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;assert memory>=500000000+128*1024**2
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/b09-continuity-formal-statistics-r2-20261011';meta=json.loads((E/'inputs.json').read_bytes());assert meta['frozen_native_source_sha']=='0d56ceccf526f6ae8973f57da152d67faf93a5d5' and meta['required_native_formal_routes']==36000 and meta['all_nine_original_units_actual_success_and_G_receipts_observed'];files={x['source']:x for x in meta['files']};groups={};seen=set();unit_proof=[]
def inspect_row(row):
 assert row['source']==meta['frozen_native_source_sha'] and row['capacity'] in (0,3,5,8) and row['hiddenOrderNegativeRejected'] and row['instanceConservationChecks']>0 and row['nativeCommandCalls']==row['typedRequestCount']
 assert row['outcome'] in ('Dead','Extracted','ObservationBudgetCensored') and 0<=row['replaced']<=row['accepted']<=row['monsterChoices'] and row['monsterChoices']==row['accepted']+row['skipped']
 if row['capacity']==0:assert row['monsterChoices']==row['accepted']==row['skipped']==row['replaced']==0
 assert all(type(row[k]) is int and row[k]>=0 for k in ('accepted','skipped','replaced','kills','monsterChoices','instanceConservationChecks'))
 return row
for unit in meta['units']:
 p=Path(unit['directory'])/'routes.jsonl';x=files[str(p)];assert p.is_file() and not p.is_symlink() and p.stat().st_size==x['bytes'];h=hashlib.sha256();count=0;keys=set()
 with p.open('rb') as f:
  for line in f:
   assert len(line)<65536;h.update(line);row=inspect_row(json.loads(line));key=(row['hero'],row['seed'],row['capacity']);assert key not in seen and row['hero']==unit['hero'] and unit['start']<=row['seed']<unit['start']+1000;seen.add(key);keys.add((row['seed'],row['capacity']));count+=1;g=groups.setdefault((row['hero'],row['capacity']),{'routes':0,'routes_with_accept':0,'routes_with_skip':0,'routes_with_replacement':0,'accepted_decisions':0,'skipped_decisions':0,'replacement_decisions':0,'native_kills':0,'all_conservation_assertions':0,'outcomes':collections.Counter()});g['routes']+=1;g['routes_with_accept']+=int(row['accepted']>0);g['routes_with_skip']+=int(row['skipped']>0);g['routes_with_replacement']+=int(row['replaced']>0);g['accepted_decisions']+=row['accepted'];g['skipped_decisions']+=row['skipped'];g['replacement_decisions']+=row['replaced'];g['native_kills']+=row['kills'];g['all_conservation_assertions']+=row['instanceConservationChecks'];g['outcomes'][row['outcome']]+=1
 assert count==4000 and keys=={(seed,cap) for seed in range(unit['start'],unit['start']+1000) for cap in (0,3,5,8)} and h.hexdigest()==x['sha256'];unit_proof.append({'hero':unit['hero'],'start':unit['start'],'rows':count,'original_routes_sha256':x['sha256']})
assert len(seen)==36000 and len(groups)==12 and all(v['routes']==3000 for v in groups.values())
valid={'source':meta['frozen_native_source_sha'],'capacity':3,'hiddenOrderNegativeRejected':True,'instanceConservationChecks':1,'nativeCommandCalls':1,'typedRequestCount':1,'outcome':'Dead','replaced':0,'accepted':1,'skipped':0,'monsterChoices':1,'kills':1}
controls=[]
for name,changes in [('replacement_exceeds_accept',{'replaced':2}),('choice_total_changed',{'monsterChoices':2}),('default_off_made_optional',{'capacity':0}),('hidden_order_accepted',{'hiddenOrderNegativeRejected':False})]:
 try:inspect_row(valid|changes)
 except AssertionError:controls.append({'name':name,'rejected':True});continue
 raise AssertionError('Invalid descriptive coverage evidence accepted')
rows=[{'hero':k[0],'capacity':k[1],**v,'replacement_natural_observation_missing':k[1]>0 and v['replacement_decisions']==0} for k,v in sorted(groups.items())];print(json.dumps({'ok':True,'execution_host':'Tencent','kind':'original_full_natural_choice_contract_coverage_descriptive_only','actual_process_PID':os.getpid(),'original_native_source_sha':meta['frozen_native_source_sha'],'input_metadata_sha256':hashlib.sha256((E/'inputs.json').read_bytes()).hexdigest(),'all_original_routes':36000,'all_nine_original_units':unit_proof,'strata':rows,'invalid_evidence_controls':controls,'all_outcomes_including_censored_retained':True,'new_natural_experiment_samples':0,'causal_benefit_or_candidate_change_claimed':False,'declared_zero_replacement_strata_are_gaps_not_passes':True,'no_canonical_EXPERIMENT_case_automatically_closed':True,'memory_available_at_admission':memory,'duration_seconds':time.monotonic()-start,'MAIN_accepted':False}))
