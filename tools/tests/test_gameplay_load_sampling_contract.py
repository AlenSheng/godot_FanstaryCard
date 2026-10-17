"""Adversarial offline capacity evidence; fixtures do not claim live capacity."""
import contextlib
import concurrent.futures
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
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
    def run_fixture(self, *, overlap=False, local_resources=False, missing_actor=False, cycle_limit=240,
                    resource_changes=None, final_status_change=None, wall_jump=False, max_groups=1,
                    client_max_fps=None, generator_observation=None, probe_delay_seconds=0, delay_all_probes=False,
                    smoke=False, max_seconds=630, memory_floor=None, latency_limits=None):
        """Run the real final verdict with fake child/clock/network observations."""
        elapsed = [0.0]
        children = []
        clock = SimpleNamespace(
            time=lambda: 100000 + elapsed[0] - (1800 if wall_jump and elapsed[0] >= 30 else 1 if overlap and elapsed[0] >= 300 else 0),
            monotonic=lambda: elapsed[0],
            monotonic_ns=lambda: int(elapsed[0] * 1e9),
            sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
            strftime=time.strftime)
        client_events = {}
        heartbeat = [0]
        probe_events=[]
        wait_original=concurrent.futures.wait
        probe_finished=[]
        def probe_delay(label):
            if probe_delay_seconds and threading.current_thread().name.startswith('load-probe') and (label=='health' or delay_all_probes):
                started=time.monotonic();time.sleep(probe_delay_seconds)
                probe_events.append({'probe':label,'elapsed_seconds':time.monotonic()-started})
                probe_finished.append(label)
        def health_observation(*_args):
            probe_delay('health')
            return {'ok':True,'duration_ms':1,'status':200}
        def resource_observation(*_args):
            probe_delay('metrics')
            return {'cpu':1,'memory_available':90,'memory_available_bytes':3*1024**3,'disk_available':90,'actor_wait':None if missing_actor else 1,**(resource_changes or {})}
        def measured_wait(*args,**kwargs):
            started=time.monotonic();result=wait_original(*args,**kwargs)
            if probe_delay_seconds:elapsed[0]+=time.monotonic()-started
            return result

        def launch(*args, env, **kwargs):
            self.assertEqual(env['FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS'], str(cycle_limit))
            if client_max_fps is not None:
                self.assertIn('--max-fps', args[0])
                self.assertEqual(args[0][args[0].index('--max-fps')+1], str(client_max_fps))
            child = SimpleNamespace(pid=4242+len(children), returncode=None)
            child.poll = lambda: child.returncode
            children.append(child)
            return child

        def read_status(processes, cache=None, now_monotonic_ms=None, *, require_files=False, read_errors=None):
            if overlap and elapsed[0] == 290:
                elapsed[0] += 9
            statuses = []
            for entry in processes:
                events = client_events.setdefault(entry['client_id'], [])
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
                    process_epoch=entry['process_epoch'], pid=entry['process'].pid,
                    status_seq=heartbeat[0], now_unix_ms=int(clock.time() * 1000),
                    _received_at_monotonic_ms=clock.monotonic() * 1000,
                    online=True, room=True, last_progress_age_ms=0, cycles_completed=0,
                    event_seq_max=len(events), telemetry=ring,
                    operations=[e for e in ring if e['type'] == 'http'],
                    audit_lost_count=0, errors=[], cleanup={'state': 'Passed'})
                if require_files and final_status_change: final_status_change(status)
                if require_files:
                    entry['report'].write_text(json.dumps(dict(status, ok=True, outcome='completed')), encoding='utf8')
                Path(str(entry['report']) + '.telemetry.jsonl').write_text(
                    ''.join(json.dumps(e) + '\n' for e in events), encoding='utf8')
                statuses.append(status)
            return statuses, 0

        def stop(processes, stop_file):
            stop_file.touch()
            for entry in processes: entry['process'].returncode = 0
            return []

        with tempfile.TemporaryDirectory() as directory:
            argv = ['gameplay_load_test.py', '--smoke' if smoke else '--run', '--godot', sys.executable,
                '--max-groups', str(max_groups), '--group-size', '1', '--max-seconds', str(max_seconds),
                '--hold-seconds', '600', '--cycle-limit-seconds', str(cycle_limit), '--output', directory]
            if local_resources: argv.append('--local-resource-sampling')
            if client_max_fps is not None: argv+=['--client-max-fps',str(client_max_fps)]
            if memory_floor is not None:
                argv+=['--minimum-generator-memory-bytes',str(memory_floor),'--minimum-cloud-memory-bytes',str(memory_floor)]
            if latency_limits is not None:
                for flag,value in zip(['--http-p95-limit-ms','--command-p95-limit-ms','--health-limit-ms','--monitor-timeout-seconds'],latency_limits):
                    argv += [flag,str(value)]
            with patch.object(sys, 'argv', argv), patch.object(coordinator, 'time', clock), \
                    patch.object(coordinator, 'psutil', SimpleNamespace(virtual_memory=lambda: SimpleNamespace(available=3*1024**3))), \
                    patch.object(coordinator, 'subprocess', SimpleNamespace(
                        Popen=launch, STDOUT=subprocess.STDOUT,
                        SubprocessError=subprocess.SubprocessError)), \
                    patch.object(coordinator, 'provenance', return_value={'offline_fixture': True}), \
                    patch.object(coordinator, 'health_probe', side_effect=health_observation), \
                    patch.object(coordinator, 'metrics', side_effect=resource_observation), \
                    patch.object(coordinator.concurrent.futures,'wait',side_effect=measured_wait), \
                    patch.object(coordinator, 'local_host_metrics', return_value={
                        'cpu': 1, 'memory_available': 90, 'disk_available': 90, 'actor_wait': None, 'server_humans_in_room': None}), \
                    patch.object(coordinator, 'generator_resources', return_value=(generator_observation if generator_observation is not None else {'available':True,'host_memory_available_bytes':3*1024**3}, None)), \
                    patch.object(coordinator, 'read_owned_statuses', side_effect=read_status), \
                    patch.object(coordinator, 'stop_all', side_effect=stop), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = coordinator.main()
            reports = list(Path(directory).glob('*/report.json'))
            self.assertEqual(len(reports), 1)
            result=json.loads(reports[0].read_text())
            if probe_delay_seconds:
                # The coordinator has returned at its six-second budget. Join
                # the explicitly delayed fixture operations before discarding
                # their temp directory; no orphaned worker survives this case.
                deadline=time.monotonic()+probe_delay_seconds+2
                while len(probe_finished)<(2 if delay_all_probes else 1) and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(len(probe_finished),2 if delay_all_probes else 1)
                result['actual_delayed_fixture_workers']=probe_events
            return code, result

    def test_smoke_uses_registered_1800_second_budget_without_1260_second_cutoff(self):
        code, report = self.run_fixture(smoke=True, cycle_limit=600, max_seconds=1800)
        self.assertEqual(report['stop_reason'], 'duration_limit')
        self.assertGreaterEqual(report['ended'] - report['started'], 1800)
        self.assertFalse(report['acceptance_passed'])
        self.assertNotEqual(code, 0)

    def test_smoke_still_obeys_a_shorter_explicit_overall_deadline(self):
        _, report = self.run_fixture(smoke=True, cycle_limit=600, max_seconds=600)
        self.assertEqual(report['stop_reason'], 'duration_limit')
        self.assertGreaterEqual(report['ended'] - report['started'], 600)
        self.assertLess(report['ended'] - report['started'], 601)
        self.assertFalse(report['acceptance_passed'])

    def test_wall_jump_keeps_group_interval_and_monotonic_command_rate(self):
        code, report = self.run_fixture(wall_jump=True, max_groups=2)
        groups=report['group_launches']
        self.assertEqual(len(groups),2)
        self.assertEqual(groups[1]['started_monotonic_ms']-groups[0]['started_monotonic_ms'],120000)
        self.assertLess(groups[1]['started_at'],groups[0]['started_at'])
        self.assertTrue(all(s['command_rate']==4 for s in report['samples'] if s['groups']==2))
        self.assertTrue(all(s['command_rate']==2 for s in report['samples'][1:] if s['groups']==1))
        self.assertFalse(report['sampling_integrity']['passed'])
        self.assertIn('wall_clock_discontinuity',report['sampling_integrity']['reasons'])
        self.assertNotEqual(code,0)

    def test_fps_override_remains_distinct_and_records_actual_command(self):
        code, candidate=self.run_fixture(client_max_fps=30)
        _, baseline=self.run_fixture()
        self.assertEqual(code,0)
        self.assertEqual(candidate['load_contract']['client_max_fps'],30)
        self.assertNotEqual(candidate['load_contract'],baseline['load_contract'])
        self.assertIn('--max-fps',candidate['launch_receipts'][0]['command'])
        self.assertNotIn('--max-fps',baseline['launch_receipts'][0]['command'])

    def test_generator_memory_redline_is_not_server_capacity(self):
        code,report=self.run_fixture(generator_observation={'available':True,'host_memory_available_bytes':1024**3})
        self.assertEqual(code,3)
        self.assertIn('generator_memory_low',report['all_triggers'])
        self.assertFalse(report['acceptance_passed'])

    def test_explicit_500mb_floor_replaces_legacy_percent_and_generator_floor(self):
        code, report = self.run_fixture(memory_floor=500000000,
            resource_changes={'memory_available':10,'memory_available_bytes':500000000},
            generator_observation={'available':True,'host_memory_available_bytes':500000000})
        self.assertEqual(code,0)
        self.assertEqual(report['load_contract']['minimum_cloud_memory_bytes'],500000000)
        self.assertEqual(report['load_contract']['minimum_generator_memory_bytes'],500000000)
        self.assertNotIn('memory_available_redline',report['all_triggers'])

    def test_absolute_cloud_floor_violation_remains_a_capacity_stop(self):
        code, report = self.run_fixture(memory_floor=500000000,
            resource_changes={'memory_available':90,'memory_available_bytes':499999999})
        self.assertNotEqual(code,0)
        self.assertIn('memory_available_bytes_redline',report['all_triggers'])
        self.assertFalse(report['acceptance_passed'])

    def test_generator_missing_monitor_cannot_claim_success(self):
        code, report = self.run_fixture(generator_observation={'available':False})
        self.assertEqual(code,3)
        self.assertIn('generator_memory_monitoring_unavailable',report['all_triggers'])

    def test_coordinator_records_separate_north_america_latency_contract(self):
        code,report=self.run_fixture(latency_limits=[5000,8000,10000,5])
        self.assertEqual(code,0)
        self.assertEqual([report['load_contract'][key] for key in ['http_p95_limit_ms','command_p95_limit_ms','health_limit_ms','monitor_timeout_seconds']],[5000,8000,10000,5])


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
        self.assertEqual(len(report['launch_receipts']), 1)
        launch = report['launch_receipts'][0]
        self.assertEqual(launch['pid'], 4242)
        self.assertEqual(launch['client_id'], report['process_exits'][0]['client_id'])
        self.assertTrue(launch['process_epoch'])
        self.assertEqual(launch['server_origin'], {'scheme': 'http', 'host': '127.0.0.1', 'port': 5000})
        self.assertNotIn('token', launch)
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

    def test_redline_and_final_audit_loss_keep_both_causes_and_exit_three(self):
        code, report = self.run_fixture(resource_changes={'cpu': 95, 'memory_available': 10},
                                       final_status_change=lambda row: row.update(audit_lost_count=2))
        self.assertEqual(code, 3)
        self.assertIn('cpu_redline', report['all_triggers'])
        self.assertIn('memory_available_redline', report['all_triggers'])
        self.assertIn('final_audit_loss', report['all_triggers'])
        self.assertEqual(report['final_audit_lost_count'], 2)

    def test_cycle_observation_budget_is_pinned_without_changing_capacity_targets(self):
        code, report = self.run_fixture(cycle_limit=600)
        self.assertEqual(code, 0)
        self.assertEqual(report['load_contract']['cycle_limit_seconds'], 600)
        self.assertEqual(report['load_coverage']['target_active'], 1)
        self.assertEqual(report['load_coverage']['minimum_window'], 600)

    def test_invalid_cycle_budget_is_rejected_before_launch_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (0, 59, 2401, -1):
                argv = ['gameplay_load_test.py', '--godot', sys.executable,
                        '--cycle-limit-seconds', str(value), '--output', directory]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        coordinator.main()
                    self.assertEqual(error.exception.code, 2)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_gdd_deep_expedition_budget_does_not_change_required_load_window(self):
        code, report = self.run_fixture(cycle_limit=1200)
        self.assertEqual(code, 0)
        self.assertEqual(report['load_contract']['cycle_limit_seconds'], 1200)
        self.assertEqual(report['load_coverage']['minimum_window'], 600)

    def test_explicit_long_combat_budget_keeps_original_capacity_contract(self):
        code, report = self.run_fixture(cycle_limit=2400)
        self.assertEqual(code, 0)
        self.assertEqual(report['load_contract']['cycle_limit_seconds'], 2400)
        self.assertEqual(report['load_coverage']['minimum_window'], 600)
        self.assertEqual(report['load_coverage']['minimum_coverage'], .95)
        self.assertEqual(report['load_coverage']['target_active'], 1)

    def test_larger_cycle_budget_still_obeys_explicit_overall_deadline(self):
        _, report = self.run_fixture(smoke=True, cycle_limit=1200, max_seconds=600)
        self.assertEqual(report['stop_reason'], 'duration_limit')
        self.assertGreaterEqual(report['ended'] - report['started'], 600)
        self.assertLess(report['ended'] - report['started'], 601)


if __name__ == '__main__':
    unittest.main()
