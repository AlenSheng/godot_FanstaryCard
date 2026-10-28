"""Counterexamples to summing independently successful smaller load runs."""
import copy
import unittest

from tools.pr13_distributed_load import joint_overlap


BASE = 1_000_000.0


def sample(second, *, count=25, skew=0, mono_origin=1_000_000):
    return dict(at=BASE + second + skew, sample_monotonic_ms=mono_origin + second * 1000,
                online=count, active_in_room=count, alive_processes=count,
                fresh_status_clients=count, server_confirmed_in_room=50,
                command_rate=2, workload_failure=False, reasons=[],
                failed_processes=[], stale_clients=[], stalled_clients=[],
                missing_clients=[], invalid_clients=[])


def probe(host, second, phase, *, skew=0, mono_origin=1_000_000, rtt=20):
    wall = (BASE + second) * 1000
    return dict(host_id=host, phase=phase,
                reference_sent_unix_ms=wall - rtt / 2,
                reference_received_unix_ms=wall + rtt / 2,
                reference_sent_monotonic_ms=2_000_000 + second * 1000 - rtt / 2,
                reference_received_monotonic_ms=2_000_000 + second * 1000 + rtt / 2,
                remote_unix_ms=wall + skew * 1000,
                remote_monotonic_ms=mono_origin + second * 1000)


def cohort(host, *, skew=0, start=0, count=25):
    origin = 2_000_000 if host == 'windows' else 1_000_000
    return dict(host_id=host, clients=count,
                samples=[sample(s, count=count, skew=skew, mono_origin=origin)
                         for s in range(start, start + 721, 10)],
                clock_probes=[probe(host, -10, 'before', skew=skew, mono_origin=origin),
                              probe(host, max(730, start + 730), 'after', skew=skew, mono_origin=origin)])


