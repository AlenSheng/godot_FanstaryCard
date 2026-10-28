"""Explicit PR13 OFFLINE faults through the actual coordinator and owned processes.

Clock/network observations in coordinator fixtures are controlled inputs, not
live-server or capacity evidence. Native child and Godot cases use real processes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.tests.test_gameplay_load_finalization import FinalizationTests
from tools.tests.test_gameplay_load_sampling_contract import CoordinatorSamplingContractTests
from tools.cloud_load_test import stop_all
from tools.gameplay_load_validation import provenance
from tools.pr13_runtime_evidence import reconcile_cycles


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode())


def native_fixtures(output, godot):
    """Start two real engines with seeded, owned userdata before autoload starts."""
    processes = []
    records = []
    results = []
    try:
        for number in range(2):
            directory = output / ("native-" + str(number))
            directory.mkdir()
            env = dict(os.environ, FANTASYCARD_SERVER_URL="http://127.0.0.1:1",
                       FANTASYCARD_LOAD_RUN_ID="fault-" + uuid.uuid4().hex,
                       PR13_FAULT_REPORT=str(directory / "result.json"))
            for key, folder in {"APPDATA": "roaming", "LOCALAPPDATA": "local", "TEMP": "temp", "TMP": "temp",
                                "XDG_DATA_HOME": "data", "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache"}.items():
                path = directory / folder
                path.mkdir(exist_ok=True)
                env[key] = str(path)
            userdata = directory / ("roaming/Godot/app_userdata/Relicbound" if os.name == "nt"
                                    else "data/godot/app_userdata/Relicbound")
            userdata.mkdir(parents=True)
            session = userdata / "session.cfg"
            session.write_bytes(b'[session]\ndevice_id="fixture-shared-device"\nsequence=999\nroom_id="fixture-old-room"\nrevision=17\n')
            before = hashlib.sha256(session.read_bytes()).hexdigest()
            command = [godot, "--headless", "--path", str(ROOT / "client"), "--script", "res://tests/pr13_load_faults.gd"]
            log = (directory / "engine.log").open("w", encoding="utf8")
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            processes.append((child, log))
            records.append(dict(pid=child.pid, command=command, directory=directory, session=session, before=before))
        for item, (child, log) in zip(records, processes):
            code = child.wait(timeout=30)
            log.close()
            result = json.loads((item['directory'] / "result.json").read_text(encoding="utf8"))
            if code != 0 or any(not case['passed'] for case in result['cases']):
                raise AssertionError("Native fault fixture failed: " + str(item['directory']))
            session_case = next(case for case in result['cases'] if case['case_id'] == 'LOAD-07.3-T03')
            assert session_case['actual']['pid'] == child.pid
            assert hashlib.sha256(item['session'].read_bytes()).hexdigest() == item['before']
            results.append(result)
        identities = [next(c['actual'] for c in r['cases'] if c['case_id'] == 'LOAD-07.3-T03') for r in results]
        assert len({r['device_id_sha256'] for r in identities}) == 2
        assert len({r['userdata'] for r in identities}) == 2
        write(output / 'native-launches.json', {'launches': [
            {k: str(v) if isinstance(v, Path) else v for k, v in item.items()} for item in records]})
        return results
    finally:
        for child, log in processes:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            log.close()


def forced_child_case():
    with tempfile.TemporaryDirectory() as directory:
        owned = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        outside = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        started = time.monotonic()
        try:
            forced = stop_all([{'process': owned}], Path(directory) / 'STOP', grace_seconds=.1)
            actual = dict(owned_pid=owned.pid, outside_pid=outside.pid, forced=forced,
                          owned_exit=owned.poll(), outside_alive=outside.poll() is None,
                          cleanup_seconds=time.monotonic() - started)
            return actual, forced == [owned.pid] and owned.poll() is not None and outside.poll() is None and actual['cleanup_seconds'] < 15
        finally:
            for child in (owned, outside):
                if child.poll() is None: child.kill()
                child.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--godot', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan_path = ROOT / 'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
    plan = json.loads(plan_path.read_text(encoding='utf8'))
    contracts = {case['id']: case for package in plan['packages'] for task in package['subtasks'] for case in task['test_cases']}
    native = native_fixtures(output, args.godot)
    fixture = FinalizationTests()
    sampler = CoordinatorSamplingContractTests()
    cache = {}

    def cached(name, action):
        if name not in cache:
            actual, passed = action()
            write(output / (name + '.json'), {'actual': actual, 'passed': bool(passed)})
            cache[name] = (actual, passed)
        return cache[name]

    def failure_before_stop():
        def fail(entry, child):
            fixture.change_status(entry, lambda s: s.update(errors=[{'message': 'before_stop_business_failure'}]))
            path = entry['report']; row = json.loads(path.read_text(encoding='utf8'))
            row.update(ok=False, outcome='failed', errors=[{'message': 'before_stop_business_failure'}])
            path.write_text(json.dumps(row), encoding='utf8'); child.returncode = 1
        code, report = fixture.run_fixture(operator_stop=True, before_stop=fail)
        return {'exit_code': code, 'report': report}, code != 0 and report['process_exits'][0]['before_stop'] == 1 and 'final_business_failure' in report['all_triggers']

    def redline(corrupt=False):
        code, report = sampler.run_fixture(resource_changes={'cpu': 95, 'memory_available': 10},
            final_status_change=(lambda row: row.update(audit_lost_count=2)) if corrupt else None)
        passed = code == (3 if corrupt else 2) and all(cause in report['all_triggers'] for cause in ['cpu_redline', 'memory_available_redline'])
        if corrupt: passed = passed and report['final_audit_lost_count'] == 2 and 'final_audit_loss' in report['all_triggers']
        return {'exit_code': code, 'report': report}, passed

    def bad_json():
        code, report = fixture.run_fixture(lambda entry, child: Path(str(entry['report']) + '.status.json').write_text('{broken', encoding='utf8'))
        return {'exit_code': code, 'report': report}, code == 3 and report['final_read_errors'] > 0 and not report['acceptance_passed']

    def late_exit():
        code, report = fixture.run_fixture(real_child_after_stop=True)
        return {'exit_code': code, 'report': report}, code == 3 and report['process_exits'][0]['before_stop'] is None and report['process_exits'][0]['after_stop'] == 7 and report['result_dimensions']['dimensions']['cleanup'] == 'Failed'

    def archive_gap():
        def remove(entry, child):
            path = Path(str(entry['report']) + '.telemetry.jsonl')
            lines = path.read_text(encoding='utf8').splitlines()
            path.write_text('\n'.join(lines[:-1]) + '\n', encoding='utf8')
        code, report = fixture.run_fixture(remove)
        return {'exit_code': code, 'report': report}, code == 3 and bool(report['audit_read_errors']) and not report['acceptance_passed']

    def emergency():
        code, report = fixture.run_fixture(report_write_fails=True)
        return {'exit_code': code, **report}, code == 3 and 'injected final report disk failure' in report['emergency']

    def audit_loss():
        observations = [next(c['actual'] for c in r['cases'] if c['case_id'] == 'LOAD-07.3-T02') for r in native]
        code, report = fixture.run_fixture(lambda entry, child: fixture.change_status(entry, lambda row: row.update(audit_lost_count=2)))
        return {'native_write_failures': observations, 'exit_code': code, 'report': report}, all(x['audit_lost_count'] == 2 for x in observations) and code == 3 and report['final_audit_lost_count'] == 2

    def cycle_event(seq, at, kind):
        return dict(run_id='fixture', client_id='client', process_epoch='epoch', event_seq=seq,
                    at_unix_ms=at, cycle_id='client:1', match_id='match', event_type=kind)

    def cutoffs(which):
        rows = [cycle_event(1, 110, 'settlement.acknowledged'), cycle_event(2, 120, 'cycle.completed')]
        if which == 2: rows = [dict(r, at_unix_ms=99) for r in rows] * 2
        if which == 3:
            report = reconcile_cycles([], 100, 200)
            return {'reported_final_cycles': 1, 'authority': 'Unknown', 'derived': report}, report['final']['acknowledgements'] == 0 and report['final']['completed_cycles'] == 0 and report['zero_cycle_clients'] is None
        report = reconcile_cycles(rows, 100, 200)
        passed = not report['evidence_errors'] and report['final']['acknowledgements'] == report['final']['completed_cycles'] == 1
        if which == 1: passed = passed and report['running']['acknowledgements'] == 0 and report['drain']['acknowledgements'] == 1
        return report, passed

    actions = {
        'LOAD-02.1-T02': ('business-before-stop', failure_before_stop),
        'LOAD-02.1-T03': ('redline-and-corruption', lambda: redline(True)),
        'LOAD-02.3-T02': ('forced-owned-child', forced_child_case),
        'LOAD-02.3-T03': ('emergency-report', emergency),
        'LOAD-02.4-T02': ('all-redline-causes', redline),
        'LOAD-07.3-T02': ('native-audit-write-loss', audit_loss),
        'LOAD-07.3-T03': ('native-session-isolation', lambda: (native, True)),
        'LOAD-07.4-T01': ('bad-final-json', bad_json),
        'LOAD-07.4-T02': ('real-exit-seven', late_exit),
        'LOAD-07.4-T03': ('forced-owned-child', forced_child_case),
        'PR13-A02.3-T01': ('bad-final-json', bad_json),
        'PR13-A02.3-T02': ('real-exit-seven', late_exit),
        'PR13-A02.3-T03': ('missing-archive-tail', archive_gap),
    }
    for number in range(1, 4): actions['PR13-A01.2-T0' + str(number)] = ('cutoffs-' + str(number), lambda n=number: cutoffs(n))
    records = []
    for case_id, (name, action) in actions.items():
        case = contracts[case_id]
        record = dict(case_id=case_id, executed=True, setup=case['setup_and_injection'], expected=case['expected'],
                      profiles_executed=['OFFLINE'], artifact=name + '.json', started_at=time.time())
        try:
            actual, passed = cached(name, action)
            record.update(status='Passed' if passed else 'Failed', actual=actual)
        except Exception as error:
            record.update(status='Failed', error=repr(error))
        records.append(record)
    (output / 'cases.jsonl').write_bytes(''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in records).encode())
    source_paths = ('tools/pr13_fault_cases.py', 'tools/tests/test_gameplay_load_finalization.py',
                    'tools/tests/test_gameplay_load_sampling_contract.py', 'tools/gameplay_load_test.py',
                    'tools/cloud_load_test.py', 'tools/pr13_runtime_evidence.py', 'client/tests/pr13_load_faults.gd',
                    'client/tests/gameplay_load_client.gd', 'client/network/gateway.gd')
    source_paths += ('client/project.godot',)
    source = provenance(ROOT, source_paths)
    report = dict(source_sha=source['git_commit'], source=source,
                  plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                  kind='explicit_offline_fault_cases', scope=__doc__, executed=len(records),
                  passed=sum(r['status'] == 'Passed' for r in records), all_cases_accepted=False,
                  missing_layers='POSTGRES/LIVE requirements remain separate; controlled clock/network fixtures do not claim live gameplay or capacity.')
    write(output / 'report.json', report)
    write(output / 'manifest.json', {'files': [dict(path=p.relative_to(output).as_posix(), bytes=p.stat().st_size,
          sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(output.rglob('*'))
          if p.is_file() and 'native-' not in p.relative_to(output).parts[0]]})
    print(json.dumps({key: report[key] for key in ('executed', 'passed', 'source_sha')}))
    return 0 if report['executed'] == report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
