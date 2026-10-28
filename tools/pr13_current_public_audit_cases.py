"""Audit actual frozen public stage bytes and source/derived lineage on cloud."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.pr13_public_evidence import derived_identity, inspect_public, validated_files


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(root, output, source_sha):
    if output.exists():
        raise ValueError('Preserve previous audit originals')
    output.mkdir(parents=True)
    prefix = root / 'docs/reports/pr13-stages-20261009'
    stages = ['S4-historical-inventory-audit', 'S4-b09-natural-continuity-first-four-render',
              'S4-b09-natural-continuity-fifth-render']
    originals = {}
    ledger = []
    for slug in stages:
        folder = prefix / slug
        manifest = folder / 'manifest.json'
        entries = json.loads(manifest.read_bytes())['files']
        paths = validated_files(folder, entries)
        originals[manifest] = sha(manifest)
        for row, path in zip(entries, paths):
            data = path.read_bytes()
            if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != row['git_blob_sha1']:
                raise ValueError('Public member differs from recorded Git object')
            originals[path] = row['sha256']
            ledger.append({'path': path.relative_to(root).as_posix(), 'bytes': len(data),
                           'sha256': row['sha256'], 'git_blob_sha1': row['git_blob_sha1']})

    controlled = output / 'controlled-private-inputs'
    controlled.mkdir()
    target = controlled / 'same-name.json'
    original_summary = prefix / stages[-1] / 'summary.json'
    target.write_bytes(original_summary.read_bytes())
    entry = {'path': target.name, 'bytes': target.stat().st_size, 'sha256': sha(target)}
    validated_files(controlled, [entry])
    value = json.loads(target.read_bytes())
    value['current_cloud_UI_rows'] += 1
    target.write_text(json.dumps(value) + '\n')
    overwritten_rejected = False
    try:
        validated_files(controlled, [entry])
    except ValueError as error:
        overwritten_rejected = 'changed after immutable manifest' in str(error)
    if not overwritten_rejected or sha(target) == entry['sha256']:
        raise ValueError('Same-name replacement was not rejected')

    rejections = []
    marker = 'controlled_private_value_20261011'
    for index, value in enumerate([{'access_token': marker}, {'authorization': 'Bearer ' + marker},
                                   {'nested': {'ticket_body': {'status': 'Ready'}}}]):
        path = controlled / ('sensitive-' + str(index) + '.json')
        path.write_text(json.dumps(value) + '\n')
        try:
            inspect_public(path)
        except ValueError as error:
            reason = str(error)
            if marker in reason:
                raise ValueError('Rejected private value leaked in an error')
            rejections.append(reason)
    if len(rejections) != 3:
        raise ValueError('Credential boundary control did not reject all inputs')

    plan = json.loads((root / 'docs/plans/PR13_B09_NATURAL_CONTINUITY_RENDER_20261011.json').read_bytes())
    lineage = []
    for slug in stages[1:]:
        folder = prefix / slug
        summary = json.loads((folder / 'summary.json').read_bytes())
        total = 0
        for parent in sorted(folder.rglob('native-result.json')):
            native = json.loads(parent.read_bytes())
            rows = native['observations']
            indexes = {int(row['index']) for row in rows}
            keys = [(int(row['index']), tuple(row['resolution']), row['frame_cap'], row['controlled_delay_ms']) for row in rows]
            expected = set(itertools.product(indexes, map(tuple, plan['resolutions']),
                                             plan['frame_caps'], plan['controlled_response_delay_ms']))
            if not native['ok'] or native['failures'] or len(keys) != len(set(keys)) or set(keys) != expected:
                raise ValueError('Actual source rows do not cover the frozen Cartesian matrix')
            if not all(row['passed'] for row in rows):
                raise ValueError('Actual original observation failed')
            identity = derived_identity(parent, folder / 'summary.json')
            if identity['parent']['sha256'] == identity['derived']['sha256'] or identity['original_overwritten']:
                raise ValueError('Source and derived identity are not separate')
            lineage.append({'stage': slug, 'original_path': parent.relative_to(root).as_posix(),
                            'observations': len(rows), 'identity': identity})
            total += len(rows)
        if total != summary.get('cloud_rows_this_stage', summary.get('current_cloud_UI_rows')):
            raise ValueError('Derived summary does not match every original observation')
    if len(lineage) != 5 or sum(row['observations'] for row in lineage) != 567:
        raise ValueError('Missing real source lineage')
    if any(sha(path) != digest for path, digest in originals.items()):
        raise ValueError('Actual public originals changed during audit')

    records = [
        {'case_id': 'LOAD-11.2-T01', 'actual': {'actual_public_members_hash_checked': len(ledger),
          'same_filename_changed_copy_rejected': True, 'original_copy_sha256': entry['sha256'],
          'changed_copy_sha256': sha(target), 'actual_originals_unchanged': True}},
        {'case_id': 'LOAD-11.2-T02', 'actual': {'actual_public_members_inspected': len(ledger),
          'credential_controls_rejected': 3, 'reasons_without_values': rejections,
          'raw_private_control_files_excluded_from_public_report': True}},
        {'case_id': 'LOAD-11.2-T03', 'actual': {'actual_original_native_files': 5,
          'actual_original_native_observations': 567, 'all_derived_counts_reconciled': True,
          'parent_and_derived_SHA256_recorded_separately': True, 'lineage': lineage}},
    ]
    for record in records:
        record.update(executed=True, status='Passed', profiles_executed=['AUDIT'], source_sha=source_sha,
                      scope='Current actual frozen public evidence and owned corruption/secret controls; no old historical raw recovery, game rerun, DB/LIVE or whole MAIN acceptance')
    (output / 'cases.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
    report = {'ok': True, 'source_sha': source_sha, 'executed': 3, 'passed': 3,
              'profiles': ['AUDIT'], 'actual_public_input_members': len(ledger),
              'all_actual_original_bytes_unchanged': True, 'source_lineage': lineage,
              'controlled_private_inputs_never_publish': True, 'MAIN_accepted': False}
    (output / 'input-ledger.json').write_text(json.dumps(ledger, indent=2) + '\n')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ok': True, 'actual_public_input_members': len(ledger), 'AUDIT_cases_passed': 3,
                      'actual_native_parent_observations': 567, 'MAIN_accepted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    if len(args.source_sha) != 40 or any(c not in '0123456789abcdef' for c in args.source_sha):
        raise ValueError('Exact parent source SHA required')
    execute(args.root, args.output, args.source_sha)
