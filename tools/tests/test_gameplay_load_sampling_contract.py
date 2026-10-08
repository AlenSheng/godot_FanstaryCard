"""Adversarial offline capacity evidence; fixtures do not claim live capacity."""
import contextlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.gameplay_load_validation import aggregate_window, new_events
from tools.pr13_runtime_evidence import coverage, result_dimensions, sampling_integrity

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gameplay_load_test as coordinator


class SamplingContractTests(unittest.TestCase):
    def rows(self):
        return [dict(at=1000 + t, sample_monotonic_ms=t * 1000,
                     online=10, active_in_room=10, command_rate=2)
                for t in range(0, 601, 10)]

    def measure(self, rows, **changes):
        contract = dict(start=1000, end=1600, target_online=10, target_active=10)
        contract.update(changes)
        return coverage(rows, **contract)

    def capacity(self, measured, sampled):
        return result_dimensions(execution=True, evidence=sampled['passed'],
                                 load=measured['passed'], gameplay=None,
                                 performance=True, cleanup=True,
                                 applicable=['execution', 'evidence', 'load',
                                             'performance', 'cleanup'])

    def test_distinct_observations_at_maximum_gap_remain_usable(self):
        rows = self.rows()[::2]
        self.assertTrue(self.measure(rows)['passed'])
        self.assertTrue(sampling_integrity(rows, 0, 600000)['passed'])

    def test_conflicting_overlap_cannot_hide_a_load_drop(self):
        rows = self.rows()
        rows[31:31] = [dict(rows[30], online=0, active_in_room=0), dict(rows[30])]
        measured = self.measure(rows)
        sampled = sampling_integrity(rows, 0, 600000)
        self.assertFalse(measured['passed'])
        self.assertFalse(sampled['passed'])
        self.assertFalse(self.capacity(measured, sampled)['all_applicable_passed'])

    def test_identical_replayed_sample_does_not_count_as_a_new_observation(self):
        rows = self.rows()
        rows.insert(30, dict(rows[30]))
        self.assertFalse(self.measure(rows)['passed'])
        self.assertFalse(sampling_integrity(rows, 0, 600000)['passed'])

    def test_reordered_rows_are_not_sorted_into_success(self):
        rows = self.rows()
        rows[20], rows[21] = rows[21], rows[20]
        self.assertFalse(self.measure(rows)['passed'])
        self.assertFalse(sampling_integrity(rows, 0, 600000)['passed'])

    def test_unknown_time_is_not_removed_to_bridge_adjacent_observations(self):
        for bad in (None, True, -1, math.nan, math.inf):
            with self.subTest(bad=bad):
                rows = self.rows()
                rows[30]['at'] = bad
                result = self.measure(rows)
                self.assertFalse(result['passed'])
                self.assertEqual(result['compliant_seconds'], 0)
                self.assertFalse(sampling_integrity(rows, 0, 600000)['passed'])

    def test_negative_elapsed_clock_cannot_prove_capacity(self):
        rows = self.rows()
        for row in rows:
            row['sample_monotonic_ms'] -= 600000
        self.assertFalse(sampling_integrity(rows, -600000, 0)['passed'])
        self.assertFalse(sampling_integrity(rows, 0, 600000)['passed'])
        with self.assertRaises(ValueError):
            self.measure(rows, start=-600, end=0)

    def test_stop_tail_and_first_observation_blackouts_are_rejected(self):
        for rows in (self.rows()[:-3], self.rows()[3:]):
            sampled = sampling_integrity(rows, 0, 600000)
            self.assertFalse(sampled['passed'])
            self.assertIn('sampling_gap_over_contract', sampled['reasons'])

    def test_missing_tick_breaks_continuous_hold_at_same_coverage(self):
        rows = [r for r in self.rows() if r['at'] != 1300 and r['at'] != 1310]
        result = self.measure(rows, minimum_continuous=600)
        self.assertEqual(result['coverage'], .95)
        self.assertEqual(result['longest_continuous_seconds'], 290)
        self.assertFalse(result['passed'])

    def test_unobserved_stop_tail_stays_in_coverage_denominator(self):
        result = self.measure(self.rows()[:-4])
        self.assertEqual(result['window_seconds'], 600)
        self.assertEqual(result['compliant_seconds'], 560)
        self.assertFalse(result['passed'])

    def test_online_and_active_in_separate_windows_do_not_meet_joint_target(self):
        rows = self.rows()
        for row in rows:
            row['online' if row['at'] < 1300 else 'active_in_room'] = 5
        result = self.measure(rows)
        self.assertEqual(result['coverage'], 0)
        self.assertFalse(result['passed'])

    def test_monitoring_unknown_is_not_capacity_success_even_with_full_load(self):
        result = result_dimensions(execution=True, evidence=False, load=True,
                                   gameplay=None, performance=None, cleanup=True,
                                   applicable=['execution', 'evidence', 'load',
                                               'performance', 'cleanup'])
        self.assertEqual(result['dimensions']['performance'], 'Unknown')
        self.assertFalse(result['all_applicable_passed'])


