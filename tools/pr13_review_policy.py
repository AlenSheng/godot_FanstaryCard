"""Keep specification readiness, runtime coverage and human evidence distinct."""

HUMAN_TASKS={'PR13-B11.4','PR13-B12.2','PR13-B12.4'}


def human_complete(evidence):
    if not isinstance(evidence,dict) or evidence.get('authority')!='MAIN' or not evidence.get('verified_source_files'):return False
    people=evidence.get('participants',[])
    if len(people)<6 or len({p.get('participant_id') for p in people})!=len(people):return False
    if not {'Mage','Priest','Guardian'}.issubset({p.get('hero_class') for p in people}):return False
    return all(p.get('participant_kind')=='human' and p.get('skill_band') and len(set(p.get('natural_cycle_ids',[])))>=3 for p in people)


def execution_state(records, required_profiles, *, human_required=False, human_evidence=None):
    if any(r.get('status')=='Failed' for r in records):return 'Failed'
    passed=[r for r in records if r.get('executed') is True and r.get('status')=='Passed']
    if len(passed)!=len(records) or not records:return 'Partial' if passed else 'Queued'
    if any(set(required_profiles)-set(r.get('profiles_executed',[])) for r in passed):return 'Partial'
    if human_required and not human_complete(human_evidence):return 'Partial'
    return 'ReadyForAcceptance'


def candidate_matrix(default_passed, on_runs, required_candidates):
    if not default_passed:return dict(state='Failed',reason='default_off_regression',production_activation=False)
    missing=[name for name in required_candidates if not on_runs.get(name,{}).get('all_required_layers_executed')]
    if missing:return dict(state='Blocked',reason='candidate_on_layer_missing',missing_candidates=missing,production_activation=False)
    if any(r.get('correctness_passed') is not True for r in on_runs.values()):return dict(state='Failed',reason='candidate_correctness_failure',production_activation=False)
    return dict(state='ReadyForMainReview',production_activation=False)


def deployment_claim(*,pr_closed=False,restored_environment_hash=None,current_health_verified=None):
    return dict(code_review_closed=bool(pr_closed),historical_environment_restoration_recorded=bool(restored_environment_hash),
                current_runtime_health='Unknown' if current_health_verified is None else ('Verified' if current_health_verified else 'Failed'),
                runtime_rollback_verified=False,reason='Code review state and a historical file restoration do not verify a current deployed runtime.')


def history_claim(passed,skipped,*,raw_reconciled=False):
    return dict(historical_passed=passed,historical_skipped=skipped,current_passed=0,
                comparison_state='ReconciledForReview' if raw_reconciled else 'Blocked',runtime_revalidated=False)


def asset_gate(alerts):
    unresolved=[a['id'] for a in alerts if a.get('explained') is not True]
    return dict(state='Blocked' if unresolved else 'ReadyForMainReview',unexplained_alerts=unresolved,asset_acceptance=False)
