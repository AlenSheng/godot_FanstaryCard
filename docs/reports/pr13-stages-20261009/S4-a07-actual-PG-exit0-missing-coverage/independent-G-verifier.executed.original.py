"""Independent local byte/XML/JSON identity audit; no experiment calculation."""
import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

B = Path(__file__).parent
R = B.parents[1]
OUT = B / 'A07-exit0-missing-PG-coverage-r2-independent-G-check'
assert not OUT.exists()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_bytes())


receipt_path = B / 'A07-exit0-missing-PG-coverage-r2-complete-original-G-backup/complete-original-G-receipt.original.json'
receipt = read(receipt_path)
G = Path(receipt['local_directory'])
archive = Path(receipt['local_archive'])
assert receipt['ok'] and receipt['all_original_members_SHA_verified'] and receipt['archive_gzip_CRC_verified']
assert archive.stat().st_size == receipt['archive_bytes'] and sha(archive) == receipt['archive_sha256']
with gzip.open(archive, 'rb') as stream:
    while stream.read(65536):
        pass
manifest_path = G / 'complete-original-manifest.json'
assert sha(manifest_path) == receipt['manifest_sha256']
manifest = read(manifest_path)
assert len(manifest['files']) == receipt['original_members'] == 22
for row in manifest['files']:
    path = G / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
plan = read(G / 'work/plan.original.json')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip()
for row in plan['source_files']:
    raw = subprocess.check_output(['git', 'show', head + ':' + row['path']], cwd=R)
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
assert len(plan['source_files']) == 328
runtime = Path('G:/PR13Evidence/current-process27-r2/native-build/artifacts/bin/FantasyCard.Server.Tests/release')
assert len(plan['runtime_files']) == 146
for row in plan['runtime_files']:
    path = runtime / row['path']
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
guard_raw = subprocess.check_output(['git', 'show', head + ':tools/pr13_suite_coverage.py'], cwd=R)
assert guard_raw == (G / 'work/pr13_suite_coverage.original.py').read_bytes()
result = read(G / 'evidence/result.original.json')
assert result['ok'] and result['exit_code'] == result['actual_native_job_exit_code'] == 0 and not result['oom_killed']
assert result['actual_native_PG_rows'] == 1 and result['owned_containers_removed']
assert result['isolated_PG_schemas_before'] == result['isolated_PG_schemas_after'] == 0
assert result['original_source_runtime_and_work_inputs_unchanged'] and result['private_environment_removed_after_owned_containers_ended']
started = read(G / 'evidence/started.original.json')
assert started['actual_cloud_release_sha'] == head and started['state']['MainPID'] == str(started['pid'])
actual_report = G / 'evidence/persistent-output/coverage-control.original.json'
assert sha(actual_report) == result['actual_control_report_sha256']
report = read(actual_report)
method = plan['selected_actual_PG_method']
tree = ET.parse(G / 'evidence/persistent-output/results/partial-native.original.trx')
counts = {key: int(value) for key, value in tree.find('.//{*}Counters').attrib.items()}
assert counts['total'] == counts['executed'] == counts['passed'] == 1 and counts['failed'] == counts['notExecuted'] == 0
definitions = {row.attrib['id']: row.find('{*}TestMethod').attrib['name'] for row in tree.findall('.//{*}UnitTest')}
rows = tree.findall('.//{*}UnitTestResult')
assert len(rows) == 1 and rows[0].attrib['outcome'] == 'Passed' and definitions[rows[0].attrib['testId']] == method
missing = {name: count for name, count in plan['required_original_nine_methods'].items() if name != method}
coverage = report['actual_partial_native_coverage_guard']
assert len(missing) == 8 and coverage['missing_assertion_rows'] == missing and coverage['state'] == 'Blocked'
assert coverage['acceptance'] is False and report['coverage_acceptance_rejected_despite_actual_exit0']
assert report['actual_native_job_exit_code'] == 0 and report['actual_native_rows'] == 1 and report['native_skipped'] == 0
positive = report['unchanged_original_full_native9_positive_guard']
assert positive['state'] == 'CoveredForMainReview' and positive['counters']['passed'] == 9
assert sha(G / 'work/full-native-nine.original.trx') == plan['original_full_native9_TRX_sha256']
assert (G / 'work/full-native-nine.original.trx').read_bytes() == (R / 'docs/reports/pr13-stages-20261009/S3-a07-current-numerical-postgres-nine/native-nine.original.trx').read_bytes()
db = report['actual_database_persist_restore_receipt']
assert db['caseId'] == 'PR13-B02.1-T02' and db['status'] == 'Passed'
assert [row['observations'] for row in db['actual']['rows']] == [[0, 0, 1, 1, 2], [2, 2, 2, 2, 2]]
assert all(row['FenxianDrawPolicy'] == row['GuardianShieldPolicy'] == 1 for row in db['actual']['rows'])
proof = {'ok': True, 'native_clean': True, 'owned_container_removed': True, 'source_inputs_match_git': True,
         'implementation_source_sha': head, 'actual_native_source_sha': started['actual_cloud_release_sha'],
         'actual_native_PG_rows': 1, 'actual_job_exit_code': 0, 'expected_original_methods': 9, 'actual_missing_methods': 8,
         'actual_coverage_state': 'Blocked', 'all_G_original_members_rehashed': 22,
         'all_G_archive_SHA_and_CRC_rechecked': True, 'current_Git_source_members': 328,
         'shared_G_runtime_members_rehashed': 146, 'original_full_native9_not_reexecuted': True,
         'actual_database_receipt': db, 'current_suite_guard_exact_Git_bytes': True,
         'no_local_native_or_statistical_work': True, 'MAIN_accepted': False}
OUT.mkdir()
(OUT / 'independent-G-check.original.json').write_bytes((json.dumps(proof, indent=2) + '\n').encode())
print(json.dumps({key: value for key, value in proof.items() if key != 'actual_database_receipt'}))
