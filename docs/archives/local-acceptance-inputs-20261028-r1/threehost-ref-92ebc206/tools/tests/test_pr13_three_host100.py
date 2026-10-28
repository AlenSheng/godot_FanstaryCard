"""Three real producers are mandatory; these are offline counterexamples only."""
import copy
import tempfile
import unittest
from pathlib import Path

from tools.tests.test_pr13_distributed_capacity import SyntheticStudy
from tools.pr13_distributed_capacity import THREE_HOST100_INITIAL_MEMORY


class ThreeHost100EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='pr13-three-host100-')
        self.study=SyntheticStudy(Path(self.temp.name),target_clients=100,three_host100=True)

    def tearDown(self):
        self.temp.cleanup()

    def reject(self):
        result=self.study.assess()
        self.assertFalse(result['capacity_accepted'],result)
        return result

    def test_three_full_native_cohorts_accept_only_new_technical_scope(self):
        result=self.study.assess()
        self.assertTrue(result['capacity_accepted'],result)
        self.assertEqual(100,result['participants'])
        self.assertEqual(600,result['overlap']['compliant_seconds'])
        self.assertEqual({'windows','sjh','cloud'},set(result['per_host_latency']))
        self.assertFalse(result['whole_project_accepted'])
        self.assertTrue(result['user_over300_rule_not_used_for_this_technical_verdict'])

    def test_missing_third_host_not_replaced_by_total100_claim(self):
        self.study.spec['partitions']=self.study.spec['partitions'][:2]
        self.study.bind_spec();self.reject()

    def test_third_host_reusing_cloud_account_rejected(self):
        other=self.study.get('cloud',self.study.native_names['cloud'][0])
        self.study.change_native('sjh',0,lambda native:native.update(user_id=other['user_id']))
        result=self.reject()
        self.assertIn('cohorts_reuse_runtime_or_user_identity',result['evidence_errors'])

    def test_sjh_linux_substitution_rejected(self):
        self.study.spec['partitions'][1]['platform']='linux'
        self.study.bind_spec();self.reject()

    def test_renamed_local_cohort_cannot_impersonate_sjh_machine(self):
        meta=self.study.get('sjh','host-capture.original.json')
        meta['machine_name']='other-windows'
        self.study.put('sjh','host-capture.original.json',meta);self.reject()

    def test_unfrozen_windows_controller_cannot_certify_extra_host(self):
        meta=self.study.get('sjh','host-capture.original.json')
        meta['controller_sha256']='f'*64
        self.study.put('sjh','host-capture.original.json',meta);self.reject()

    def test_sjh_memory_reserve_cannot_use_cloud500MB_floor(self):
        self.study.spec['partitions'][1]['memory_floor_bytes']=500000000
        self.study.bind_spec();self.reject()

    def test_all_hosts_need_full_queue_initial_admission(self):
        for host in ['windows','sjh','cloud']:
            with self.subTest(host=host):
                old=self.study.get(host,'supervisor.json');changed=copy.deepcopy(old)
                changed['resources'][0]['memory_available_bytes']=THREE_HOST100_INITIAL_MEMORY[host]-1
                self.study.put(host,'supervisor.json',changed);self.reject()
                self.study.put(host,'supervisor.json',old)

    def test_sjh_missing_original_native_final_not_hidden_by_summary(self):
        report=self.study.report('sjh');report['native_final_reports'].pop()
        self.study.put_report('sjh',report);self.reject()

    def test_new_round_does_not_inherit_over300_waiver(self):
        self.study.spec['user_final_acceptance_policy']='user-20261026-100-then50-over300'
        self.study.bind_spec();self.reject()

    def test_prior301_cannot_reset_or_expand_new100_world_budget(self):
        self.study.spec['prior_capacity_worlds']=0
        self.study.bind_spec();self.reject()

    def test_bounded_new_world_count_is_independent_of_history(self):
        self.study.after['matches']=101;self.reject()

    def test_third_host_partial_online_cannot_use_other_host_counts(self):
        report=self.study.report('sjh')
        for sample in report['samples']:
            if sample['active_in_room']:
                sample['online']=49;sample['active_in_room']=49
        self.study.put_report('sjh',report);self.reject()

    def test_server_foreign_human_cannot_fill100(self):
        report=self.study.report('sjh')
        for sample in report['samples']:
            sample['server_confirmed_in_room']=101
        self.study.put_report('sjh',report);self.reject()

    def test_cloud5percent_floor_still_required(self):
        supervisor=self.study.get('cloud','supervisor.json')
        supervisor['resources'][10]['root_disk_available_percent']=4.99
        self.study.put('cloud','supervisor.json',supervisor);self.reject()

    def test_incomplete_native_cleanup_not_user_accepted(self):
        report=self.study.report('sjh');report['forced_termination_pids']=[1001]
        self.study.put_report('sjh',report);self.reject()


if __name__=='__main__':unittest.main()
