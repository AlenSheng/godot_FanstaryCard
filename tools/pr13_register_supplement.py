"""Merge exact validated case/profile evidence without waiving other PR13 work."""
from collections import Counter
import copy
import re


def supplement(register, records, proof):
    if proof.get('native_clean') is not True or proof.get('owned_container_removed') is not True or proof.get('source_inputs_match_git') is not True:
        raise ValueError('Clean native execution, owned cleanup and exact source equivalence required')
    source = proof.get('implementation_source_sha', '')
    if not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('Exact implementation source SHA required')
    tasks = {t['task_id']: t for t in register['tasks']}
    known = {cid: task for task in tasks.values() for cid in task['case_ids']}
    seen = set()
    for record in records:
        cid = record.get('case_id')
        if cid not in known or cid in seen:
            raise ValueError('Unknown or duplicate supplemental case')
        seen.add(cid)
        profiles = record.get('profiles_executed')
        if record.get('executed') is not True or record.get('status') != 'Passed' or not isinstance(profiles, list) or not profiles or set(profiles) - set(known[cid]['profiles']):
            raise ValueError('Only actually passed declared profile evidence may supplement a case')
        if not record.get('actual') or not record.get('evidence'):
            raise ValueError('Actual observations and source evidence required')
    if not records:
        raise ValueError('No supplemental cases')
    result = copy.deepcopy(register)
    updated = {t['task_id']: t for t in result['tasks']}
    affected = set()
    for record in records:
        cid = record['case_id']; original = known[cid]; task = updated[original['task_id']]
        if task['state'] in ('Accepted', 'NoChangeWithEvidence', 'Failed') or task.get('missing_cases'):
            raise ValueError('Supplement cannot override an acceptance, failure or missing-case decision')
        missing = task.get('missing_case_profiles', {}).get(cid, [])
        if not set(missing) & set(record['profiles_executed']):
            raise ValueError('Supplement does not address a currently missing profile')
        remaining = sorted(set(missing) - set(record['profiles_executed']))
        if remaining: task['missing_case_profiles'][cid] = remaining
        else: task['missing_case_profiles'].pop(cid, None)
        history = task.setdefault('case_source_history', {}).setdefault(cid, [])
        prior = task.get('case_source_shas', {}).get(cid)
        if prior and prior not in history: history.append(prior)
        task['case_source_shas'][cid] = source
        task.setdefault('supplemental_case_evidence', []).append(copy.deepcopy(record))
        affected.add(task['task_id'])
    for task_id in affected:
        task = updated[task_id]
        if not task['missing_case_profiles'] and not task['missing_cases']:
            task['state'] = 'ReadyForAcceptance'
            task['accepted_by'] = None
            task['next_action'] = '逐项证据覆盖已补齐；仍须复核依赖和当前来源，由 MAIN 裁决。'
    result['counts']['task_states'] = dict(Counter(t['state'] for t in result['tasks']))
    result.setdefault('case_profile_supplements', []).append({**copy.deepcopy(proof), 'case_ids': sorted(seen), 'affected_tasks': sorted(affected), 'acceptance_granted': False})
    # Gate decisions remain unchanged. Completing evidence cannot sign a gate.
    result['all_accepted'] = False
    return result
