"""Full paired encounter report, separate from contract and GUI acceptance."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import json
import statistics
from pathlib import Path
from pr13_candidate_review import paired_clusters,holm_adjust
from pr13_element_marginal_report import paired_mean_p
from pr13_tuning_recovery_experiment import require,validate

PRIMARY=('Damage30','ImmediateCardsDrawn','ObservedAliveControlUnionTicks','EffectiveHeal','EffectiveShield','HealOverflow','ShieldOverflow')
ARMS=('BaselineGreenWater','SingleGreenReplacement')

def analyze(inputs,source,analysis_source,pilot=False):
    require(len(analysis_source)==40 and all(c in '0123456789abcdef' for c in analysis_source),'Exact analysis source required')
    buckets=defaultdict(dict);units=set();parents=[];totals=Counter();applicability=defaultdict(Counter)
    for directory in inputs:
        directory=Path(directory);verified=validate(directory,source);manifest=json.loads((directory/'manifest.json').read_text());family=(manifest['hero'],manifest['alternative'],manifest['group']);unit=family+(manifest['block_index'],)
        require(unit not in units,'Duplicate declared unit');units.add(unit)
        if not pilot:require(manifest['samples']==1000,'Full unit requires thousand paired seeds')
        for key,value in verified['case_denominators'].items():applicability[family][key]+=value
        with gzip.open(directory/'encounters.jsonl.gz','rt') as f:
            for text in f:
                row=json.loads(text);pair=buckets[family].setdefault(row['Seed'],{});require(row['Profile'] not in pair,'Duplicate paired encounter')
                pair[row['Profile']]={m:row[m] for m in PRIMARY}|{'Outcome':row['Outcome'],'SeedBlock':row['SeedBlock']};totals['rows']+=1
        parents.append({'directory':str(directory),'manifest_sha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),'validation':verified})
    expected={(hero,card,group) for hero in ['Mage','Priest','Guardian'] for card in ['ET-WOOD-G','ET-EARTH-G','ET-METAL-G'] for group in ['O1','O6','E1','BOSS']}
    require(set(buckets)==expected,'All 36 comparison families required')
    if not pilot:require(units=={f+(block,) for f in expected for block in [0,1,2]} and totals['rows']==216000,'All 108 full units and 216000 rows required')
    reports=[];p_values={metric:{} for metric in PRIMARY};case_gaps=[]
    for family,pairs in sorted(buckets.items()):
        if not pilot:require(set(pairs)==set(range(420001,423001)),'Three independent thousand-seed blocks required')
        require(all(set(p)==set(ARMS) for p in pairs.values()),'Every seed requires both original arms');name='/'.join(family);metrics={}
        for metric in PRIMARY:
            left=[{'seed':s,'battle':'encounter','value':p[ARMS[0]][metric]} for s,p in sorted(pairs.items())];right=[{'seed':s,'battle':'encounter','value':p[ARMS[1]][metric]} for s,p in sorted(pairs.items())]
            stats=paired_clusters(left,right,resamples=1000,seed=20261010);stats['baseline_mean']=statistics.fmean(v['value'] for v in left);stats['candidate_mean']=statistics.fmean(v['value'] for v in right);stats['state']='Inconclusive';metrics[metric]=stats
            p_values[metric][name]=paired_mean_p([b['value']-a['value'] for a,b in zip(left,right)])
        denominators=dict(applicability[family])
        for arm in ARMS:
            for case in ['T01','T02','T03']:
                if denominators.get(arm+'/'+case+'_applicable',0)==0:case_gaps.append({'family':name,'arm':arm,'case':case,'reason':'No applicable cast observed'})
        outcomes={arm:dict(Counter(p[arm]['Outcome'] for p in pairs.values())) for arm in ARMS}
        reports.append({'family':name,'paired_seeds':len(pairs),'seed_blocks':dict(Counter(p[ARMS[0]]['SeedBlock'] for p in pairs.values())),'outcomes':outcomes,'censor_ratios':{arm:outcomes[arm].get('Censored',0)/len(pairs) for arm in ARMS},'case_denominators':denominators,'metrics':metrics})
    adjusted={metric:holm_adjust(p_values[metric]) for metric in PRIMARY}
    for report in reports:
        for metric,stats in report['metrics'].items():
            stats['two_sided_p']=p_values[metric][report['family']];stats['holm_adjusted_p']=adjusted[metric][report['family']];interval=stats['paired_seed_cluster_bootstrap95']
            stats['reason']='pilot_only' if pilot else 'No paired difference identified after correction'
            if not pilot and not interval[0]<=0<=interval[1] and stats['holm_adjusted_p']<=.05:
                stats['state']='ObservedDifferenceForReview';stats['reason']='Measured paired card replacement effect; not a balance recommendation'
    return {'schema':'tuning_recovery_full_paired_report_v1','source_sha':source,'analysis_source_sha':analysis_source,'rows':totals['rows'],'pairs':totals['rows']//2,'families':reports,'parents':parents,'pilot_only':pilot,'full_experiment':not pilot,'case_coverage_gaps':case_gaps,'required_cases_accepted':False,'primary_metrics':PRIMARY,'statistical_contract':{'interval':'1000 deterministic paired seed-cluster percentile 95% bootstrap; seed 20261010','p_value':'Paired mean Student t approximation; zero variance p=1, no equivalence claim','multiplicity':'Holm across 36 families per primary metric','outcomes':'All Victory/Death/Censored observations retained; longer fights are not contract failures'},'balance_recommendation':'NoChange unless independently reproduced contract defect; effect deltas alone do not justify buffs or nerfs','production_activation':False,'main_acceptance_granted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--source-sha',required=True);p.add_argument('--analysis-source',required=True);p.add_argument('--output',required=True);p.add_argument('--pilot',action='store_true');a=p.parse_args();require(not Path(a.output).exists(),'New report required');r=analyze(a.inputs,a.source_sha,a.analysis_source,a.pilot);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'ok':True,'rows':r['rows'],'pairs':r['pairs'],'families':len(r['families']),'case_coverage_gaps':len(r['case_coverage_gaps']),'full_experiment':r['full_experiment'],'main_acceptance_granted':False}))
