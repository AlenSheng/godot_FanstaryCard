import copy
import unittest

from tools.pr13_execution_policy import apply_execution_policy


class ExecutionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.register = {'counts': {'tasks': 3, 'task_states': {'Accepted': 1, 'Failed': 1, 'Partial': 1}},
                         'all_accepted': False, 'human_experience_scope': {'in_scope': False},
                         'tasks': [
                             {'task_id': 'done', 'state': 'Accepted', 'profiles': ['CAPACITY'], 'missing_case_profiles': {}, 'evidence': ['old-proof']},
                             {'task_id': 'failed', 'state': 'Failed', 'profiles': ['LIVE'], 'missing_case_profiles': {'failed-T1': ['LIVE']}, 'observation': {'reason': 'timeout'}},
                             {'task_id': 'pending', 'state': 'Partial', 'profiles': ['OFFLINE', 'CAPACITY'], 'missing_case_profiles': {'pending-T1': ['CAPACITY', 'POSTGRES']}, 'case_source_shas': {'pending-T1': 'actual-sha'}},
                         ], 'gates': [{'gate_id': 'G4', 'state': 'NotAccepted', 'unfinished': ['failed', 'pending']}]}
        self.decision = {'schema_version': 1, 'authority': 'human', 'mode': 'development_first',
                         'deferred_task_ids': ['failed'], 'deferred_profiles': ['CAPACITY'],
                         'reason': 'User defers environment-dependent tests', 'resume_condition': 'Explicit later rerun',
                         'preserve_failed_results': True, 'preserve_missing_profiles': True, 'acceptance_waiver': False}

    def test_deferral_keeps_failure_evidence_profiles_gates_and_input_immutable(self):
        before = copy.deepcopy(self.register)
        result = apply_execution_policy(self.register, self.decision)
        self.assertEqual(before, self.register)
        self.assertEqual(before['counts'], result['counts'])
        self.assertEqual(before['tasks'][0], result['tasks'][0])
        for old, new in zip(before['tasks'], result['tasks']):
            for key in old:
                self.assertEqual(old[key], new[key])
        self.assertEqual('Failed', result['tasks'][1]['state'])
        self.assertFalse(result['tasks'][1]['execution_deferral']['environment_cause_verified'])
        self.assertEqual({'pending-T1': ['CAPACITY']}, result['tasks'][2]['execution_deferral']['deferred_case_profiles'])
        self.assertEqual('NotAccepted', result['gates'][0]['state'])
        self.assertEqual(['failed', 'pending'], result['gates'][0]['execution_deferred_tasks'])
        self.assertFalse(result['all_accepted'])

    def test_unknown_duplicate_and_accepted_tasks_are_rejected(self):
        for task_ids in [['unknown'], ['failed', 'failed'], ['done']]:
            with self.subTest(task_ids=task_ids), self.assertRaises(ValueError):
                apply_execution_policy(self.register, {**self.decision, 'deferred_task_ids': task_ids})

    def test_no_authority_waiver_or_hidden_coverage_removal(self):
        for change in [{'authority': 'bot'}, {'acceptance_waiver': True}, {'preserve_failed_results': False},
                       {'preserve_missing_profiles': False}, {'resume_condition': ''}, {'reason': ''}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                apply_execution_policy(self.register, {**self.decision, **change})

    def test_profiles_are_exact_and_accepted_work_is_not_rescheduled(self):
        for profiles in [['UNKNOWN'], ['CAPACITY', 'CAPACITY'], 'CAPACITY']:
            with self.subTest(profiles=profiles), self.assertRaises(ValueError):
                apply_execution_policy(self.register, {**self.decision, 'deferred_profiles': profiles})
        result = apply_execution_policy(self.register, {**self.decision, 'deferred_task_ids': [], 'deferred_profiles': ['LIVE']})
        self.assertEqual(self.register['tasks'][0], result['tasks'][0])
        self.assertEqual(['failed'], result['execution_policy']['affected_task_ids'])


if __name__ == '__main__':
    unittest.main()
