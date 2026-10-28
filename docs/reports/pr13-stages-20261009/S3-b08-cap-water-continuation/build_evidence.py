"""Build a finite B1/B2 continuation report from closed original G evidence.

No simulator, native executable, cloud command or business oracle runs here.
Every successful public result is gated by both complete G proofs and cloud
cleanup receipts. Failed or unfinished units produce no passed summary.
The publisher must verify manifest hashes against committed Git blob bytes.
"""
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

PUBLIC = Path(__file__).resolve().parent
REPO = PUBLIC.parents[3]
sys.path.insert(0, str(REPO))
from tools.cloud.pr13.cap_full_transport import verify_archive, verify_unit
from tools.cloud.pr13.cap_runtime_recovery import RUNTIME_HASHES
from tools.pr13_pool_render_evidence import read_json, require, safe_parts, sha

SOURCE = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
TOOLS_SOURCE = 'bdced93f33415e095de5e580981e8b7cbcdd92f3'
ROOT = REPO / 'outputs/pr13-tencent-20261009'
G = ROOT / 'cap-experiment-full-r2-raw'
UNITS = ('Mage-E1-Water-L5-B1', 'Mage-E1-Water-L5-B2')
PLAN = 'docs/plans/PR13_B08_CAP_EFFECTIVE_EXPERIMENT_20261011.json'
BLOCK = 65536


def save(name, value):
    path = PUBLIC / name
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if name == 'manifest.json':
        # This is a derived index of this unpublished report, not an original
        # native/G/cloud receipt. Rebuild it after any intentional report edit.
        path.write_bytes(content)
    elif path.exists():
        require(path.read_bytes() == content, 'Existing public report differs: ' + name)
    else:
        path.write_bytes(content)


def copy_original(source, name):
    target = PUBLIC / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(sha(target) == sha(source), 'Existing public original differs')
    else:
        shutil.copyfile(source, target)
    require(target.stat().st_size == source.stat().st_size and sha(target) == sha(source), 'Original copy differs')


def runtime_proof():
    backup = ROOT / 'cap-runtime-recovery-backup'
    receipt = read_json(backup / 'local-backup-receipt.json')
    archive = backup / 'delivery.private.tar.gz'
    manifest_path = backup / 'delivery-manifest.json'
    require(receipt['ok'] is True and receipt['bytes'] == archive.stat().st_size
            and receipt['sha256'] == sha(archive) and receipt['manifest_sha256'] == sha(manifest_path),
            'Original recovery runtime G backup differs')
    manifest = read_json(manifest_path)
    expected = {row['path']: row for row in manifest['files']}
    require(len(expected) == len(manifest['files']) == receipt['members'] == receipt['members_verified'],
            'Runtime archive member count differs')
    with gzip.open(archive, 'rb') as stream:
        for _ in iter(lambda: stream.read(BLOCK), b''):
            pass
    members = {}
    inputs = None
    root_name = None
    with tarfile.open(archive, mode='r|gz') as stream:
        for member in stream:
            require(member.isfile(), 'Runtime archive contains a link or special entry')
            parts = safe_parts(member.name)
            require(len(parts) > 1, 'Runtime archive original root is absent')
            root_name = root_name or parts[0]
            require(parts[0] == root_name, 'Runtime archive has mixed roots')
            name = '/'.join(parts[1:])
            require(name not in members, 'Duplicate original runtime member')
            source = stream.extractfile(member)
            digest = hashlib.sha256()
            size = 0
            capture = bytearray() if name == 'metadata/inputs.json' else None
            for block in iter(lambda: source.read(BLOCK), b''):
                digest.update(block)
                size += len(block)
                if capture is not None:
                    capture.extend(block)
                    require(len(capture) <= 1024**2, 'Runtime input metadata exceeds its bound')
            source.close()
            require(size == member.size, 'Runtime original member size differs')
            if name == 'manifest.json':
                require(digest.hexdigest() == receipt['manifest_sha256'], 'Embedded runtime manifest differs')
            else:
                require(name in expected and expected[name]['bytes'] == size
                        and expected[name]['sha256'] == digest.hexdigest(), 'Runtime original SHA differs')
            members[name] = digest.hexdigest()
            if capture is not None:
                inputs = json.loads(capture)
    require(set(members) == set(expected) | {'manifest.json'} and inputs is not None,
            'Original runtime members or recovery source inputs missing')
    require(inputs['source_sha'] == SOURCE and len(inputs['source_hashes']) == 372,
            'Frozen 372-file source subset differs')
    source_hashes = inputs['source_hashes']
    require(all(members.get('persistent/source/' + name) == digest for name, digest in source_hashes.items()),
            'Original persisted source members differ from recovery inputs')
    runtime_hashes = {name: members.get('persistent/runtime/' + name) for name in RUNTIME_HASHES}
    require(runtime_hashes == RUNTIME_HASHES and len(runtime_hashes) == 8,
            'Recovered compiled runtime differs from eight original hashes')
    # Git object reads verify code provenance; no native or business execution.
    requests = b''.join((SOURCE + ':' + name + '\n').encode('utf-8') for name in source_hashes)
    process = subprocess.run(['git', 'cat-file', '--batch'], input=requests, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=REPO, check=True)
    original_blobs = io.BytesIO(process.stdout)
    for name, digest in source_hashes.items():
        header = original_blobs.readline().decode('ascii').strip().split()
        require(len(header) == 3 and header[1] == 'blob', 'Frozen source Git blob missing')
        content = original_blobs.read(int(header[2]))
        require(hashlib.sha256(content).hexdigest() == digest and original_blobs.read(1) == b'\n',
                'Recovery source member differs from exact native Git bytes')
    require(not original_blobs.read(1), 'Unexpected source Git batch output')
    return {'source_sha': SOURCE, 'runtime_original_hashes': runtime_hashes,
            'source_subset_files_verified': 372, 'source_subset_G_members_match_frozen_Git_bytes': True,
            'inputs_sha256': members['metadata/inputs.json'], 'original_2068_directory_restored': False,
            'runtime_backup_archive_sha256': receipt['sha256'], 'runtime_backup_manifest_sha256': receipt['manifest_sha256'],
            'runtime_backup_original_members_verified': receipt['members']}


