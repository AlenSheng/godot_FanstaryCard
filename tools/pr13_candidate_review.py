"""Bounded paired seed statistics and conservative candidate review contracts.

Review states are proposals for MAIN. They never enable runtime candidates or
prove capacity, human experience, or unobserved scenario correctness.
"""
from collections import defaultdict
import math
import random
import statistics

def number(value):return type(value) in (int,float) and math.isfinite(value)

def paired_clusters(baseline,candidate,*,resamples=1000,seed=20260930):
    if type(resamples) is not int or not 100<=resamples<=10000:raise ValueError('Bounded bootstrap budget required')
    def keyed(rows):
        result={}
        for row in rows:
            key=(row['seed'],row['battle'])
            if type(key[0]) is not int or key in result or not number(row['value']):raise ValueError('Invalid/duplicate paired unit')
            result[key]=row['value']
        return result
    a=keyed(baseline);b=keyed(candidate)
    if not a or a.keys()!=b.keys():raise ValueError('All paired battles, including unfinished outcomes, must remain present')
    clusters=defaultdict(list)
    for identity in sorted(a):clusters[identity[0]].append(b[identity]-a[identity])
    # Every selected seed carries all its battles together. Equal seed weights
    # match the preregistered seed unit, rather than treating repeated battles as
    # independent draws or letting a seed with extra battles dominate.
    values=[statistics.fmean(v) for v in clusters.values()]
    rng=random.Random(seed)
    samples=sorted(statistics.fmean(rng.choices(values,k=len(values))) for _ in range(resamples))
    lo=max(0,math.ceil(.025*resamples)-1);hi=min(resamples-1,math.ceil(.975*resamples)-1)
    return {'paired_battles':len(a),'independent_seed_clusters':len(values),'mean_delta':statistics.fmean(values),
        'paired_seed_cluster_bootstrap95':[samples[lo],samples[hi]],'bootstrap_seed':seed,'resamples':resamples,
        'precision_guaranteed':False,'capacity_acceptance':False,'production_activation':False}

def holm_adjust(p_values):
    if not p_values or any(not number(p) or not 0<=p<=1 for p in p_values.values()):raise ValueError('Finite registered family p-values required')
    ordered=sorted(p_values.items(),key=lambda row:(row[1],row[0]));adjusted={};last=0.0
    for rank,(name,p) in enumerate(ordered):
        last=max(last,min(1.0,p*(len(ordered)-rank)));adjusted[name]=last
    return adjusted

def tail_evidence(values,*,quantile=.99,minimum_samples=3000):
    if not number(quantile) or not 0<quantile<1 or type(minimum_samples) is not int or minimum_samples<1:raise ValueError('Frozen tail sample contract required')
    if len(values)>1000000 or any(not number(v) or v<0 for v in values):raise ValueError('Invalid/bounded tail observations required')
    if len(values)<minimum_samples:return {'state':'Unknown','n':len(values),'required_n':minimum_samples,'quantile':quantile,'value':None,'reason':'sample_count_below_preregistered_floor'}
    return {'state':'ObservedForReview','n':len(values),'required_n':minimum_samples,'quantile':quantile,'value':sorted(values)[math.ceil(quantile*len(values))-1],'acceptance':False}

def gameplay_review(*,improvement,interval,p_values,primary,drifts,correctness=True,scenarios_complete=True,budget_met=True):
    if not number(improvement) or len(interval)!=2 or not all(number(v) for v in interval) or interval[0]>interval[1]:raise ValueError('Finite ordered improvement interval required')
    if primary not in p_values:raise ValueError('Primary endpoint not in frozen comparison family')
    adjusted=holm_adjust(p_values)
    risk={k:v for k,v in drifts.items() if not number(v) or abs(v)>.05}
    if not correctness:state='Failed';reason='correctness_failure'
    elif risk:state='Blocked';reason='strength_or_economy_drift_requires_review'
    elif not scenarios_complete:state='Blocked';reason='required_scenario_unobserved'
    elif not budget_met:state='Inconclusive';reason='preregistered_budget_not_met'
    elif interval[0]<=0 or adjusted[primary]>.05:state='Inconclusive';reason='benefit_not_identified_after_family_correction'
    elif improvement<.15 or interval[0]<.15:state='Inconclusive';reason='proposed_tail_improvement_threshold_not_identified'
    else:state='EligibleForMainReview';reason='isolated_candidate_threshold_and_risk_checks_met'
    return {'state':state,'reason':reason,'point_improvement':improvement,'improvement_interval95':interval,
        'holm_adjusted_p':adjusted,'drifts':drifts,'risk_drift':risk,'production_defaults_retained':True,
        'production_activation':False,'capacity_acceptance':False,'human_experience_acceptance':False}

def performance_review(baseline,candidate):
    keys=('source_config_hash','request_mix_hash','gameplay_profile','effective_limit_hash','window_seconds')
    differences=[k for k in keys if baseline.get(k) is None or baseline.get(k)!=candidate.get(k)]
    if differences:return {'state':'DiagnosticOnly','mismatched_inputs':differences,'performance_acceptance':False}
    numeric=('n','request_rate','error_rate','p95_ms')
    if any(not number(r.get(k)) for r in (baseline,candidate) for k in numeric):return {'state':'Unknown','reason':'metric_unavailable','performance_acceptance':False}
    if min(baseline['n'],candidate['n'])<20:return {'state':'Unknown','reason':'sample_count_below_contract','performance_acceptance':False}
    if not baseline.get('load_passed') or not candidate.get('load_passed'):return {'state':'Failed','reason':'original_load_contract_failed','performance_acceptance':False}
    if candidate['request_rate']<baseline['request_rate'] or candidate['error_rate']>baseline['error_rate']:
        return {'state':'Inconclusive','reason':'lower_work_or_higher_failures','performance_acceptance':False}
    return {'state':'EligibleForMainReview' if candidate['p95_ms']<baseline['p95_ms'] else 'NoBenefitForMainReview',
        'performance_acceptance':False,'retain_default':True,'p95_delta_ms':candidate['p95_ms']-baseline['p95_ms']}
