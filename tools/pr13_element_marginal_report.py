"""Paired seed-cluster analysis for the frozen actual elemental replacement matrix.

Encounter outcomes, including censored rows, remain in every denominator.
This reporter never activates candidates or grants acceptance.
"""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

from pr13_candidate_review import paired_clusters, holm_adjust
from pr13_element_marginals import validate, require

PRIMARY=('Damage30','ImmediateCardsDrawn','ObservedAliveControlUnionTicks','EffectiveHeal','EffectiveShield','HealOverflow','ShieldOverflow')
SECONDARY=('NetCards','TotalEffectiveDamage','RequestedImmediateCards','RequestedHeal','RequestedShield','AddedAliveControlUnionTicks','Victory','FinalPoolSize','NoCardsSeconds','LongestEffectiveGapSeconds')


def beta_fraction(a,b,x):
    # Continued fraction for the Student t CDF, avoiding an undeclared library.
    tiny=1e-300;qab=a+b;qap=a+1;qam=a-1;c=1.0;d=1-qab*x/qap
    if abs(d)<tiny:d=tiny
    d=1/d;h=d
    for m in range(1,301):
        aa=m*(b-m)*x/((qam+2*m)*(a+2*m));d=1+aa*d;c=1+aa/c
        if abs(d)<tiny:d=tiny
        if abs(c)<tiny:c=tiny
        d=1/d;h*=d*c
        aa=-(a+m)*(qab+m)*x/((a+2*m)*(qap+2*m));d=1+aa*d;c=1+aa/c
        if abs(d)<tiny:d=tiny
        if abs(c)<tiny:c=tiny
        d=1/d;delta=d*c;h*=delta
        if abs(delta-1)<3e-14:return h
    raise ValueError('Student t continued fraction did not converge')


def beta_regularized(a,b,x):
    if x<=0:return 0.0
    if x>=1:return 1.0
    front=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    return front*beta_fraction(a,b,x)/a if x<(a+1)/(a+b+2) else 1-front*beta_fraction(b,a,1-x)/b


def paired_mean_p(deltas):
    if len(deltas)<2:return 1.0
    mean=statistics.fmean(deltas);variance=statistics.variance(deltas)
    # A deterministic offset is descriptive, not evidence of population variance.
    if variance==0:return 1.0
    t=abs(mean)/math.sqrt(variance/len(deltas));df=len(deltas)-1
    return min(1.0,max(0.0,beta_regularized(df/2,.5,df/(df+t*t))))


def value(row,metric):
    if metric=='NetCards':return row['ImmediateCardsDrawn']+row['NaturalCardsDrawn']-row['CardsSpent']
    if metric=='Victory':return int(row['Outcome']=='Victory')
    return row[metric]


