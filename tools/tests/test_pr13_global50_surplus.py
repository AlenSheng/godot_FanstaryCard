"""Synthetic count counterexamples; never live capacity evidence."""
import tempfile
import unittest

from tools.tests.test_pr13_distributed_capacity import SyntheticStudy


class GlobalFiftyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr13-global50-')
        self.addCleanup(self.temp.cleanup)
        self.study = SyntheticStudy(self.temp.name, global_surplus=True)

    def counts(self, windows, cloud):
        for host, count in [('windows', windows), ('cloud', cloud)]:
            r = self.study.report(host)
            for row in r['samples']:
                if row['active_in_room']:
                    row['active_in_room'] = count
            self.study.put_report(host, r)

    def test_full60_supply_can_prove_only_registered_global50(self):
        self.assertNotIn('user_id',self.study.report('windows')['final_clients'][0])
        result = self.study.assess()
        self.assertTrue(result['capacity_accepted'], result)
        self.assertEqual((60, 50), (result['participants'], result['target_active']))
        self.assertEqual(50, result['overlap']['actual_native_active_required'])
        self.assertFalse(result['whole_project_accepted'])

    def test_actual30plus20_is50_despite_local_floors25plus15(self):
        self.counts(30, 20)
        self.assertTrue(self.study.assess()['capacity_accepted'])

    def test_local40_cannot_borrow_server_gauge50_or_supply60(self):
        self.counts(25, 15)
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_49_actual_native_active_never_proves50(self):
        self.counts(29, 20)
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_different_time_peaks_cannot_be_added_to50(self):
        for host in ('windows', 'cloud'):
            r = self.study.report(host)
            for index, row in enumerate(r['samples']):
                if row['active_in_room']:
                    row['active_in_room'] = (30 if index < 60 else 29) if host == 'windows' else (19 if index < 60 else 20)
            self.study.put_report(host, r)
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_changing_distribution_can_keep_global50(self):
        for host in ('windows', 'cloud'):
            r = self.study.report(host)
            for index, row in enumerate(r['samples']):
                if row['active_in_room']:
                    row['active_in_room'] = (35 if index < 60 else 25) if host == 'windows' else (15 if index < 60 else 25)
            self.study.put_report(host, r)
        self.assertTrue(self.study.assess()['capacity_accepted'])

    def test_global_server49_still_fails_with60_native_views(self):
        for host in ('windows', 'cloud'):
            r = self.study.report(host)
            for row in r['samples']:
                row['server_confirmed_in_room'] = 49
            self.study.put_report(host, r)
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_59_launched_processes_cannot_be_relabelled60(self):
        r = self.study.report('cloud')
        r['clients'] = 24
        self.study.put_report('cloud', r)
        self.assertIn('cohort_count_mismatch', self.study.assess()['evidence_errors'])

    def test_low_memory_is_not_a_profile_exception(self):
        r = self.study.get('windows', 'supervisor.json')
        r['resources'][50]['memory_available_bytes'] = 6442450943
        self.study.put('windows', 'supervisor.json', r)
        self.assertIn('host_memory_reserve_breached', self.study.assess()['evidence_errors'])

    def test_original_failed_execution_remains_failed_without_explicit_policy(self):
        r = self.study.report('windows')
        r['outcome']['passed'] = False
        self.study.put_report('windows', r)
        self.assertIn('original_cohort_did_not_pass', self.study.assess()['evidence_errors'])

    def test_new_profile_cannot_be_labelled100(self):
        self.study.spec['target_clients'] = 100
        self.study.spec['target_online_clients'] = 100
        self.study.bind_spec()
        self.assertFalse(self.study.assess()['capacity_accepted'])

    def test_unknown_native_error_cannot_be_hidden_by_claimed_review(self):
        self.study.change_native('windows',0,lambda n:n.update(errors=[{'at_unix_ms':1,'message':'unknown genuine failure'}]))
        r=self.study.report('windows')
        r['final_clients'][0]['errors']=[{'at_unix_ms':1,'message':'unknown genuine failure'}]
        self.study.put_report('windows',r)
        self.assertIn('authority_transition_replay_failed',self.study.assess()['evidence_errors'])

    def test_reported_policy_verdict_must_equal_raw_replay(self):
        r=self.study.report('windows');r['authority_transition_review']['verified_completed_play_requests']=10000
        self.study.put_report('windows',r)
        self.assertIn('authority_transition_replay_failed',self.study.assess()['evidence_errors'])

    def test_policy_must_be_registered_and_frozen(self):
        del self.study.spec['authority_transition_policy'];self.study.bind_spec()
        self.assertIn('global50_authority_policy_not_registered',self.study.assess()['evidence_errors'])

    def test_policy_source_hash_is_not_optional(self):
        del self.study.reference['controls']['tools/pr13_authority_transitions.py']
        self.assertIn('policy_runtime_source_not_frozen',self.study.assess()['evidence_errors'])

    def test_host_platform_cannot_be_relabelled(self):
        self.study.spec['partitions'][0]['platform']='linux';self.study.bind_spec()
        self.assertIn('changed_registered_host_platform',self.study.assess()['evidence_errors'])


if __name__ == '__main__':
    unittest.main()
