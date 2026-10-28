"""Actual PostgreSQL partial native job plus current coverage/gate guards."""
import importlib.util
import json
import subprocess
from pathlib import Path

W = Path('/work')
O = Path('/output')
plan = json.loads((W / 'plan.original.json').read_bytes())
method = plan['selected_actual_PG_method']
args = ['dotnet', 'vstest', '/runtime/FantasyCard.Server.Tests.dll',
        '/TestCaseFilter:FullyQualifiedName=FantasyCard.Server.Tests.Persistence.PostgresNumericalContractTests.' + method,
        '/ResultsDirectory:/output/results', '/Logger:trx;LogFileName=partial-native.original.trx']
with (O / 'partial-native.stdout.original.log').open('xb') as stdout, (O / 'partial-native.stderr.original.log').open('xb') as stderr:
    native = subprocess.run(args, cwd='/source/server', stdout=stdout, stderr=stderr, timeout=180)
assert native.returncode == 0, 'Native job must actually exit zero'
spec = importlib.util.spec_from_file_location('actual_current_suite_guard', W / 'pr13_suite_coverage.original.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
partial = guard.assess_trx(O / 'results/partial-native.original.trx', plan['required_original_nine_methods'])
assert partial['counters']['total'] == partial['counters']['executed'] == partial['counters']['passed'] == 1
assert partial['counters']['failed'] == partial['counters']['notExecuted'] == 0
assert method not in partial['missing_assertion_rows'] and len(partial['missing_assertion_rows']) == 8
assert partial['state'] == 'Blocked' and partial['acceptance'] is False
positive = guard.assess_trx(W / 'full-native-nine.original.trx', plan['required_original_nine_methods'])
assert positive['state'] == 'CoveredForMainReview' and positive['counters']['passed'] == 9
assert not positive['missing_assertion_rows'] and positive['acceptance'] is False
receipt = json.loads((O / 'native-receipts/PR13-B02.1-T02.json').read_bytes())
assert receipt['status'] == 'Passed' and len(receipt['actual']['rows']) == 2
report = {'ok': True, 'case_id': 'PR13-A07.3-T03', 'profile': 'POSTGRES',
          'actual_native_job_exit_code': native.returncode, 'actual_current_PG_method': method,
          'actual_native_rows': 1, 'native_skipped': 0,
          'expected_original_suite_methods': 9, 'actual_missing_methods': 8,
          'actual_partial_native_coverage_guard': partial,
          'unchanged_original_full_native9_positive_guard': positive,
          'original_full_native9_not_reexecuted': True,
          'actual_database_persist_restore_receipt': receipt,
          'coverage_acceptance_rejected_despite_actual_exit0': True,
          'no_strength_experiment_or_capacity_claim': True, 'MAIN_accepted': False}
(O / 'coverage-control.original.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
print(json.dumps({'ok': True, 'actual_native_exit': 0, 'actual_PG_rows': 1, 'missing_methods': 8, 'coverage': 'Blocked'}))