def analyze(inputs,expected_source,analysis_source,*,pilot=False):
    require(len(analysis_source)==40 and all(c in '0123456789abcdef' for c in analysis_source),'Exact analysis source required')
    buckets=defaultdict(dict);parents=[];identities=set();total=0
    for directory in inputs:
        result,rows=validate(directory,expected_source);manifest=json.loads((Path(directory)/'manifest.json').read_text())
        require(tuple(manifest['primary_metrics'])==PRIMARY,'Registered primary family differs')
        if not pilot:require(manifest['samples']==1000 and manifest['seed_start']==400001+1000*manifest['block_index'],'Frozen seed block differs')
        for key,row in rows.items():
            require(key not in identities,'Repeated paired source identity');identities.add(key)
            family=(row['Hero'],row['Deck'],row['Group']);seed=row['Seed'];profile=row['Profile']
            unit=buckets[family].setdefault(seed,{})
            unit[profile]={m:value(row,m) for m in PRIMARY+SECONDARY}|{'Outcome':row['Outcome'],'SeedBlock':row['SeedBlock']}
        parents.append({'path':str(directory),'rows':result['rows'],'manifest_sha256':hashlib.sha256((Path(directory)/'manifest.json').read_bytes()).hexdigest(),'summary_sha256':hashlib.sha256((Path(directory)/'summary.json').read_bytes()).hexdigest()});total+=result['rows']
    expected={(h,c,g) for h in ('Mage','Priest','Guardian') for c in ('ET-WOOD-G','ET-EARTH-G','ET-METAL-G','ET-WATER-G') for g in ('O1','O6','E1','BOSS')}
    require(set(buckets)==expected,'All 48 registered comparisons required before Holm adjustment')
    reports=[];p_values={m:{} for m in PRIMARY}
    for family,units in sorted(buckets.items()):
        if not pilot:require(set(units)==set(range(400001,403001)),'Three nonoverlap thousand-seed blocks required per stratum')
        require(all(set(u)=={'BaselineGreenFire','SingleGreenReplacement'} for u in units.values()),'Every seed requires both actual arms')
        a=[(s,u['BaselineGreenFire']) for s,u in sorted(units.items())];b=[(s,u['SingleGreenReplacement']) for s,u in sorted(units.items())]
        name='/'.join(family);metrics={}
        for metric in PRIMARY+SECONDARY:
            baseline=[{'seed':s,'battle':'encounter','value':r[metric]} for s,r in a];candidate=[{'seed':s,'battle':'encounter','value':r[metric]} for s,r in b]
            stats=paired_clusters(baseline,candidate,resamples=1000,seed=20261010)
            stats['baseline_mean']=statistics.fmean(r[metric] for _,r in a);stats['candidate_mean']=statistics.fmean(r[metric] for _,r in b)
            stats['state']='Inconclusive';stats['reason']='pilot_sample_only' if pilot else 'descriptive_secondary_endpoint'
            if metric in PRIMARY:p_values[metric][name]=paired_mean_p([y['value']-x['value'] for x,y in zip(baseline,candidate)])
            metrics[metric]=stats
        outcomes={arm:dict(Counter(u[arm]['Outcome'] for u in units.values())) for arm in ('BaselineGreenFire','SingleGreenReplacement')}
        reports.append({'family':name,'hero':family[0],'replacement':family[1],'group':family[2],'paired_seeds':len(units),'seed_blocks':dict(Counter(u['BaselineGreenFire']['SeedBlock'] for u in units.values())),'outcomes':outcomes,'metrics':metrics})
    adjusted={metric:holm_adjust(p_values[metric]) for metric in PRIMARY}
    for report in reports:
        high_censoring=any(v.get('Censored',0)/report['paired_seeds']>.10 for v in report['outcomes'].values())
        report['high_censoring']=high_censoring
        for metric in PRIMARY:
            stats=report['metrics'][metric];stats['two_sided_p']=p_values[metric][report['family']];stats['holm_adjusted_p']=adjusted[metric][report['family']];interval=stats['paired_seed_cluster_bootstrap95']
            if not pilot:
                if high_censoring:stats['reason']='censoring_above_frozen_ten_percent'
                elif interval[0]<=0<=interval[1] or stats['holm_adjusted_p']>.05:stats['reason']='difference_not_identified_after_family_correction'
                else:stats['state']='ObservedDifferenceForReview';stats['reason']='paired_difference_identified_not_balance_recommendation'
    return {'schema':'element_marginal_paired_report_v1','source_sha':expected_source,'analysis_source_sha':analysis_source,'rows':total,'families':reports,'parents':parents,'pilot_only':pilot,'full_experiment':not pilot,'primary_metrics':PRIMARY,'secondary_metrics':SECONDARY,
        'statistical_contract':{'unit':'paired independent seed; each encounter retained including censored outcomes','interval':'1000 deterministic paired seed-cluster bootstrap resamples, percentile 95%, seed 20261010','p_value':'two-sided paired mean Student t approximation; zero variance is conservatively p=1','multiple_comparisons':'Holm across all 48 comparisons separately per registered primary metric','high_censoring_threshold':.10,'secondary_endpoints':'descriptive, no family corrected claim','net_cards':'all actual on-play arrivals + natural arrivals - cards spent, not theoretical requests'},
        'balance_recommendation':'Retain defaults; measurements do not establish universal benefit or equivalence','main_acceptance_granted':False,'production_activation':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source',required=True);p.add_argument('--analysis-source',required=True);p.add_argument('--pilot',action='store_true');args=p.parse_args();require(not args.output.exists(),'New report output required')
    result=analyze(args.inputs,args.expected_source,args.analysis_source,pilot=args.pilot);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'ok':True,'rows':result['rows'],'families':len(result['families']),'pilot_only':args.pilot,'main_acceptance_granted':False}))


if __name__=='__main__':main()
