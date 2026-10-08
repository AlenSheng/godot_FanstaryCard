"""Exercise the coordinator's final verdict with deterministic owned artifacts.

No live server or simulated capacity claim: the clock and child are fixtures.
The assertions cover the actual main/report/exit path, not a second verdict.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gameplay_load_test as coordinator


class FinalizationTests(unittest.TestCase):
    def run_fixture(self, anomaly=None, *, real_child_after_stop=False, report_write_fails=False,
                    operator_stop=False, receipt_write_fails=False):
        elapsed = [0.0]
        child = SimpleNamespace(pid=4242, returncode=0)
        child.poll = lambda: child.returncode
        clock = SimpleNamespace(
            time=lambda: 100000 + elapsed[0],
            monotonic=lambda: elapsed[0],
            monotonic_ns=lambda: int(elapsed[0] * 1e9),
            sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
            strftime=time.strftime)

        def launch(*args, env, **kwargs):
            nonlocal child
            if real_child_after_stop:
                child = subprocess.Popen([sys.executable, '-c',
                    'import pathlib,sys,time\n'
                    'while not pathlib.Path(sys.argv[1]).exists(): time.sleep(.005)\n'
                    'raise SystemExit(7)\n', env['FANTASYCARD_LOAD_STOP_FILE']])
            report = Path(env['FANTASYCARD_LOAD_REPORT'])
            events = [dict(run_id=env['FANTASYCARD_LOAD_RUN_ID'],
                           client_id=env['FANTASYCARD_LOAD_CLIENT_ID'],
                           process_epoch=env['FANTASYCARD_LOAD_PROCESS_EPOCH'],
                           event_seq=n, at_unix_ms=100000000 + n,
                           type='lifecycle', cycle_id=f'cycle:{(n + 1) // 2}',
                           match_id=f'match:{(n + 1) // 2}',
                           event_type='settlement.acknowledged' if n % 2 else 'cycle.completed')
                      for n in range(1, 7)]
            status = dict(run_id=env['FANTASYCARD_LOAD_RUN_ID'],
                          client_id=env['FANTASYCARD_LOAD_CLIENT_ID'],
                          process_epoch=env['FANTASYCARD_LOAD_PROCESS_EPOCH'],
                          pid=child.pid, status_seq=1, now_unix_ms=100000000,
                          online=False, room=False, last_progress_age_ms=0,
                          cycles_completed=3, event_seq_max=6, telemetry=events,
                          operations=[], audit_lost_count=0, errors=[],
                          cleanup={'state': 'Passed'})
            report.write_text(json.dumps(dict(status, ok=True)), encoding='utf8')
            Path(str(report) + '.status.json').write_text(json.dumps(status), encoding='utf8')
            Path(str(report) + '.telemetry.jsonl').write_text(
                ''.join(json.dumps(e) + '\n' for e in events), encoding='utf8')
            if operator_stop:
                Path(env['FANTASYCARD_LOAD_STOP_FILE']).touch()
            return child

        def stop(processes, stop_file):
            if real_child_after_stop:
                return coordinator_stop_all(processes, stop_file, grace_seconds=5)
            stop_file.touch()
            if anomaly:
                anomaly(processes[0], child)
            return []

        with tempfile.TemporaryDirectory() as directory:
            coordinator_stop_all = coordinator.stop_all
            coordinator_save = coordinator.save
            def save(path, data):
                if receipt_write_fails and path.name == 'launch-manifest.json' and data['launches']:
                    raise OSError('injected launch receipt disk failure after child start')
                if report_write_fails and path.name == 'report.json':
                    raise OSError('injected final report disk failure')
                return coordinator_save(path, data)
            argv = ['gameplay_load_test.py', '--smoke', '--godot', sys.executable,
                    '--max-seconds', '20', '--output', directory]
            with patch.object(sys, 'argv', argv), patch.object(coordinator, 'time', clock), \
                    patch.object(coordinator, 'subprocess', SimpleNamespace(
                        Popen=launch, STDOUT=subprocess.STDOUT,
                        SubprocessError=subprocess.SubprocessError)), \
                    patch.object(coordinator, 'provenance', return_value={'fixture': True}), \
                    patch.object(coordinator, 'health_probe', return_value={
                        'ok': True, 'duration_ms': 1, 'status': 200}), \
                    patch.object(coordinator, 'generator_resources', return_value=({}, None)), \
                    patch.object(coordinator, 'stop_all', side_effect=stop), \
                    patch.object(coordinator, 'save', side_effect=save), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = coordinator.main()
            reports = list(Path(directory).glob('*/report.json'))
            if report_write_fails:
                self.assertEqual(reports, [])
                emergency = list(Path(directory).glob('*/report.emergency.txt'))
                self.assertEqual(len(emergency), 1)
                return code, {'emergency': emergency[0].read_text(encoding='utf8')}
            self.assertEqual(len(reports), 1)
            return code, json.loads(reports[0].read_text(encoding='utf8'))

    @staticmethod
    def change_status(entry, change):
        path = Path(str(entry['report']) + '.status.json')
        status = json.loads(path.read_text(encoding='utf8'))
        status['status_seq'] += 1
        change(status)
        path.write_text(json.dumps(status), encoding='utf8')

    def assert_invalid(self, anomaly):
        code, report = self.run_fixture(anomaly)
        self.assertEqual(code, 3)
        self.assertEqual(report['result_dimensions']['dimensions']['evidence'], 'Failed')
        self.assertFalse(report['acceptance_passed'])
        self.assertFalse(report['outcome']['passed'])
        return report

    def test_complete_owned_smoke_keeps_exit_zero_and_scope(self):
        code, report = self.run_fixture()
        self.assertEqual(code, 0)
        self.assertTrue(report['acceptance_passed'])
        self.assertFalse(report['full_acceptance_passed'])
        self.assertEqual(report['cycle_cutoffs']['final']['completed_cycles'], 3)

    def test_launch_receipt_write_fault_still_reaps_the_real_owned_child(self):
        code, report = self.run_fixture(real_child_after_stop=True, receipt_write_fails=True)
        self.assertEqual(code, 3)
        self.assertFalse(report['acceptance_passed'])
        self.assertTrue(report['stop_reason'].startswith('coordinator_error:'))
        self.assertEqual(len(report['process_exits']), 1)
        self.assertEqual(report['process_exits'][0]['after_stop'], 7)
        self.assertEqual(len(report['launch_receipts']), 1)
        self.assertEqual(report['launch_receipts'][0]['client_id'], report['process_exits'][0]['client_id'])

    def test_operator_stop_before_first_sample_keeps_exit_130_without_acceptance(self):
        code, report = self.run_fixture(operator_stop=True)
        self.assertEqual(code, 130)
        self.assertFalse(report['acceptance_passed'])
        self.assertEqual(report['stop_reason'], 'operator_stop_file')
        self.assertEqual(report['result_dimensions']['dimensions']['evidence'], 'Failed')

    def test_audit_loss_only_in_final_status_invalidates_verdict(self):
        self.assert_invalid(lambda e, c: self.change_status(e, lambda s: s.update(audit_lost_count=1)))

    def test_malformed_final_audit_loss_invalidates_verdict(self):
        for value in (True, -1, '1'):
            with self.subTest(value=value):
                self.assert_invalid(lambda e, c: self.change_status(e, lambda s: s.update(audit_lost_count=value)))

    def test_invalid_metric_only_in_tail_invalidates_verdict(self):
        def anomaly(entry, child):
            def add(status):
                event = dict(status['telemetry'][-1], event_seq=7, type='realtime',
                             event_type='realtime', duration_ms=-1)
                status['telemetry'].append(event)
                status['event_seq_max'] = 7
                with Path(str(entry['report']) + '.telemetry.jsonl').open('a', encoding='utf8') as f:
                    f.write(json.dumps(event) + '\n')
            self.change_status(entry, add)
        self.assert_invalid(anomaly)

    def test_foreign_audit_event_cannot_add_completed_cycle(self):
        def anomaly(entry, child):
            path = Path(str(entry['report']) + '.telemetry.jsonl')
            event = json.loads(path.read_text().splitlines()[-1])
            event.update(run_id='another-run', event_seq=7, cycle_id='foreign', match_id='foreign')
            with path.open('a', encoding='utf8') as f:
                f.write(json.dumps(event) + '\n')
        report = self.assert_invalid(anomaly)
        self.assertEqual(report['cycle_cutoffs']['final']['completed_cycles'], 3)

    def test_audit_sequence_gap_cannot_be_hidden_by_full_status(self):
        def anomaly(entry, child):
            path = Path(str(entry['report']) + '.telemetry.jsonl')
            rows = path.read_text().splitlines()
            path.write_text('\n'.join(rows[1:]) + '\n', encoding='utf8')
        self.assert_invalid(anomaly)

    def test_audit_tail_missing_below_final_high_watermark_is_invalid(self):
        def anomaly(entry, child):
            path = Path(str(entry['report']) + '.telemetry.jsonl')
            rows = path.read_text().splitlines()
            path.write_text('\n'.join(rows[:-1]) + '\n', encoding='utf8')
        self.assert_invalid(anomaly)

    def test_audit_file_missing_cannot_be_recreated_from_status_ring(self):
        self.assert_invalid(lambda e, c: Path(str(e['report']) + '.telemetry.jsonl').unlink())

    def test_final_report_write_failure_emits_emergency_and_exit_three(self):
        code, report = self.run_fixture(report_write_fails=True)
        self.assertEqual(code, 3)
        self.assertIn('injected final report disk failure', report['emergency'])
        self.assertIn("'exit_code': 3", report['emergency'])

    def test_final_status_missing_cannot_use_cached_cleanup_as_final_evidence(self):
        self.assert_invalid(lambda e, c: Path(str(e['report']) + '.status.json').unlink())

    def test_final_status_bad_json_is_invalid_evidence_exit_three(self):
        self.assert_invalid(lambda e, c: Path(str(e['report']) + '.status.json').write_text('{broken'))

    def test_changed_final_status_without_heartbeat_advance_is_invalid(self):
        def anomaly(entry, child):
            path = Path(str(entry['report']) + '.status.json')
            status = json.loads(path.read_text())
            status['audit_lost_count'] = 1
            path.write_text(json.dumps(status), encoding='utf8')
        self.assert_invalid(anomaly)

    def test_final_cycle_and_error_schema_are_checked_after_last_sample(self):
        for change in (dict(cycles_completed=True), dict(errors='invalid')):
            with self.subTest(change=change):
                self.assert_invalid(lambda e, c: self.change_status(e, lambda s: s.update(change)))

    def test_final_counter_must_equal_archived_completions(self):
        self.assert_invalid(lambda e, c: self.change_status(e, lambda s: s.update(cycles_completed=4)))

    def test_foreign_final_report_cannot_prove_smoke_success(self):
        original = coordinator.completed_smoke
        def foreign(processes, expected_clients, cycles):
            path = processes[0]['report']
            report = json.loads(path.read_text())
            report['run_id'] = 'another-run'
            path.write_text(json.dumps(report), encoding='utf8')
            return original(processes, expected_clients, cycles)
        with patch.object(coordinator, 'completed_smoke', side_effect=foreign):
            code, report = self.run_fixture()
        self.assertNotEqual(code, 0)
        self.assertFalse(report['acceptance_passed'])

    def test_business_error_only_after_stop_prevents_smoke_acceptance(self):
        code, report = self.run_fixture(lambda e, c: self.change_status(
            e, lambda s: s.update(errors=[{'message': 'late unexpected write failure'}])))
        self.assertEqual(code, 1)
        self.assertFalse(report['acceptance_passed'])
        self.assertEqual(report['result_dimensions']['dimensions']['gameplay'], 'Failed')
        self.assertIn('final_business_failure', report['all_triggers'])

    def test_explicit_business_cleanup_failure_stays_failed(self):
        code, report = self.run_fixture(lambda e, c: self.change_status(
            e, lambda s: s.update(cleanup={'state': 'Failed'})))
        self.assertEqual(code, 1)
        self.assertEqual(report['result_dimensions']['dimensions']['cleanup'], 'Failed')

    def test_child_exit_seven_after_stop_is_failed_cleanup_not_accepted(self):
        code, report = self.run_fixture(lambda e, c: setattr(c, 'returncode', 7))
        self.assertEqual(code, 3)
        self.assertFalse(report['acceptance_passed'])
        self.assertEqual(report['result_dimensions']['dimensions']['cleanup'], 'Failed')
        self.assertFalse(report['process_cleanup_complete'])

    def test_real_child_exits_seven_only_after_stop_and_is_reaped(self):
        code, report = self.run_fixture(real_child_after_stop=True)
        self.assertEqual(code, 3)
        self.assertEqual(report['process_exits'][0]['before_stop'], None)
        self.assertEqual(report['process_exits'][0]['after_stop'], 7)
        self.assertFalse(report['process_cleanup_complete'])
        self.assertFalse(report['acceptance_passed'])
        self.assertEqual(report['result_dimensions']['dimensions']['cleanup'], 'Failed')


if __name__ == '__main__':
    unittest.main()
