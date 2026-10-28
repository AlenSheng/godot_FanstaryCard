"""Tencent-only full-original seed-cluster method replay; no strength activation."""
import collections,gc,hashlib,importlib.util,json,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
P=Path('/inputs');W=Path('/work');OUT=Path('/output')
def require(v,m):
 if not v:raise ValueError(m)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 plan=json.loads((W/'secondary-preregistration.original.json').read_bytes());m=load('original_full_projection',W/'original-projection-validator.py');m.cloud_guard(str(P));require(plan['original_full_encounters']==720000 and plan['original_full_paired_battles']==360000 and plan['original_unique_seed_clusters']==3000 and plan['bootstrap_resamples']==1000 and plan['postcollection_method_replay_only'],'Exact complete secondary method plan required');dataset,units,source=m.validate_projection(str(P),plan['original_analysis_preregistration_sha256'],plan['original_formal_plan_sha256']);require(m.digest(P/'dataset.json')==plan['original_dataset_sha256'] and len(units)==360,'Complete original projection differs');review=load('current_paired_statistics',W/'pr13_candidate_review.py');require(m.digest(W/'pr13_candidate_review.py')==plan['paired_review_source_sha256'],'Exact current statistical source differs')
 baseline=[];candidate=[];outcomes=collections.Counter();seed_battles=collections.Counter();unit_rows=[];canonical_seed={s:s for s in range(440001,443001)}
 for unit in units:
  original=m.stream_rows(unit);identity=unit['identity'];battle='/'.join(str(identity[k]) for k in ['hero','group','element','level']);count=0
  for (seed,arm),row in sorted(original.items()):
   require(seed in canonical_seed and row['Error'] is None,'Exact original seed or error differs');entry={'seed':canonical_seed[seed],'battle':battle,'value':row['ObservedSeconds']};(baseline if arm=='BaselinePurple' else candidate).append(entry);outcomes[row['Outcome']]+=1;count+=1
   if arm=='BaselinePurple':seed_battles[seed]+=1
  require(count==2000,'All original rows required');unit_rows.append({'unit':identity['unit'],'original_encounters':count,'original_encounter_gzip_sha256':m.digest(unit['paths']['encounters'])});del original
 require(len(baseline)==len(candidate)==360000 and set(seed_battles)==set(canonical_seed) and set(seed_battles.values())=={120} and sum(outcomes.values())==720000,'All original 120 battles per 3000 unique seeds required')
 result=review.paired_clusters(baseline,candidate,resamples=1000,seed=20260930);require(result['paired_battles']==360000 and result['independent_seed_clusters']==3000 and result['bootstrap_seed']==20260930 and result['resamples']==1000,'Actual seed-cluster method differs')
 # Controlled incomplete-copy checks; original complete arrays/files stay unchanged.
 controls=[]
 for name,a,b in [('one_actual_baseline_row_removed',baseline[:-1],candidate),('empty',[],[])]:
  try:review.paired_clusters(a,b,resamples=1000,seed=20260930)
  except ValueError as e:controls.append({'name':name,'rejected':True,'reason':str(e),'original_rows_not_modified':True})
  else:raise ValueError('Incomplete original pairing accepted')
 report={'ok':True,'case_id':'PR13-B03.3-T01','implementation_business_sha':plan['original_business_source_sha'],'original_analysis_source_sha':plan['original_analysis_source_sha'],'secondary_current_source_sha':plan['current_source_sha'],'original_encounters':720000,'actual_original_paired_battles':360000,'actual_original_unique_seed_clusters':3000,'actual_battles_per_original_seed':120,'original_independent_seed_blocks':3,'actual_paired_cluster_result':result,'same_seed_repeated_battles_not_counted_as_independent':True,'actual_original_outcomes':dict(outcomes),'controlled_incomplete_pair_checks':controls,'primary_metric':'ObservedSeconds','scope':'Postcollection method contract replay of full immutable actual Domain encounter originals; clustered interval is diagnostic, no confirmatory strength inference, no natural-cycle, capacity, candidate or MAIN acceptance','original_descriptive_statistics_and314_zero_counts_unchanged':True,'no_new_native_encounters_or_samples':True,'original_projection_validator_sha256':m.digest(W/'original-projection-validator.py'),'paired_review_source_sha256':m.digest(W/'pr13_candidate_review.py'),'original_dataset_sha256':plan['original_dataset_sha256'],'formal_EXPERIMENT_case_review_pending':True,'MAIN_accepted':False,'units':unit_rows};p=OUT/'full-original-seed-cluster-method.original.json';require(not p.exists(),'Immutable output exists');p.write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in report.items() if k!='units'}))
if __name__=='__main__':main()