class DistributedOverlapTests(unittest.TestCase):
    def setUp(self):
        self.cohorts = [cohort('windows'), cohort('cloud', skew=5)]
        self.contract = dict(target_clients=50, reference_host_id='windows', window_start_ms=(BASE + 60) * 1000,
                             window_end_ms=(BASE + 660) * 1000)

    def check_result(self):
        return joint_overlap(self.cohorts, self.contract)

    def assertRejected(self):
        self.assertFalse(self.check_result()['joint_overlap_passed'])

    def test_clock_corrected_full50_overlap_is_only_component_evidence(self):
        result = self.check_result()
        self.assertTrue(result['joint_overlap_passed'], result)
        self.assertEqual(600, result['compliant_seconds'])
        self.assertFalse(result['capacity_acceptance'])

    def test_separate_good720second_runs_cannot_be_added(self):
        self.cohorts[1] = cohort('cloud', skew=5, start=900)
        result = self.check_result()
        self.assertFalse(result['joint_overlap_passed'])
        self.assertEqual(0, result['compliant_seconds'])

    def test_partial_overlap_is_not_full_window(self):
        self.cohorts[1] = cohort('cloud', skew=5, start=600)
        self.assertRejected()

    def test_exactly600_local_seconds_do_not_hide_clock_uncertainty(self):
        for c in self.cohorts:
            c['samples'] = c['samples'][6:67]
        result = self.check_result()
        self.assertLess(result['longest_continuous_seconds'], 600)
        # Original95percent/120second coverage still applies, rather than
        # inventing an unconditional600continuous requirement.
        self.assertTrue(result['joint_overlap_passed'])

    def test_each_generator_seeing_only25_server_humans_fails(self):
        for c in self.cohorts:
            for row in c['samples']:
                row['server_confirmed_in_room'] = 25
        self.assertRejected()

    def test_missing_server_gauge_is_not_successful_zero(self):
        for row in self.cohorts[0]['samples']:
            row.pop('server_confirmed_in_room')
        self.assertRejected()

    def test_foreign_humans_cannot_fill_target_count(self):
        for row in self.cohorts[1]['samples']:
            row['server_confirmed_in_room'] = 51
        self.assertRejected()

    def test_partition_must_equal50(self):
        self.cohorts[1]['clients'] = 24
        self.assertRejected()

    def test_duplicate_host_identity_rejected(self):
        self.cohorts[1]['host_id'] = 'windows'
        self.assertRejected()

    def test_boolean_client_count_rejected(self):
        self.cohorts[0]['clients'] = True
        self.assertRejected()

    def test_boolean_online_not_treated_as_integer(self):
        self.cohorts[0]['samples'][12]['online'] = True
        self.assertRejected()

    def test_larger_unowned_online_count_does_not_certify_partition(self):
        for row in self.cohorts[0]['samples']:
            row['online'] = 100
        self.assertRejected()

    def test_reordered_observation_cannot_be_sorted_into_a_pass(self):
        rows = self.cohorts[1]['samples']
        rows[20], rows[21] = rows[21], rows[20]
        self.assertRejected()

    def test_duplicate_timestamp_rejected(self):
        self.cohorts[0]['samples'].insert(10, copy.deepcopy(self.cohorts[0]['samples'][10]))
        self.assertRejected()

    def test_nonfinite_timestamp_rejected(self):
        self.cohorts[0]['samples'][5]['at'] = float('nan')
        self.assertRejected()

    def test_missing_monotonic_sample_rejected(self):
        self.cohorts[0]['samples'][5].pop('sample_monotonic_ms')
        self.assertRejected()

    def test_unobserved_large_gap_not_bridged(self):
        self.cohorts[1]['samples'] = self.cohorts[1]['samples'][:20] + self.cohorts[1]['samples'][30:]
        self.assertRejected()

    def test_bad_middle_observations_do_not_disappear_in_merged_run(self):
        for row in self.cohorts[1]['samples'][20:25]:
            row['server_confirmed_in_room'] = 49
        self.assertRejected()

    def test_zero_command_activity_does_not_certify_a_hold(self):
        for row in self.cohorts[0]['samples']:
            row['command_rate'] = 0
        self.assertRejected()

    def test_missing_after_probe_rejected(self):
        self.cohorts[1]['clock_probes'].pop()
        self.assertRejected()

    def test_clock_probe_with_wrong_host_rejected(self):
        self.cohorts[1]['clock_probes'][0]['host_id'] = 'third-host'
        self.assertRejected()

    def test_clock_probes_must_bracket_evaluation_window(self):
        self.cohorts[1]['clock_probes'][1] = probe('cloud', 650, 'after', skew=5)
        self.assertRejected()

    def test_clock_jump_after_workload_not_repaired_by_average_offset(self):
        self.cohorts[1]['clock_probes'][1]['remote_unix_ms'] += 10000
        self.assertRejected()

    def test_round_trip_too_wide_rejected(self):
        self.cohorts[1]['clock_probes'][0] = probe('cloud', -10, 'before', skew=5, rtt=2000)
        self.assertRejected()

    def test_bounded_slow_transport_preserves_uncertainty_instead_of_exact_offset(self):
        self.cohorts[1]['clock_probes'][0] = probe('cloud', -10, 'before', skew=5, rtt=1400)
        result = self.check_result()
        self.assertTrue(result['joint_overlap_passed'], result)
        clock = result['hosts'][1]['clock']
        self.assertEqual(1400, clock['maximum_round_trip_ms'])
        self.assertEqual(2400, clock['upper_ms'] - clock['lower_ms'])
        self.assertFalse(result['capacity_acceptance'])

    def test_any_probe_exceeding1500ms_is_retained_as_failure(self):
        self.cohorts[1]['clock_probes'][0] = probe('cloud', -10, 'before', skew=5, rtt=1501)
        self.assertRejected()

    def test_both_clock_drifts_are_included_in_relative_bound(self):
        self.cohorts[0]['samples'][30]['at'] += .2
        self.cohorts[1]['samples'][30]['at'] -= .2
        result = self.check_result()
        self.assertTrue(result['joint_overlap_passed'], result)
        clock = result['hosts'][1]['clock']
        self.assertLessEqual(clock['lower_ms'], -5400)
        self.assertGreaterEqual(clock['upper_ms'], -4600)

    def test_opposite_clock_deviations_cannot_hide_behind_first_anchor(self):
        self.cohorts[1]['samples'][30]['at'] += .2
        self.cohorts[1]['samples'][31]['at'] -= .2
        self.assertRejected()

    def test_drifting_before_after_probes_use_union_not_intersection(self):
        self.cohorts[1]['clock_probes'][1]['remote_unix_ms'] += 200
        result = self.check_result()
        self.assertTrue(result['joint_overlap_passed'], result)
        clock = result['hosts'][1]['clock']
        self.assertLessEqual(clock['lower_ms'], -5200)
        self.assertGreaterEqual(clock['upper_ms'], -5000)

    def test_reference_host_cannot_use_different_monotonic_origin(self):
        for row in self.cohorts[0]['samples']:
            row['sample_monotonic_ms'] += 100000
        for p in self.cohorts[0]['clock_probes']:
            p['remote_monotonic_ms'] += 100000
        self.assertRejected()

    def test_negative_round_trip_rejected(self):
        p = self.cohorts[1]['clock_probes'][0]
        p['reference_received_monotonic_ms'] = p['reference_sent_monotonic_ms'] - 1
        self.assertRejected()

    def test_reference_clock_shift_between_generator_calibrations_rejected(self):
        for p in self.cohorts[1]['clock_probes']:
            p['reference_sent_unix_ms'] += 1000
            p['reference_received_unix_ms'] += 1000
        self.assertRejected()

    def test_weaker_coverage_contract_rejected(self):
        self.contract['minimum_coverage'] = .9
        self.assertRejected()

    def test_shorter_window_not_accepted(self):
        self.contract['window_end_ms'] = self.contract['window_start_ms'] + 599000
        self.assertRejected()

    def test_empty_or_malformed_input_has_no_capacity_success(self):
        for cohorts, contract in [(None, self.contract), (self.cohorts, None), ([], {}), ([{}], self.contract)]:
            with self.subTest(cohorts=type(cohorts).__name__):
                result = joint_overlap(cohorts, contract)
                self.assertFalse(result['joint_overlap_passed'])
                self.assertFalse(result['capacity_acceptance'])


if __name__ == '__main__':
    unittest.main()
