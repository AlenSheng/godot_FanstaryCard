"""Clock/count/budget counterexamples; synthetic data never proves live capacity."""
import copy
import unittest

from tools.pr13_distributed_load import (AGGREGATE_LATENCY_PROFILE,
    GLOBAL50_AGGREGATE_PROFILE, _latency_alert_budget, joint_overlap)
from tools.tests.test_pr13_distributed_load import BASE, cohort


class AggregateFiftyOverlapTests(unittest.TestCase):
    def setUp(self):
        self.hosts=[cohort('windows',count=40),cohort('cloud',count=20,skew=5)]
        for host in self.hosts:host['target_active']=30 if host['host_id']=='windows' else 10
        self.spec=dict(target_clients=50,target_online_clients=50,native_supply_clients=60,
            workload_profile=GLOBAL50_AGGREGATE_PROFILE,latency_profile=AGGREGATE_LATENCY_PROFILE,
            latency_warning_budget_fraction=.05,reference_host_id='windows',
            window_start_ms=(BASE+60)*1000,window_end_ms=(BASE+660)*1000)

    def result(self):return joint_overlap(self.hosts,self.spec)

    def counts(self,windows,cloud):
        for h,count in zip(self.hosts,(windows,cloud)):
            for row in h['samples']:row.update(online=count,active_in_room=count)

    def test_actual50_not_all60_online_is_the_registered_target(self):
        self.counts(30,20);original=copy.deepcopy(self.hosts);r=self.result()
        self.assertTrue(r['joint_overlap_passed'],r);self.assertFalse(r['capacity_acceptance'])
        self.assertEqual((50,60),(r['target_online_clients'],r['native_supply_clients']))
        self.assertEqual(original,self.hosts)

    def test_local_floor40_and_global49_cannot_borrow_gauge(self):
        for w,c in [(30,10),(30,19)]:
            self.counts(w,c)
            with self.subTest(w=w,c=c):self.assertFalse(self.result()['joint_overlap_passed'])

    def test_changing_real_distribution_can_keep_global50(self):
        for i in range(len(self.hosts[0]['samples'])):
            for h,count in zip(self.hosts,(40 if i<35 else 30,10 if i<35 else 20)):
                h['samples'][i].update(online=count,active_in_room=count)
        self.assertTrue(self.result()['joint_overlap_passed'])

    def test_nonoverlapping_peaks_never_sum_to50(self):
        for i in range(len(self.hosts[0]['samples'])):
            for h,count in zip(self.hosts,(40 if i<35 else 30,9 if i<35 else 19)):
                h['samples'][i].update(online=count,active_in_room=count)
        self.assertFalse(self.result()['joint_overlap_passed'])

    def test_two_isolated_latency_windows_have_a_bound_not_a_blanket_waiver(self):
        for i in (20,40):self.hosts[0]['samples'][i]['reasons']=['command_p95_over_8000ms']
        original=copy.deepcopy(self.hosts);r=self.result()
        self.assertTrue(r['joint_overlap_passed'],r)
        self.assertLess(r['latency_warning_reviews']['windows']['fraction'],.05)
        self.assertEqual(original,self.hosts)

    def test_three_consecutive_alerts_fail_even_if_clock_time_is_small(self):
        for i in (20,21,22):self.hosts[0]['samples'][i]['reasons']=['command_p95_over_8000ms']
        r=self.result();self.assertFalse(r['joint_overlap_passed'])
        self.assertIn('three_consecutive_latency_alert_windows',r['evidence_errors'])

    def test_four_separated_latency_windows_exceed5percent(self):
        for i in (20,30,40,50):self.hosts[0]['samples'][i]['reasons']=['http_p95_over_5000ms']
        r=self.result();self.assertFalse(r['joint_overlap_passed'])
        self.assertIn('latency_alert_time_exceeds5percent',r['evidence_errors'])

    def test_disjoint_host_warnings_share_one_global5percent_budget(self):
        for i in (20,40):self.hosts[0]['samples'][i]['reasons']=['command_p95_over_8000ms']
        for i in (30,50):self.hosts[1]['samples'][i]['reasons']=['http_p95_over_5000ms']
        r=self.result();self.assertFalse(r['joint_overlap_passed'])
        self.assertIn('joint_latency_alert_time_exceeds5percent',r['evidence_errors'])

    def test_simultaneous_host_alerts_are_unioned_not_double_counted(self):
        for host in self.hosts:
            for i in (20,40):host['samples'][i]['reasons']=['command_p95_over_8000ms']
        r=self.result();self.assertTrue(r['joint_overlap_passed'],r)
        self.assertLess(r['joint_latency_warning_fraction'],.05)

    def test_resource_health_and_unknown_alerts_are_never_budgeted(self):
        for reason in ('generator_memory_redline','health_over_10000ms','unknown','command_rejections_10pct'):
            self.hosts[0]['samples'][20]['reasons']=[reason]
            with self.subTest(reason=reason):
                r=self.result();self.assertFalse(r['joint_overlap_passed'])
                self.assertIn('non_latency_alert_in_shared_window',r['evidence_errors'])

    def test_exact_budget_and_expanded_clock_boundary(self):
        rows=self.hosts[0]['samples']
        for i in (20,40,60):rows[i]['reasons']=['command_p95_over_8000ms']
        env=dict(lower_ms=0,upper_ms=0)
        r=_latency_alert_budget(rows,env,self.spec['window_start_ms'],self.spec['window_end_ms'],20)
        self.assertAlmostEqual(.05,r['fraction'])
        with self.assertRaisesRegex(ValueError,'exceeds5percent'):
            _latency_alert_budget(rows,dict(lower_ms=0,upper_ms=1),self.spec['window_start_ms'],self.spec['window_end_ms'],20)

    def test_unbounded_first_alert_interval_is_not_zero_time(self):
        rows=self.hosts[0]['samples'];rows[0]['reasons']=['command_p95_over_8000ms']
        with self.assertRaisesRegex(ValueError,'unbounded'):
            _latency_alert_budget(rows,dict(lower_ms=0,upper_ms=0),BASE*1000,(BASE+600)*1000,20)

    def test_59_supply_and_changed_partition_are_not_registered(self):
        self.spec['native_supply_clients']=59;self.assertFalse(self.result()['joint_overlap_passed'])
        self.spec['native_supply_clients']=60;self.hosts[0]['clients']=39
        self.assertFalse(self.result()['joint_overlap_passed'])

    def test_every_supplied_native_still_requires_fresh_alive_status(self):
        for mode in ('fresh_status_clients','alive_processes'):
            original=copy.deepcopy(self.hosts)
            for row in self.hosts[0]['samples']:row[mode]=39
            with self.subTest(mode=mode):self.assertFalse(self.result()['joint_overlap_passed'])
            self.hosts=original

    def test_active_count_cannot_exceed_actual_online(self):
        for row in self.hosts[0]['samples']:row['online']=30;row['active_in_room']=40
        self.assertFalse(self.result()['joint_overlap_passed'])

    def test_missing_clock_unknown_profile_or_larger_budget_fails(self):
        self.spec['latency_warning_budget_fraction']=.06;self.assertFalse(self.result()['joint_overlap_passed'])
        self.spec['latency_warning_budget_fraction']=.05
        self.spec['workload_profile']='almost-aggregate';self.assertFalse(self.result()['joint_overlap_passed'])
        self.spec['workload_profile']=GLOBAL50_AGGREGATE_PROFILE
        self.hosts[0]['clock_probes']=[];self.assertFalse(self.result()['joint_overlap_passed'])

    def test_new_budget_cannot_be_injected_into_old_profile(self):
        self.spec['workload_profile']='full-native60-global50-win35-cloud25'
        self.assertFalse(self.result()['joint_overlap_passed'])

    def test_global_server49_does_not_fill50_native_proof(self):
        for host in self.hosts:
            for row in host['samples']:row['server_confirmed_in_room']=49
        self.assertFalse(self.result()['joint_overlap_passed'])

    def test_component_never_claims_pooled_latency_or_whole_acceptance(self):
        r=self.result();self.assertTrue(r['joint_overlap_passed'])
        self.assertFalse(r['capacity_acceptance'])
        self.assertTrue(r['latency_warning_reviews']['cloud']['pooled_raw_latency_check_still_required'])


if __name__=='__main__':unittest.main()
