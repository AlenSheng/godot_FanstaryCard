"""Cloud-only paired-seed continuity statistics; missing strata reject promotion."""
import argparse,hashlib,json,math,random,statistics,sys
from collections import Counter
from pathlib import Path
HEROES=('Mage','Priest','Guardian');STARTS=(479001,480001,481001);CAPS=(0,3,5,8)
def require(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(65536),b''):h.update(data)
 return h.hexdigest()
def quantile(sorted_values,p):
 x=(len(sorted_values)-1)*p;lo=int(x);hi=math.ceil(x);return sorted_values[lo]*(hi-x)+sorted_values[hi]*(x-lo) if hi!=lo else sorted_values[lo]
def paired_binary_bootstrap(differences,resamples,rng):
 # The three outcome differences {-1,0,+1} form the exact empirical seed
 # distribution. Sampling their counts is equivalent to resampling seeds.
 n=len(differences);counts=Counter(differences);require(set(counts)<={-1,0,1},'Invalid binary contrast')
 # Use seed-index draws rather than a Gaussian approximation or independent arms.
 values=[sum(differences[rng.randrange(n)] for _ in range(n))/n for _ in range(resamples)]
 values.sort();discordant=sum(d!=0 for d in differences)
 return {'mean':statistics.fmean(differences),'CI95':[quantile(values,.025),quantile(values,.975)],'CI_familywise95':[quantile(values,.05/18),quantile(values,1-.05/18)],'bootstrap_resamples':resamples,'discordant_seed_pairs':discordant,'precision_insufficient':discordant<20,'empirical_degenerate_interval_is_not_proof_of_zero_population_effect':discordant==0}
