"""Tencent-only bounded retained-field statistics with the human-revised balanced denominator of 540 parts.

Inputs are original encounter gzip files, manifests, summaries, validated-part
reports and G receipts restored byte-for-byte from the primary G archive.
Final case approval, rendered layers and production changes remain separate.
"""
import argparse,gzip,hashlib,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path
from pr13_candidate_review import paired_clusters

HEROES=['Mage','Priest','Guardian'];GROUPS=['O1','O6','E1','BOSS'];STRATEGIES=['baseline_all_hand','basic','build'];ARMS=['ActualPublishedDefault','SingleCardCandidate'];OUTCOMES=['Victory','Death','Censored','Error']
def require(ok,reason):
 if not ok:raise ValueError(reason)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def original_rows(directory):
 d=Path(directory);m=json.loads((d/'manifest.original.json').read_bytes());s=json.loads((d/'summary.original.json').read_bytes());v=json.loads((d/'independent-part-validation.original.json').read_bytes());receipt=json.loads((d/'local-G-receipt.original.json').read_bytes());require(receipt['ok'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified'],'Original G custody incomplete');require(v['ok'] and v['samples']==m['samples']==20 and v['encounters']==s['actual_encounters']==40 and s['passed'] and s['actual_errors']==0,'Original physical unit incomplete');p=d/'encounters.original.jsonl.gz';require(p.stat().st_size==s['stored_bytes'] and sha(p)==s['stored_sha256'],'Original encounter compressed bytes differ');h=hashlib.sha256();n=0;count=0
 with gzip.open(p,'rb') as f:
  for raw in f:h.update(raw);n+=len(raw);count+=1;yield m,v,json.loads(raw)
 require(count==40 and n==s['original_raw_bytes'] and h.hexdigest()==s['original_raw_sha256'],'Original raw encounter bytes or rows differ')
def quantiles(values):
 xs=sorted(values);require(xs,'Empty observed denominator')
 return {str(p):xs[int((len(xs)-1)*p)] for p in [.1,.5,.9,.95,.99]}
def wilson(success,total):
 require(total>0,'Empty event denominator');z=1.95996398454054;p=success/total;den=1+z*z/total;center=(p+z*z/(2*total))/den;half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den;return [max(0,center-half),min(1,center+half)]
METRICS={
 'victory_indicator':lambda r:int(r['Outcome']=='Victory'),
 'death_indicator':lambda r:int(r['Outcome']=='Death'),
 'censored_indicator':lambda r:int(r['Outcome']=='Censored'),
 'observed_seconds_all_outcomes':lambda r:r['ObservedSeconds'],
 'effective_action_ratio':lambda r:r['EffectiveActions']/max(1,r['Actions']),
 'no_cards_ratio':lambda r:r['NoCardsSeconds']/max(.1,r['ObservedSeconds']),
 'strategy_hold_ratio':lambda r:r['StrategyHoldSeconds']/max(.1,r['ObservedSeconds']),
 'heal_overflow':lambda r:r['HealOverflow'],
 'shield_overflow':lambda r:r['ShieldOverflow']}
PROJECTED_FIELDS=('Actions', 'CardsSpent', 'EffectiveActions', 'EffectiveHeal', 'EffectiveShield', 'Error', 'Group', 'HealOverflow', 'Hero', 'ImmediateCardsDrawn', 'NaturalCardsDrawn', 'NoCardsSeconds', 'ObservedSeconds', 'Outcome', 'Profile', 'RequestedHeal', 'RequestedShield', 'Seed', 'SeedBlock', 'ShieldOverflow', 'Strategy', 'StrategyHoldSeconds')
def compact_original_row(row):
 require(all(k in row for k in PROJECTED_FIELDS),"Original required analysis field missing")
 return {k:row[k] for k in PROJECTED_FIELDS}

def main():
 a=argparse.ArgumentParser();a.add_argument('--parts-index',type=Path,required=True);a.add_argument('--plan',type=Path,required=True);a.add_argument('--config-reference',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args();require(not args.output.exists(),'Final immutable output already exists');plan=json.loads(args.plan.read_bytes());require(sha(args.config_reference)==plan['config_reference_sha256'],'Frozen reference SHA differs');reference=json.loads(args.config_reference.read_bytes());index=json.loads(args.parts_index.read_bytes());require(plan['expected_encounters']==21600 and len(plan['units'])==540 and plan['required_paired_seeds_per_stratum']==300,'Original quota changed');require(len(index['parts'])==540,'All original physical parts required');expected_units={u['unit']:u for u in plan['units']};seen_units=set();seen=set();strata=defaultdict(list);outcomes=Counter();coverage=Counter();config_hashes=set();metadata=[]
 for part in index['parts']:
  name=part['unit'];require(name in expected_units and name not in seen_units,'Unknown or duplicate physical part');seen_units.add(name);spec=expected_units[name];d=Path(part['directory']);manifest=json.loads((d/'manifest.original.json').read_bytes());validation=json.loads((d/'independent-part-validation.original.json').read_bytes());require(manifest['source_sha']==plan['source_sha'] and manifest['hero']==spec['hero'] and manifest['group']==spec['group'] and manifest['strategy']==spec['strategy'] and manifest['block']==spec['block'] and manifest['offset']==spec['offset'],'Original physical stratum differs');require(manifest['seed_start']==450001+1000*spec['block']+spec['offset'] and manifest['samples']==20,'Original seeds differ');require(manifest['fixed_effective_rules']==reference['fixed_effective_rules'] and manifest['embedded_resource_bytes_sha256']==reference['embedded_resource_bytes_sha256'],'Actual frozen effective input differs');config_hashes.add((manifest['config_sha256'],manifest['embedded_resource_bytes_sha256']));coverage['actual_reshuffle_witnesses']+=validation['actual_reshuffle_witnesses'];coverage.update({('waiting:'+k):v for k,v in validation['wait_reason_counts'].items()});metadata.append({'unit':name,'original_encounter_gzip_sha256':sha(d/'encounters.original.jsonl.gz'),'original_validation_sha256':sha(d/'independent-part-validation.original.json')})
  for m,v,r in original_rows(d):
   key=(r['Hero'],r['Group'],r['Strategy'],r['SeedBlock'],r['Seed'],r['Profile']);require(key not in seen,'Overlapping or duplicate original encounter');seen.add(key);require(r['Profile'] in ARMS and r['Outcome'] in OUTCOMES and r['Error'] is None,'Actual error or profile mismatch');require(r['SeedBlock']==spec['block'] and 450001+1000*spec['block']<=r['Seed']<451001+1000*spec['block'],'Wrong original seed block');require(0<=r['ObservedSeconds']<=600 and 0<=r['EffectiveActions']<=r['Actions'],'Outcome metrics invalid');outcomes[r['Outcome']]+=1;strata[(r['Hero'],r['Group'],r['Strategy'])].append(compact_original_row(r))
 require(seen_units==set(expected_units) and len(seen)==21600 and len(strata)==36 and len(config_hashes)==1,'Complete original global denominator differs');reports=[];complete_seeds={450001+1000*b+i for b in range(3) for i in range(100)}
 for identity,rows in sorted(strata.items()):
  require(len(rows)==600,'Original stratum denominator differs');by={arm:[r for r in rows if r['Profile']==arm] for arm in ARMS}
  for arm,selected in by.items():require(len(selected)==300 and {r['Seed'] for r in selected}==complete_seeds and all(sum(r['SeedBlock']==b for r in selected)==100 for b in range(3)),'Three human-revised 100 paired-seed blocks required')
  summaries={}
  for arm,selected in by.items():
   counts=Counter(r['Outcome'] for r in selected);seconds=[r['ObservedSeconds'] for r in selected];summaries[arm]={'all_original_outcomes':{k:counts[k] for k in OUTCOMES},'total':300,'victory_rate_wilson95':wilson(counts['Victory'],300),'death_rate_wilson95':wilson(counts['Death'],300),'observed_time_all_outcome_quantiles':quantiles(seconds),'conditional_victory_time_quantiles':quantiles([r['ObservedSeconds'] for r in selected if r['Outcome']=='Victory']) if counts['Victory'] else None,'censored_time_not_dropped':True,'natural_draws':sum(r['NaturalCardsDrawn'] for r in selected),'immediate_draws':sum(r['ImmediateCardsDrawn'] for r in selected),'cards_spent':sum(r['CardsSpent'] for r in selected),'requested_heal':sum(r['RequestedHeal'] for r in selected),'effective_heal':sum(r['EffectiveHeal'] for r in selected),'heal_overflow':sum(r['HealOverflow'] for r in selected),'requested_shield':sum(r['RequestedShield'] for r in selected),'effective_shield':sum(r['EffectiveShield'] for r in selected),'shield_overflow':sum(r['ShieldOverflow'] for r in selected)}
  comparisons={}
  for name,metric in METRICS.items():
   values={arm:[{'seed':r['Seed'],'battle':'first-encounter','value':metric(r)} for r in selected] for arm,selected in by.items()};comparisons[name]=paired_clusters(values[ARMS[0]],values[ARMS[1]],resamples=1000,seed=20260930)
  reports.append({'hero':identity[0],'group':identity[1],'strategy':identity[2],'actual_paired_seeds':300,'independent_blocks':3,'arm_denominators':summaries,'paired_seed_cluster_intervals':comparisons,'no_strength_decision_from_click_rate_only':True})
 report={'ok':True,'source_sha':plan['source_sha'],'original_parts':540,'original_encounters':21600,'original_strata':36,'outcomes_full_denominator':{k:outcomes[k] for k in OUTCOMES},'coverage':dict(coverage),'levels':reports,'all_original_part_identities':metadata,'requested_vs_effective_resources_reported':True,'human_authorized_sample_reduction_factor':10,'original_large_study_primary_target':5400,'revised_primary_target':540,'original_supplementary_results_retained':True,'default_config_no_change':True,'only_one_card_factor':True,'censored_and_death_not_removed_from_pairing':True,'retained_original_analysis_fields':list(PROJECTED_FIELDS),'unused_original_fields_remain_in_byte_exact_parent':True,'full_case_specific_coverage_review_pending':True,'source_workbook_mapping_and_RENDER_still_separate':True,'precision_guaranteed':False,'production_activation':False,'MAIN_accepted':False};args.output.mkdir();(args.output/'final-statistics.original.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in report.items() if k not in ['levels','all_original_part_identities']}))
if __name__=='__main__':main()
