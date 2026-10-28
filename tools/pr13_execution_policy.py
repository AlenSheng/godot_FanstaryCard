"""Separate human-directed execution deferrals from PR13 acceptance decisions."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

PROFILES = {'OFFLINE', 'POSTGRES', 'LIVE', 'CAPACITY', 'EXPERIMENT', 'RENDER', 'AUDIT'}


def apply_execution_policy(register, decision, source=None):
    if decision.get('schema_version') != 1 or decision.get('authority') != 'human' or decision.get('mode') != 'development_first':
        raise ValueError('Explicit human development-first decision required')
    for key in ('preserve_failed_results', 'preserve_missing_profiles'):
        if decision.get(key) is not True:
            raise ValueError('Execution deferral must retain original results and coverage')
    if decision.get('acceptance_waiver') is not False:
        raise ValueError('Execution scheduling cannot waive acceptance')
    if not isinstance(decision.get('reason'), str) or not decision['reason'].strip():
        raise ValueError('Execution deferral reason required')
    if not isinstance(decision.get('resume_condition'), str) or not decision['resume_condition'].strip():
        raise ValueError('Execution deferral recovery condition required')
    task_ids = decision.get('deferred_task_ids')
    profiles = decision.get('deferred_profiles')
    if not isinstance(task_ids, list) or not all(isinstance(v, str) for v in task_ids) or len(set(task_ids)) != len(task_ids):
        raise ValueError('Unique deferred task IDs required')
    if not isinstance(profiles, list) or not all(isinstance(v, str) for v in profiles) or len(set(profiles)) != len(profiles) or set(profiles) - PROFILES:
        raise ValueError('Unknown or duplicate deferred execution profile')
    tasks = register['tasks']
    known = {task['task_id']: task for task in tasks}
    if len(known) != len(tasks) or set(task_ids) - set(known):
        raise ValueError('Unknown or duplicate runtime task')
    if any(known[task_id]['state'] in ('Accepted', 'NoChangeWithEvidence') for task_id in task_ids):
        raise ValueError('Accepted work cannot be turned into pending work by execution scheduling')
    result = copy.deepcopy(register)
    deferred_tasks = []
    deferred_case_profiles = Counter()
    for task in result['tasks']:
        if task['state'] in ('Accepted', 'NoChangeWithEvidence'):
            continue
        missing = task.get('missing_case_profiles', {})
        affected = {case_id: sorted(set(values) & set(profiles)) for case_id, values in missing.items() if set(values) & set(profiles)}
        explicit = task['task_id'] in task_ids
        if not explicit and not affected:
            continue
        deferred_tasks.append(task['task_id'])
        for values in affected.values():
            deferred_case_profiles.update(values)
        task['execution_deferral'] = {
            'state': 'DeferredByUser', 'authority': 'human', 'acceptance_state': task['state'],
            'whole_task_retest_deferred': explicit, 'deferred_case_profiles': affected,
            'reason': decision['reason'], 'resume_condition': decision['resume_condition'],
            'environment_cause_verified': decision.get('environment_cause_verified') is True,
            'evidence_retained': True, 'acceptance_granted': False,
        }
        task['execution_next_action'] = '先继续后续开发；按恢复条件另行登记这些测试的复测，原验收状态保留。'
    for gate in result.get('gates', []):
        gate['execution_deferred_tasks'] = [task_id for task_id in gate.get('unfinished', []) if task_id in deferred_tasks]
    result['execution_policy'] = {
        'mode': 'development_first', 'authority': 'human', 'source': copy.deepcopy(source),
        'explicit_deferred_task_ids': list(task_ids), 'deferred_profiles': list(profiles),
        'affected_task_ids': deferred_tasks, 'deferred_case_profile_counts': dict(deferred_case_profiles),
        'reason': decision['reason'], 'resume_condition': decision['resume_condition'],
        'acceptance_states_unchanged': True, 'missing_profiles_unchanged': True,
        'development_may_continue': True, 'acceptance_waiver': False,
    }
    return result


def decision_source(path, root):
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Execution decision escaped the repository')
    raw = path.read_bytes()
    return json.loads(raw), {'path': path.relative_to(root.resolve()).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--register', type=Path, required=True)
    parser.add_argument('--decision', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    register = json.loads(args.register.read_text('utf-8'))
    decision, source = decision_source(args.decision, root)
    result = apply_execution_policy(register, decision, source)
    assert not args.output.exists(), 'Retain earlier register snapshots instead of overwriting them'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'acceptance_counts': result['counts'], 'execution_policy': result['execution_policy']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
