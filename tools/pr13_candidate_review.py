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


def retain_default_decision(review, *, observed_problem=True, evidence_complete=True):
    """A no-change implementation decision is never a statistical equivalence claim."""
    if not evidence_complete or review.get('reason')=='preregistered_budget_not_met':
        return {'state':'Blocked','reason':'required_evidence_incomplete','production_defaults_retained':True,'production_activation':False}
    if review.get('state') in ('Failed','Blocked'):
        return dict(review,production_defaults_retained=True,production_activation=False)
    if not observed_problem or review.get('state') in ('Inconclusive','NoBenefitForMainReview'):
        return {'state':'NoChangeWithEvidence','reason':'no_supported_change_to_default','underlying_review':review,
                'uncertainty_retained':True,'equivalence_claim':False,'production_defaults_retained':True,'production_activation':False}
    return dict(review,production_activation=False)


def hotspot_target_review(measured_phases, target):
    allowed={'DatabaseAcquire','SqlExecution','PlayerLockRoundTrip','ActorExecute','SocketGateWait','SocketSend'}
    if not measured_phases or set(measured_phases)-allowed or any(not number(v) or v<0 for v in measured_phases.values()):
        raise ValueError('Named measured phase durations required')
    largest=max(measured_phases,key=measured_phases.get)
    localized=target in measured_phases and target==largest
    return dict(state='EligibleForDiagnostics' if localized else 'Blocked',target_phase=target,
                observed_largest_phase=largest,measured_phase_ms=measured_phases,
                reason='candidate_targets_observed_path' if localized else 'candidate_targets_unlocalized_path',
                production_activation=False,service_tail_improvement_proven=False,retain_default=True)


def resource_gap_review(baseline, candidate):
    keys=('resource_per_card','no_cards_seconds')
    if any(not number(r.get(k)) or r[k]<0 for r in (baseline,candidate) for k in keys):
        raise ValueError('Finite resource and empty-hand observations required')
    change={k:candidate[k]-baseline[k] for k in keys}
    return dict(baseline=baseline,candidate=candidate,deltas=change,
                side_effects=['empty_hand_wait_increased'] if change['no_cards_seconds']>0 else [],
                single_card_resource_decreased=change['resource_per_card']<0,
                production_activation=False,retain_default=True)


# Conservative native transport judgments. They never activate a runtime flag.
def transport_review(baseline, candidate):
    """Compare complete fixed-mix observations;successful-only latency cannot excuse failures."""
    import math
    profile_keys=('source_config_hash','request_mix_hash','response_byte_profile_hash','schedule_profile')
    required_counts=('launched','success','failure','pending_final','unexpected_failures')
    for arm in (baseline,candidate):
        if any(type(arm.get(k)) is not int or arm[k]<0 for k in required_counts):raise ValueError('Nonnegative exact outcome counts required')
        if arm['success']+arm['failure']+arm['pending_final']!=arm['launched']:raise ValueError('Every launched request needs exactly one terminal or pending state')
        if arm['unexpected_failures']>arm['failure']:raise ValueError('Unexpected failures exceed observed failures')
        if any(not isinstance(arm.get(k),str) or not arm[k] for k in profile_keys):raise ValueError('Measured workload and response-byte identity required')
        if arm['pending_final']==0 and (type(arm.get('all_terminal_mean_ms')) not in (int,float) or not math.isfinite(arm['all_terminal_mean_ms']) or arm['all_terminal_mean_ms']<0):raise ValueError('Finite all-terminal elapsed mean required')
    common={'production_activation':False,'production_defaults_retained':True,'performance_acceptance':False,'capacity_acceptance':False}
    if min(baseline['launched'],candidate['launched'])<20:return dict(common,state='Unknown',reason='frozen_request_budget_not_met')
    if candidate['unexpected_failures']>baseline['unexpected_failures']:return dict(common,state='Failed',reason='correctness_regression_despite_possible_success_only_latency_gain')
    mismatch=[k for k in profile_keys if baseline[k]!=candidate[k]]
    if baseline['launched']!=candidate['launched']:mismatch.append('launched')
    if mismatch:return dict(common,state='DiagnosticOnly',reason='workload_or_response_bytes_differ',mismatched=mismatch)
    if baseline['pending_final'] or candidate['pending_final']:return dict(common,state='Inconclusive',reason='terminal_outcomes_pending')
    if baseline['unexpected_failures'] or candidate['unexpected_failures']:return dict(common,state='Failed',reason='unexpected_fixture_outcome')
    return dict(common,state='EligibleForPairedRoundReview',reason='correctness_and_workload_profiles_matched',all_terminal_mean_delta_ms=candidate['all_terminal_mean_ms']-baseline['all_terminal_mean_ms'])


def transport_three_round_review(pairs):
    """Exact bounded round-cluster resampling;three clusters do not prove production benefit."""
    import itertools,math,statistics
    if len(pairs)!=3:raise ValueError('Exactly the three frozen paired rounds required')
    reviews=[transport_review(a,b) for a,b in pairs]
    if any(r['state']!='EligibleForPairedRoundReview' for r in reviews):return {'state':'Inconclusive','reason':'not_all_rounds_comparable','round_reviews':reviews,'production_activation':False,'performance_acceptance':False}
    deltas=[r['all_terminal_mean_delta_ms'] for r in reviews];observed=statistics.fmean(deltas)
    bootstrap=sorted(statistics.fmean(deltas[i] for i in indexes) for indexes in itertools.product(range(3),repeat=3))
    null=[statistics.fmean(d*s for d,s in zip(deltas,signs)) for signs in itertools.product((-1,1),repeat=3)]
    p=sum(abs(v)>=abs(observed)-1e-12 for v in null)/len(null)
    return {'state':'Inconclusive','reason':'three_round_precision_not_sufficient_for_95percent_benefit','round_reviews':reviews,'paired_rounds':3,'candidate_minus_baseline_round_mean_ms':deltas,'mean_delta_ms':observed,'exact_round_bootstrap_resamples':27,'descriptive_cluster_bootstrap95_ms':[bootstrap[math.ceil(.025*27)-1],bootstrap[math.ceil(.975*27)-1]],'exact_signflip_states':8,'two_sided_signflip_p':p,'inference_assumption':'independent paired rounds with sign symmetry under null;only3rounds,not a guarantee','bootstrap_interval_precision_guaranteed':False,'production_activation':False,'production_defaults_retained':True,'performance_acceptance':False,'capacity_acceptance':False}