def main():
    for unit in UNITS:
        require((G / unit / 'verified/local-backup-receipt.json').is_file()
                and (G / unit / 'cloud-cleanup-receipt.json').is_file(),
                'Both complete unit G/cleanup proofs required before a passed stage can be built')
    prior_path = ROOT / 'cap-full-r2-adoption-revision2.json'
    adoption = read_json(prior_path)
    require(adoption['schema_version'] == 2 and adoption['kind'] == 'cap-experiment-full-r2-explicit-adoption'
            and adoption['source_sha'] == SOURCE and adoption['whole_task_accepted'] is False
            and adoption['logical_verified_units'] == 88 and adoption['original_G_verified_units'] == 87
            and adoption['named_raw_recovery_units'] == 1 and len(adoption['entries']) == 88,
            'Prior logical 88-unit adoption differs')
    require(len({row['unit'] for row in adoption['entries']}) == 88
            and all(row['unit'] not in UNITS for row in adoption['entries']),
            'New Water units overlap prior adopted original/recovery evidence')
    public_prior = REPO / 'docs/reports/pr13-stages-20261009/S0-b08-persistent-continuation/adoption-revision2.json'
    require(sha(public_prior) == sha(prior_path), 'Published prior adoption differs from original local G metadata')
    plan_blob = subprocess.check_output(['git', 'show', TOOLS_SOURCE + ':' + PLAN], cwd=REPO)
    plan = json.loads(plan_blob)
    require(plan['schema_version'] == 2 and plan['native_units'] == 360
            and plan['expected_encounters'] == 720000 and plan['expected_pairs'] == 360000
            and plan['paired_seeds_per_block_and_stratum'] == 1000, 'Frozen full scope differs')
    recovered = runtime_proof()
    outputs = []
    outcomes = Counter()
    total_casts = total_ticks = total_events = total_rows = total_pairs = reclaimed = 0
    copies = []
    for unit in UNITS:
        local = G / unit
        extraction = local / 'verified'
        transfer = read_json(local / 'transport-receipt.json')
        receipt = read_json(extraction / 'local-backup-receipt.json')
        cleanup = read_json(local / 'cloud-cleanup-receipt.json')
        archive = local / 'delivery.private.tar.gz'
        require(transfer['ok'] is True and receipt['ok'] is True and cleanup['ok'] is True,
                'Failed or unfinished native unit retained; no passed continuation report')
        manifest = verify_archive(archive, transfer, extraction, transfer['output_budget_bytes'] + 16 * 1024**2)
        verified = verify_unit(extraction, manifest, unit)
        require(all(receipt[key] == value for key, value in verified.items())
                and receipt['members_verified'] == len(manifest['files']), 'Saved G proof differs from independent reinspection')
        require(cleanup['unit'] == unit and cleanup['source_sha'] == SOURCE
                and cleanup['manifest_sha256'] == receipt['manifest_sha256'] == transfer['manifest_sha256']
                and cleanup['local_G_archive_sha256'] == receipt['sha256'] == transfer['sha256']
                and cleanup['local_G_archive_bytes'] == receipt['bytes'] == transfer['bytes']
                and cleanup['cloud_raw_removed'] is True and cleanup['source_runtime_and_metadata_retained'] is True
                and cleanup['whole_task_accepted'] is False and cleanup['full_formal_pending'] is True,
                'Cloud cleanup is not anchored to the complete original G archive')
        prereg = read_json(extraction / 'metadata/preregistration.json')
        result = read_json(extraction / 'metadata/result.json')
        native = extraction / 'outputs' / unit / 'native'
        summary = read_json(native / 'summary.json')
        validation = read_json(extraction / 'outputs' / unit / 'validation.json')
        require(prereg['runtime_contract']['runtime_hashes'] == recovered['runtime_original_hashes']
                and prereg['runtime_contract']['source_subset_files'] == recovered['source_subset_files_verified']
                and prereg['runtime_contract']['inputs_sha256'] == recovered['inputs_sha256']
                and result['source_subset_files'] == 372, 'Execution runtime/372 input provenance differs')
        runner = extraction / 'metadata/runner.py'
        require(sha(runner) == prereg['runner_sha256'], 'Actual cloud runner differs from preregistration SHA')
        prefix = 'units/' + unit + '/'
        for original, name in (
            (extraction / 'metadata/result.json', 'result.json'),
            (extraction / 'metadata/preregistration.json', 'preregistration.json'),
            (native / 'summary.json', 'native-summary.json'),
            (native / 'manifest.json', 'native-manifest.json'),
            (extraction / 'outputs' / unit / 'validation.json', 'cloud-validation.json'),
            (extraction / 'manifest.json', 'delivery-manifest.json'),
            (extraction / 'local-backup-receipt.json', 'local-backup-receipt.json'),
            (local / 'cloud-cleanup-receipt.json', 'cloud-cleanup-receipt.json'),
        ):
            copies.append((original, prefix + name))
        runner_provenance = {'native_execution_source_sha': SOURCE,
            'controller_tools_publication_source_sha': TOOLS_SOURCE,
            'actual_cloud_runner_sha256': sha(runner), 'runner_original_G_relative_path': unit + '/verified/metadata/runner.py',
            'native_runtime_relabelled_to_tools_commit': False,
            'native_runtime_original_hashes': recovered['runtime_original_hashes']}
        outputs.append({'unit': unit, 'seed_start': prereg['seed_start'], 'seed_end': prereg['seed_end'],
            'encounters_verified': verified['raw_encounters_verified'], 'pairs_verified': verified['raw_pairs_verified'],
            'actual_casts_verified': verified['actual_casts_verified'], 'actual_ticks_verified': verified['actual_ticks_verified'],
            'raw_events_verified': verified['raw_events_verified'], 'outcomes': verified['original_outcomes_verified'],
            'case_denominators': validation['case_denominators'], 'cloud_negative_controls': validation['negative_controls'],
            'native_summary_passed': summary['passed'], 'cloud_validation_ok': validation['ok'],
            'G_archive_bytes': receipt['bytes'], 'G_archive_sha256': receipt['sha256'],
            'G_manifest_sha256': receipt['manifest_sha256'], 'G_original_members_verified': len(manifest['files']),
            'inner_gzip_files_verified': verified['inner_gzip_files_verified'], 'archive_and_inner_CRC_SHA_counts_reverified': True,
            'cloud_cleanup_verified': True, 'root_disk_bytes_reclaimed': cleanup['root_disk_bytes_reclaimed'],
            'runner_provenance': runner_provenance, 'formal_EXPERIMENT_pending': True, 'MAIN_accepted': False})
        total_casts += verified['actual_casts_verified']
        total_ticks += verified['actual_ticks_verified']
        total_events += verified['raw_events_verified']
        total_rows += verified['raw_encounters_verified']
        total_pairs += verified['raw_pairs_verified']
        outcomes.update(verified['original_outcomes_verified'])
        reclaimed += cleanup['root_disk_bytes_reclaimed']
        print(json.dumps({'unit': unit, 'G_raw_encounters': verified['raw_encounters_verified'],
                          'G_raw_events': verified['raw_events_verified'], 'cloud_cleanup_verified': True}), flush=True)
    require(total_rows == 4000 and total_pairs == 2000 and total_events == total_casts + total_ticks,
            'Complete two-unit continuation counts differ')
    fair_hold = ROOT / 'release_pool_hold_after_water_G_verified-stdout.txt'
    released = read_json(fair_hold)
    require(released['ok'] is True and released['logical_G_verified_units'] == 90
            and released['native_encounters_G_verified'] == 180000 and released['remaining_original_units'] == 270
            and released['render_native_not_restarted'] is True and released['whole_task_accepted'] is False,
            'Render scheduling release is not anchored to these complete Water G units')
    copies.append((fair_hold, 'cloud-render-fair-hold-ended.json'))
    # No passed artifact is written until both full original evidence gates pass.
    for source, name in copies:
        copy_original(source, name)
    for unit in outputs:
        save('units/' + unit['unit'] + '/runner-source.json', unit['runner_provenance'])
    save('runtime-provenance.json', recovered)
    save('summary.json', {'ok': True, 'task_id': 'PR13-B08.4', 'stage': 'S3_EXPERIMENT_two_Water_units_closed',
        'native_execution_source_sha': SOURCE, 'controller_tools_publication_source_sha': TOOLS_SOURCE,
        'native_execution_source_not_relabelled': True, 'units': outputs,
        'new_G_verified_units': 2, 'new_G_verified_encounters': total_rows, 'new_G_verified_pairs': total_pairs,
        'new_actual_casts_verified': total_casts, 'new_actual_ticks_verified': total_ticks,
        'new_original_raw_events_verified': total_events, 'all_original_outcomes': dict(outcomes),
        'cloud_root_disk_bytes_reclaimed_sum': reclaimed,
        'prior_adoption': {'path': public_prior.relative_to(REPO).as_posix(), 'sha256': sha(prior_path),
                           'logical_G_verified_units': 88, 'original_G_verified_units': 87, 'separate_missing_raw_recovery_units': 1},
        'coverage_after_these_two_units': {'logical_G_verified_units': 90, 'required_native_units': 360,
            'native_execution_attempts_with_successful_results': 91,
            'execution_count_includes_original_missing_raw_B0_and_its_separate_recovery': True,
            'G_verified_encounters': 180000, 'G_verified_pairs': 90000,
            'remaining_units': 270, 'remaining_encounters': 540000, 'remaining_pairs': 270000},
        'frozen_plan': {'path': PLAN, 'source_sha': TOOLS_SOURCE, 'committed_blob_sha256': hashlib.sha256(plan_blob).hexdigest(),
                        'revision': 2, 'full_expected_encounters': 720000, 'full_expected_pairs': 360000},
        'full_statistics_and_applicability_pending': True, 'formal_EXPERIMENT_pending': True,
        'MAIN_accepted': False, 'LIVE_accepted': False, 'capacity_tests_deferred': True,
        'human_experience_in_current_scope': False, 'whole_task_accepted': False,
        'card_deck_or_balance_values_changed': False, 'Guardian_long_progressing_fights_are_not_a_contract_failure': True,
        'complete_original_raw_archives_retained_on_G_not_copied_to_Git': True,
        'no_native_business_executed_locally': True, 'current_register_states_unchanged': True,
        'publication_manifest_committed_Git_bytes_verification_required': True})
    files = [{'path': path.relative_to(PUBLIC).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(PUBLIC.rglob('*')) if path.is_file() and path.name != 'manifest.json' and '__pycache__' not in path.parts]
    save('manifest.json', {'files': files})
    print(json.dumps({'ok': True, 'new_encounters': 4000, 'new_pairs': 2000,
                      'actual_events': total_events, 'public_members': len(files), 'full_formal_pending': True}), flush=True)


if __name__ == '__main__':
    main()