class RequestAccountingContractTests(unittest.TestCase):
    def event(self, seq, **changes):
        row = dict(type='http', event_seq=seq, run_id='r', client_id='a',
                   process_epoch='e', at_unix_ms=1000, status=200, ok=True,
                   duration_ms=1)
        row.update(changes)
        return row

    def test_retry_cancel_and_invalid_latency_preserve_separate_denominators(self):
        terminal = [self.event(1), self.event(2, status=0, ok=False, result='cancelled'),
                    self.event(3, status=500, ok=False, duration_ms=math.nan)]
        attempts = [self.event(4, type='http_attempt', status=503, ok=False, result='http_error'),
                    self.event(5, type='http_attempt', result='success')]
        result = aggregate_window([dict(operations=terminal, telemetry=terminal + attempts)])
        self.assertEqual((result['logical_request_count'], result['cancelled_count'],
                          result['sample_count'], result['all_attempt_count']), (3, 1, 2, 2))
        self.assertEqual(result['error_rate'], .5)
        self.assertEqual(result['valid_latency_count'], 1)
        self.assertGreater(result['invalid_metric_count'], 0)

    def test_duplicate_event_sequences_are_evidence_loss_and_never_two_requests(self):
        event = self.event(1)
        status = dict(run_id='r', client_id='a', process_epoch='e', event_seq_max=1,
                      telemetry=[event, dict(event)], operations=[event, dict(event)])
        rows, lost = new_events([status], {})
        self.assertGreater(lost, 0)
        self.assertEqual(aggregate_window(rows)['sample_count'], 1)


