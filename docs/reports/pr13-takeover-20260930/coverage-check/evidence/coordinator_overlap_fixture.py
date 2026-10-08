"""Fixed offline coordinator fixture: slow read plus a one-second wall-clock step.

All child processes, monitoring and health responses are in-memory fixtures.
The original main writes and reads real temporary report/audit files.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path('/workspace/godot_FanstaryCard')
sys.path.insert(0, str(ROOT / 'tools'))
import gameplay_load_test as coordinator


def run(runtime_module=None):
    if runtime_module:
        spec = importlib.util.spec_from_file_location('fixture_runtime', runtime_module)
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        coordinator.coverage = runtime.coverage
        coordinator.sampling_integrity = runtime.sampling_integrity
    elapsed = [0.0]
    child = SimpleNamespace(pid=4242, returncode=None)
    child.poll = lambda: child.returncode
    clock = SimpleNamespace(
        time=lambda: 100000 + elapsed[0] - (1 if elapsed[0] >= 300 else 0),
        monotonic=lambda: elapsed[0],
        monotonic_ns=lambda: int(elapsed[0] * 1e9),
        sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds),
        strftime=time.strftime)
    events = []
    heartbeat = [0]

    def launch(*args, env, **kwargs):
        return child

    def read_status(processes, cache=None, now_monotonic_ms=None, *, require_files=False):
        if elapsed[0] == 290:
            elapsed[0] += 9  # Observation at 299s, followed by the tick at 300s.
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
        with patch.object(sys, 'argv', argv), patch.object(coordinator, 'time', clock), \
                patch.object(coordinator, 'subprocess', SimpleNamespace(
                    Popen=launch, STDOUT=subprocess.STDOUT,
                    SubprocessError=subprocess.SubprocessError)), \
                patch.object(coordinator, 'provenance', return_value={'offline_fixture': True}), \
                patch.object(coordinator, 'health_probe', return_value={
                    'ok': True, 'duration_ms': 1, 'status': 200}), \
                patch.object(coordinator, 'metrics', return_value={
                    'cpu': 1, 'memory_available': 90, 'disk_available': 90}), \
                patch.object(coordinator, 'generator_resources', return_value=({}, None)), \
                patch.object(coordinator, 'read_owned_statuses', side_effect=read_status), \
                patch.object(coordinator, 'stop_all', side_effect=stop), \
                contextlib.redirect_stdout(io.StringIO()):
            code = coordinator.main()
        reports = list(Path(directory).glob('*/report.json'))
        assert len(reports) == 1
        report = json.loads(reports[0].read_text())
    return dict(exit_code=code, network=False, actual_main=True,
        timeline=[{'at': s['at'], 'sample_monotonic_ms': s['sample_monotonic_ms']}
                  for s in report['samples'] if 289000 <= s['sample_monotonic_ms'] <= 310000],
        outcome=report['outcome'], acceptance_passed=report['acceptance_passed'],
        stop_reason=report['stop_reason'], sampling_integrity=report['sampling_integrity'],
        load_coverage=report['load_coverage'], result_dimensions=report['result_dimensions'],
        final_triggers=report['final_triggers'], final_read_errors=report['final_read_errors'])


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else None), indent=2))
