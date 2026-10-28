"""Whole sealed-input verifier controls; all clients and archives are synthetic."""
import tempfile
import unittest
from pathlib import Path

from tools.pr13_authority_transitions import AUTHORITY_TRANSITION_POLICY, POLICY_SOURCE_FILES
from tools.pr13_distributed_capacity import AGGREGATE_INITIAL_MEMORY
from tools.tests.test_pr13_distributed_capacity import SyntheticStudy


class AggregateCapacityV2Tests(unittest.TestCase):
    def setUp(self):
        parent=Path(tempfile.gettempdir()).resolve()
        self.temp=tempfile.TemporaryDirectory(prefix='pr13-aggregate-v2-')
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(parent))
        self.addCleanup(self.temp.cleanup)
        self.study=SyntheticStudy(self.temp.name,aggregate=True)

    def reject(self):
        result=self.study.assess();self.assertFalse(result['capacity_accepted'],result)
        return result

    def counts(self,windows,cloud):
        for host,count in [('windows',windows),('cloud',cloud)]:
            r=self.study.report(host)
            for row in r['samples']:
                if row['active_in_room']:row.update(online=count,active_in_room=count)
            self.study.put_report(host,r)

    def test_complete_fixture_proves_only_revised_capacity_scope(self):
        self.counts(30,20);r=self.study.assess()
        self.assertTrue(r['capacity_accepted'],r)
        self.assertEqual((60,50),(r['participants'],r['target_active']))
        self.assertTrue(r['conditional_revised_capacity_scope'])
        self.assertFalse(r['original_strict_profile_accepted'])
        self.assertFalse(r['default_latency_capacity_accepted'])
        self.assertFalse(r['whole_project_accepted'])

    def test_49_actual_native_is_not_repaired_by_full_server_gauge(self):
        self.counts(30,19)
        self.assertIn('shared_full50_window_not_verified',self.reject()['evidence_errors'])

    def test_remaining47_world_cap_cannot_reset(self):
        self.study.spec['world_budget']=48;self.study.bind_spec()
        self.assertIn('cumulative_capacity_budget_reset_or_exceeded',self.reject()['evidence_errors'])

    def test_prior_worlds_or_combined_cap_cannot_be_relabeled(self):
        self.study.spec['prior_capacity_worlds']=0;self.study.bind_spec();self.reject()
        self.study.spec['prior_capacity_worlds']=253
        self.study.spec['combined_capacity_world_cap']=301;self.study.bind_spec();self.reject()

    def test_later_attempt_must_use_its_smaller_remaining_budget(self):
        self.study.spec.update(prior_capacity_worlds=284,world_budget=17)
        self.study.bind_spec();self.reject()
        self.study.spec['world_budget']=16;self.study.bind_spec()
        self.assertTrue(self.study.assess()['capacity_accepted'])

    def test_full_queue_starting_memory_is_independent_of_reserve_floor(self):
        host='windows';r=self.study.get(host,'supervisor.json')
        r['resources'][0]['memory_available_bytes']=AGGREGATE_INITIAL_MEMORY[host]-1
        self.study.put(host,'supervisor.json',r)
        self.assertIn('whole_native_queue_memory_not_admitted',self.reject()['evidence_errors'])

    def test_cloud20_full_queue_budget_is_not_just500MB(self):
        host='cloud';r=self.study.get(host,'supervisor.json')
        r['resources'][0]['memory_available_bytes']=AGGREGATE_INITIAL_MEMORY[host]-1
        self.study.put(host,'supervisor.json',r)
        self.assertIn('whole_native_queue_memory_not_admitted',self.reject()['evidence_errors'])

    def test_midrun_memory_and_both_cloud_disk_floors_remain_strict(self):
        for host,field,value in [('windows','memory_available_bytes',6442450943),
                                 ('cloud','root_disk_free_bytes',2999999999),
                                 ('cloud','root_disk_available_percent',4.99)]:
            original=self.study.get(host,'supervisor.json');bad=self.study.get(host,'supervisor.json')
            bad['resources'][50][field]=value;self.study.put(host,'supervisor.json',bad)
            with self.subTest(field=field):self.reject()
            self.study.put(host,'supervisor.json',original)

    def test_isolated_latency_warning_is_preserved_not_removed(self):
        r=self.study.report('windows')
        for i in (40,60):r['samples'][i]['reasons']=['command_p95_over_8000ms']
        self.study.put_report('windows',r);result=self.study.assess()
        self.assertTrue(result['capacity_accepted'],result)
        self.assertEqual(['command_p95_over_8000ms'],self.study.report('windows')['samples'][40]['reasons'])

    def test_pooled_raw_redline_is_not_excused_by_empty_sample_alerts(self):
        with tempfile.TemporaryDirectory(prefix='pr13-aggregate-pool-') as directory:
            s=SyntheticStudy(directory,aggregate=True,command_ms=8001)
            self.assertTrue(all(not row['reasons'] for row in s.report('windows')['samples']))
            # Forge only summaries; the sealed raw audit still contains8001ms.
            # This forces the independent pooled replay, rather than the
            # earlier correctly strict three-window summary guard, to decide.
            for host in ('windows','cloud'):
                report=s.report(host)
                for row in report['samples']:
                    if row['window']['realtime']['count']:
                        for key in ('min_ms','mean_ms','max_ms','p50_ms','p95_ms','p99_ms'):
                            row['window']['realtime'][key]=10
                s.put_report(host,report)
            result=s.assess();self.assertFalse(result['capacity_accepted'])
            self.assertIn('pooled_raw_latency_redline',result['evidence_errors'])

    def test_unknown_native_error_cannot_be_replaced_by_claimed_good_review(self):
        self.study.change_native('windows',0,lambda n:n.update(errors=[{'at_unix_ms':1,'message':'unrecognized'}]))
        r=self.study.report('windows');r['final_clients'][0]['errors']=[{'at_unix_ms':1,'message':'unrecognized'}]
        self.study.put_report('windows',r)
        self.assertIn('authority_transition_replay_failed',self.reject()['evidence_errors'])

    def test_default_v1_or_forged_source_policy_cannot_select_v2(self):
        self.study.spec['authority_transition_policy']=AUTHORITY_TRANSITION_POLICY;self.study.bind_spec();self.reject()
        self.study.reference['controls'][POLICY_SOURCE_FILES[0]]='0'*64
        self.assertIn('policy_runtime_source_not_frozen',self.reject()['evidence_errors'])

    def test_false_original_outcome_is_not_promoted(self):
        r=self.study.report('windows');r['outcome']['passed']=False;self.study.put_report('windows',r)
        self.assertIn('original_cohort_did_not_pass',self.reject()['evidence_errors'])

    def test_wrong_partition_or_local_online_floor_is_not_new_registration(self):
        self.study.spec['partitions'][0]['target_online']=1;self.study.bind_spec()
        self.assertIn('wrong_aggregate_host_online_floor',self.reject()['evidence_errors'])

    def test_undersupply_or_reused_physical_identity_still_fails(self):
        r=self.study.report('cloud');r['clients']=19;self.study.put_report('cloud',r)
        self.assertIn('cohort_count_mismatch',self.reject()['evidence_errors'])

    def test_uncapped_frame_requirement_is_not_a_warning_budget(self):
        r=self.study.report('windows');r['samples'][40]['generator']['native_frame_observations'][0]['engine_max_fps']=30
        self.study.put_report('windows',r)
        self.assertIn('native_FPS_override_observed',self.reject()['evidence_errors'])

    def test_declared_100_target_cannot_borrow_actual60(self):
        self.study.spec.update(target_clients=100,target_online_clients=100);self.study.bind_spec();self.reject()


if __name__=='__main__':unittest.main()