def analyze(root,source,resamples):
 rows={};units=[];vectors=[]
 for hero in HEROES:
  for start in STARTS:
   directory=root/f'{hero}-{start}';result_path=directory/'result.json';row_path=directory/'routes.jsonl';require(result_path.is_file() and row_path.is_file(),'All nine formal native units required')
   result=json.loads(result_path.read_text());require(result['ok'] and result['source']==source and result['hero']==hero and result['seedStart']==start and result['seedCount']==1000 and result['routes']==4000 and result['typedRouterIntents'] and not result['developmentSmoke'],'Wrong formal unit, source or smoke counted as formal')
   count=0
   with row_path.open() as stream:
    for line in stream:
     row=json.loads(line);key=(row['hero'],row['seed'],row['capacity']);require(key not in rows and key[0]==hero and start<=key[1]<start+1000 and key[2] in CAPS,'Duplicate or nonpreregistered route')
     require(row['source']==source and row['hiddenOrderNegativeRejected'] and row['instanceConservationChecks']>0 and row['nativeCommandCalls']==row['typedRequestCount'] and 0<row['simulatedSeconds']<=1800.1000001,'Validity, provenance or common budget failed')
     require(row['outcome'] in ('Dead','Extracted','ObservationBudgetCensored'),'Outcome omitted/unknown');require(row['typedRequestBytes']>0 and row['typedResponseBytes']>0,'Actual typed byte measurement absent')
     for item in row['retainedEconomicItems']:require(item['quantity']>=0 and (row['outcome']=='Extracted' or item['isSafe']),'Death assets falsely retained')
     rows[key]=row;count+=1
   require(count==4000,'Incomplete formal unit');units.append({'hero':hero,'seed_start':start,'rows':count,'result_sha256':sha(result_path),'rows_sha256':sha(row_path)})
   p=directory/'render-vectors.jsonl';require(p.is_file(),'Native current render vectors absent');vectors.append({'hero':hero,'seed_start':start,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
 require(len(rows)==36000,'Complete 36000-row matrix required')
 contrasts=[];summaries=[]
 rng=random.Random(482999)
 for hero in HEROES:
  seeds=[start+i for start in STARTS for i in range(1000)];require(len(set(seeds))==3000,'Seed blocks overlap')
  for cap in CAPS:
   arm=[rows[(hero,seed,cap)] for seed in seeds];economy=Counter()
   for row in arm:
    for item in row['retainedEconomicItems']:economy[item['kind']]+=item['quantity']
   summaries.append({'hero':hero,'capacity':cap,'N':3000,'outcomes':dict(Counter(r['outcome'] for r in arm)),'extraction_cumulative_incidence':{str(t):sum(r['outcome']=='Extracted' and r['simulatedSeconds']<=t for r in arm)/3000 for t in (90,180,600,1800)},'observed_seconds_all_outcomes':sum(r['simulatedSeconds'] for r in arm),'core_available_seconds':sum(r['coreAvailableSeconds'] for r in arm),'core_casts':sum(r['coreCasts'] for r in arm),'casts':sum(r['casts'] for r in arm),'typed_request_count':sum(r['typedRequestCount'] for r in arm),'typed_request_bytes':sum(r['typedRequestBytes'] for r in arm),'typed_response_count':sum(r['typedResponseCount'] for r in arm),'typed_response_bytes':sum(r['typedResponseBytes'] for r in arm),'controlled_choice_wait_seconds':sum(r['controlledMonsterChoiceWaitSeconds'] for r in arm),'choice_command_wall_seconds':sum(r['choiceCommandWallSeconds'] for r in arm),'CPU_minutes':sum(r['cpuSeconds'] for r in arm)/60,'wall_minutes':sum(r['wallSeconds'] for r in arm)/60,'native_retained_quantities_by_kind_no_price_conversion':dict(economy)})
  for cap in (3,5,8):
   pairs=[(rows[(hero,seed,0)],rows[(hero,seed,cap)]) for seed in seeds];delta=[int(b['outcome']=='Extracted')-int(a['outcome']=='Extracted') for a,b in pairs];interval=paired_binary_bootstrap(delta,resamples,rng)
   contrasts.append({'hero':hero,'capacity':cap,'paired_seeds':3000,'primary_metric':'Extraction probability by common horizon','primary':interval,'stable_extraction_benefit_established':interval['CI_familywise95'][0]>0 and not interval['precision_insufficient'],'statistical_status':'Inconclusive_low_discordance' if interval['precision_insufficient'] else 'Preregistered_interval_reported','side_effects_separate':{'mean_extra_typed_requests':statistics.fmean(b['typedRequestCount']-a['typedRequestCount'] for a,b in pairs),'mean_extra_controlled_choice_wait_seconds':statistics.fmean(b['controlledMonsterChoiceWaitSeconds']-a['controlledMonsterChoiceWaitSeconds'] for a,b in pairs),'mean_core_available_seconds_change':statistics.fmean(b['coreAvailableSeconds']-a['coreAvailableSeconds'] for a,b in pairs)},'no_completion_only_latency_or_P95_claimed':True})
 return {'ok':True,'source_sha':source,'formal_native_units':9,'formal_routes':36000,'paired_seeds_per_hero':3000,'all_outcomes_retained':True,'default_optional_pool_changed':False,'bootstrap_seed':482999,'multiplicity':'Nine primary comparisons, Bonferroni; 95% unadjusted and familywise-adjusted intervals','units':units,'arm_summaries':summaries,'primary_contrasts':contrasts,'native_render_vectors':vectors,'decision':'CandidateReviewPending' if any(c['stable_extraction_benefit_established'] for c in contrasts) else 'NoChange_stable_benefit_unproven','experience':'Bot_simulation_Partial_humans_excluded','current_Godot_RENDER_and_choice_cost_acceptance_pending':True,'MAIN_accepted':False,'whole_task_accepted':False}
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--source-sha',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bootstrap-resamples',type=int,default=10000);args=parser.parse_args()
 require(sys.platform.startswith('linux'),'Cloud Linux statistics only');require(args.bootstrap_resamples==10000,'Frozen resample budget must not change');require(not args.output.exists(),'Preserve previous statistics');result=analyze(args.root,args.source_sha,args.bootstrap_resamples);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'ok':True,'formal_routes':36000,'decision':result['decision'],'MAIN_accepted':False}))
if __name__=='__main__':main()