class CoordinatorSamplingContractTests(unittest.TestCase):
    def run_fixture(self, *, overlap, local_resources=False, missing_actor=False):
        """Run the real final verdict with fake child/clock/network observations."""
        elapsed = [0.0]
        child = SimpleNamespace(pid=4242, returncode=None)
        child.poll = lambda: child.returncode
        clock = SimpleNamespace(
            time=lambda: 100000 + elapsed[0] - (1 if overlap and elapsed[0] >= 300 else 0),
            monotonic=lambda: elapsed[0],
            monotonic_ns=lambda: int(elapsed[0] * 1e9),
            sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
            strftime=time.strftime)
        events = []
        heartbeat = [0]

        def launch(*args, env, **kwargs):
            return child

        def read_status(processes, cache=None, now_monotonic_ms=None, *, require_files=False):
            if overlap and elapsed[0] == 290:
                elapsed[0] += 9
            entry = processes[0]
            heartbeat[0] += 1
            if not require_files:
                types = ['realtime'] * 20 + (['http'] * 20 if not events else [])
                for kind in types:
                    events.append(dict(type=kind, event_type=kind,
                        event_seq=len(events) + 1, at_unix_ms=int(clock.time() * 1000),
                        run_id=entry['run_id'], client_id=entry['client_id'],
                        process_epoch=entry['process_epoch'], cycle_id='fixture:1',
                        match_id='fixture-match', duration_ms=1, status=200, ok=True))
            ring = events[-300:]
            status = dict(run_id=entry['run_id'], client_id=entry['client_id'],
                process_epoch=entry['process_epoch'], pid=child.pid,
                status_seq=heartbeat[0], now_unix_ms=int(clock.time() * 1000),
                _received_at_monotonic_ms=clock.monotonic() * 1000,
                online=True, room=True, last_progress_age_ms=0, cycles_completed=0,
                event_seq_max=len(events), telemetry=ring,
                operations=[e for e in ring if e['type'] == 'http'],
                audit_lost_count=0, errors=[], cleanup={'state': 'Passed'})
            Path(str(entry['report']) + '.telemetry.jsonl').write_text(
                ''.join(json.dumps(e) + '\n' for e in events), encoding='utf8')
            return [status], 0

        def stop(processes, stop_file):
            stop_file.touch()
            child.returncode = 0
            return []

        with tempfile.TemporaryDirectory() as directory:
            argv = ['gameplay_load_test.py', '--run', '--godot', sys.executable,
                '--max-groups', '1', '--group-size', '1', '--max-seconds', '630',
                '--hold-seconds', '600', '--output', directory]
            if local_resources: argv.append('--local-resource-sampling')
            with patch.object(sys, 'argv', argv), patch.object(coordinator, 'time', clock), \
                    patch.object(coordinator, 'subprocess', SimpleNamespace(
                        Popen=launch, STDOUT=subprocess.STDOUT,
                        SubprocessError=subprocess.SubprocessError)), \
                    patch.object(coordinator, 'provenance', return_value={'offline_fixture': True}), \
                    patch.object(coordinator, 'health_probe', return_value={
                        'ok': True, 'duration_ms': 1, 'status': 200}), \
                    patch.object(coordinator, 'metrics', return_value={
                        'cpu': 1, 'memory_available': 90, 'disk_available': 90, 'actor_wait': None if missing_actor else 1}), \
                    patch.object(coordinator, 'local_host_metrics', return_value={
                        'cpu': 1, 'memory_available': 90, 'disk_available': 90, 'actor_wait': None, 'server_humans_in_room': None}), \
                    patch.object(coordinator, 'generator_resources', return_value=({}, None)), \
                    patch.object(coordinator, 'read_owned_statuses', side_effect=read_status), \
                    patch.object(coordinator, 'stop_all', side_effect=stop), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = coordinator.main()
            reports = list(Path(directory).glob('*/report.json'))
            self.assertEqual(len(reports), 1)
            return code, json.loads(reports[0].read_text())

    def test_wall_overlap_is_invalid_in_actual_coordinator_verdict(self):
        code, report = self.run_fixture(overlap=True)
        self.assertEqual(code, 3)
        self.assertEqual(report['result_dimensions']['dimensions']['evidence'], 'Failed')
        self.assertEqual(report['result_dimensions']['dimensions']['load'], 'Failed')
        self.assertFalse(report['acceptance_passed'])
        self.assertIn('load_coverage_evidence_invalid', report['final_triggers'])
        pair = [s for s in report['samples'] if s['sample_monotonic_ms'] in (299000, 300000)]
        self.assertEqual(len(pair), 2)
        self.assertEqual(pair[0]['at'], pair[1]['at'])
        self.assertLess(pair[0]['sample_monotonic_ms'], pair[1]['sample_monotonic_ms'])

    def test_legal_complete_window_keeps_capacity_scope_and_exit_zero(self):
        code, report = self.run_fixture(overlap=False)
        self.assertEqual(code, 0)
        self.assertTrue(report['acceptance_passed'])
        self.assertTrue(report['sampling_integrity']['passed'])
        self.assertEqual(report['load_coverage']['window_seconds'], 600)
        self.assertEqual(report['load_coverage']['minimum_coverage'], .95)
        self.assertEqual(report['load_coverage']['evidence_errors'], [])
        self.assertEqual(report['result_dimensions']['dimensions']['load'], 'Passed')
        self.assertEqual(report['result_dimensions']['dimensions']['evidence'], 'Passed')
        self.assertEqual(report['result_dimensions']['dimensions']['gameplay'], 'NotApplicable')
        for sample in report['samples'][1:]:
            self.assertGreater(sample['window']['observed_window_seconds'], 0)
            self.assertIsNotNone(sample['window']['logical_requests_per_second'])

    def test_local_host_diagnostics_never_prove_server_performance(self):
        code, report = self.run_fixture(overlap=False, local_resources=True)
        self.assertEqual(code, 1)
        self.assertEqual(report['result_dimensions']['dimensions']['load'], 'Passed')
        self.assertEqual(report['result_dimensions']['dimensions']['performance'], 'Unknown')
        self.assertEqual(report['performance_inputs']['actor_wait_samples'], 0)
        self.assertIsNone(report['samples'][0]['server_confirmed_in_room'])

    def test_missing_actor_wait_is_not_a_zero_latency_success(self):
        code, report = self.run_fixture(overlap=False, missing_actor=True)
        self.assertEqual(code, 1)
        self.assertEqual(report['result_dimensions']['dimensions']['performance'], 'Unknown')


if __name__ == '__main__':
    unittest.main()
