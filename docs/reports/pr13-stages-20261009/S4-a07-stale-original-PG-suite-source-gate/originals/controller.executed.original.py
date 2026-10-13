"""Tencent current guard consumes an actual old PG suite without relabeling it."""
import hashlib
import importlib.util
import json
import os
import subprocess
import urllib.request
from pathlib import Path

R = Path('/opt/fantasycard-github')
E = Path('/home/ubuntu/pr13-acceptance-20261009/evidence/A07-stale-original-PG-suite-gate-r1-20261013')
S0 = 'docs/reports/pr13-stages-20261009/S0-a07-stale-original-PG-suite-source-gate'
OLD_SUITE = 'docs/reports/pr13-stages-20261009/S3-a07-current-numerical-postgres-nine'


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(R), '-C', str(R), *args], timeout=45)


def sha(data):
    return hashlib.sha256(data).hexdigest()


assert not E.exists()
head = git('rev-parse', 'HEAD').decode().strip()
frozen_plan = git('show', head + ':' + S0 + '/plan.original.json')
plan = json.loads(frozen_plan)
original_trx = git('show', head + ':' + OLD_SUITE + '/native-nine.original.trx')
original_result_raw = git('show', head + ':' + OLD_SUITE + '/native-result.original.json')
original_result = json.loads(original_result_raw)
assert sha(original_trx) == plan['actual_original_native_TRX_sha256']
assert sha(original_result_raw) == plan['actual_original_native_result_sha256']
assert original_result['ok'] and original_result['exit_code'] == 0 and not original_result['oom_killed']
assert original_result['owned_containers_removed'] and original_result['remaining_owned_fixture_schemas'] == 0
old_sha = original_result['frozen_release_sha']
assert old_sha == plan['actual_original_native_source_sha'] and old_sha != head
guard_raw = git('show', head + ':tools/pr13_suite_coverage.py')
assert sha(guard_raw) == plan['current_suite_guard_sha256']
for row in plan['source_files']:
    raw = git('show', head + ':' + row['path'])
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
assert len(plan['source_files']) == 328
available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))) * 1024
disk = os.statvfs('/')
assert available >= 500000000 and disk.f_bavail / disk.f_blocks >= .15
with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10) as response:
    assert response.status == 200
E.mkdir()
controller_raw = git('show', head + ':' + S0 + '/controller.original.py')
assert sha(controller_raw) == plan['controller_sha256']
(E / 'controller.executed.original.py').write_bytes(controller_raw)
for name, data in [('plan.original.json', frozen_plan), ('full-native-nine.original.trx', original_trx),
                   ('full-native-result.original.json', original_result_raw), ('current-suite-guard.original.py', guard_raw)]:
    (E / name).write_bytes(data)
spec = importlib.util.spec_from_file_location('current_suite_guard', E / 'current-suite-guard.original.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
coverage = guard.assess_trx(E / 'full-native-nine.original.trx', plan['actual_original_required_methods'])
assert coverage['state'] == 'CoveredForMainReview' and coverage['counters']['passed'] == 9
assert not coverage['missing_assertion_rows'] and not coverage['skipped_cases']
# The source label comes from the unchanged real native result, never from
# the analysis release or an invented workflow-success flag.
suites = {'PostgresNumerical': {'state': coverage['state'], 'source_sha': old_sha}}
negative = guard.assess_gate(suites, ['PostgresNumerical'], expected_source_sha=head)
positive = guard.assess_gate(suites, ['PostgresNumerical'], expected_source_sha=old_sha)
assert negative['state'] == 'Blocked' and negative['stale_source_suites'] == ['PostgresNumerical']
assert not negative['missing_suites'] and not negative['failed_suites'] and not negative['incomplete_suites']
assert negative['acceptance'] is False and positive['state'] == 'ReadyForMainReview' and positive['acceptance'] is False
assert not positive['stale_source_suites']
assert sha(original_trx) == sha((E / 'full-native-nine.original.trx').read_bytes())
report = {'ok': True, 'case_id': 'PR13-A07.4-T03', 'profile': 'POSTGRES',
          'actual_current_guard_release_sha': head, 'actual_controller_PID': os.getpid(), 'actual_controller_sha256': sha(controller_raw), 'actual_original_PG_native_source_sha': old_sha,
          'actual_original_PG_suite_coverage': coverage, 'actual_current_source_gate': negative,
          'exact_original_source_positive_gate': positive, 'native_result_source_label_unchanged': True,
          'current_Git_source_members_verified': 328, 'actual_old_PG_native_rows': 9,
          'actual_old_PG_native_skipped': 0, 'actual_original_native_TRX_sha256': sha(original_trx),
          'actual_original_native_result_sha256': sha(original_result_raw), 'current_suite_guard_sha256': sha(guard_raw),
          'source_mismatch_is_the_only_gate_rejection': True, 'current_PG_native_reexecution_claimed': False,
          'new_native_samples': 0, 'scope': 'Current Tencent PostgreSQL suite provenance gate only; no new GitHub workflow trigger, full regression, LIVE, EXPERIMENT, capacity or MAIN acceptance',
          'memory_available_bytes': available, 'root_free_fraction': disk.f_bavail / disk.f_blocks,
          'health_status': 200, 'MAIN_accepted': False}
(E / 'source-gate-control.original.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
print(json.dumps({key: value for key, value in report.items() if key not in
      ['actual_original_PG_suite_coverage', 'actual_current_source_gate', 'exact_original_source_positive_gate']}))
