import copy
import unittest
from tools.pr13_register_supplement import supplement


class RegisterSupplementTests(unittest.TestCase):
    def setUp(self):
        self.register = {'counts': {'task_states': {'Partial': 1, 'Failed': 1}}, 'all_accepted': False,
                         'gates': [{'state': 'NotAccepted'}], 'execution_policy': {'mode': 'development_first'},
                         'tasks': [{'task_id': 'new', 'state': 'Partial', 'accepted_by': None, 'profiles': ['OFFLINE', 'RENDER'], 'case_ids': ['one', 'two'], 'missing_cases': [],
                                    'missing_case_profiles': {'one': ['RENDER'], 'two': ['RENDER']}, 'case_source_shas': {'one': 'old', 'two': 'old'}},
                                   {'task_id': 'failed', 'state': 'Failed', 'profiles': ['LIVE'], 'case_ids': ['bad'], 'missing_cases': [], 'missing_case_profiles': {'bad': ['LIVE']}, 'observation': 'actual failure'}]}
        self.proof = {'native_clean': True, 'owned_container_removed': True, 'source_inputs_match_git': True, 'implementation_source_sha': 'a'*40}
        self.records = [{'case_id': cid, 'executed': True, 'status': 'Passed', 'profiles_executed': ['OFFLINE', 'RENDER'], 'actual': {'rows': 6}, 'evidence': ['actual-report']} for cid in ['one', 'two']]

    def test_exact_layers_only_and_other_failure_policy_gates_are_preserved(self):
        before = copy.deepcopy(self.register)
        result = supplement(self.register, self.records[:1], self.proof)
        self.assertEqual(before, self.register)
        self.assertEqual({'two': ['RENDER']}, result['tasks'][0]['missing_case_profiles'])
        self.assertEqual('Partial', result['tasks'][0]['state'])
        self.assertEqual(before['tasks'][1], result['tasks'][1])
        self.assertEqual(before['gates'], result['gates'])
        self.assertEqual(before['execution_policy'], result['execution_policy'])
        self.assertEqual(['old'], result['tasks'][0]['case_source_history']['one'])

    def test_completed_coverage_is_ready_without_signing_acceptance(self):
        result = supplement(self.register, self.records, self.proof)
        self.assertEqual('ReadyForAcceptance', result['tasks'][0]['state'])
        self.assertIsNone(result['tasks'][0]['accepted_by'])
        self.assertFalse(result['all_accepted'])
        self.assertFalse(result['case_profile_supplements'][0]['acceptance_granted'])

    def test_bad_execution_or_unknown_duplicate_profiles_cannot_remove_gaps(self):
        changes = [{'native_clean': False}, {'owned_container_removed': False}, {'source_inputs_match_git': False}, {'implementation_source_sha': 'label'}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError): supplement(self.register, self.records, {**self.proof, **change})
        for records in [self.records*2, [{**self.records[0], 'case_id': 'unknown'}], [{**self.records[0], 'profiles_executed': ['LIVE']}], [{**self.records[0], 'status': 'Failed'}]]:
            with self.subTest(records=records), self.assertRaises(ValueError): supplement(self.register, records, self.proof)

    def test_prior_failed_accepted_or_unexecuted_cases_cannot_be_overridden(self):
        for state in ['Accepted', 'NoChangeWithEvidence', 'Failed']:
            register = copy.deepcopy(self.register); register['tasks'][0]['state'] = state
            with self.subTest(state=state), self.assertRaises(ValueError): supplement(register, self.records, self.proof)
        with self.assertRaises(ValueError): supplement(self.register, [], self.proof)


if __name__ == '__main__': unittest.main()
