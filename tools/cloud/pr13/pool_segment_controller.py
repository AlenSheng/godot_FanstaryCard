"""Cloud B09.2 segment queue. Requires verified G backup before reclamation.

One action per invocation; launch observation errors never cause a second launch.
Only owned passed output directories are reclaimed. Sources and failed results
are retained. This controller makes no whole-task acceptance claim.
"""
import argparse
import base64
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time


DEFAULT_ROOT = Path('/home/ubuntu/pr13-acceptance-20261009')
GROUP = 'pool-render-segments-r3'
UNIT_PREFIX = 'pr13-pool-segment-r3-'
NATIVE_SOURCE = '1341e160afc67ba826d4b37250c9ec58f8c99462'
MONITOR = '2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
OUTPUT_LIMIT = 64 * 1024**2
METADATA_RESERVE = 16 * 1024**2
RENDER_MEMORY = 1536 * 1024**2
LANGUAGES = ('zh-CN', 'en')
CAP_ATTEMPT = 'cap-missing-raw-recovery-r1'
CAP_OWNER = 'pr13-cap-missing-raw-recovery-r1'
CAP_UNIT = 'pr13-cap-missing-raw-recovery-mage-e1-water-l5-b0'
CAP_RAW_UNIT = 'Mage-E1-Water-L5-B0'
CAP_FULL_GROUP = 'cap-experiment-full-r2'
CAP_FULL_OWNER = 'pr13-cap-experiment-full-r2'
CAP_FULL_SOURCE = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
CAP_FULL_PREFIX = 'pr13-cap-full-r2-'
CAP_MIXED_GROUP = 'cap-experiment-full-r3'
CAP_MIXED_OWNER = 'pr13-' + CAP_MIXED_GROUP
CAP_MIXED_PREFIX = 'pr13-cap-full-r3-'
CAP_MIXED_COLLECTOR = 'cap-effective-raw-budget-v2'
CAP_MIXED_OUTPUT = 512 * 1024**2
CAP_MIXED_RAW_MIN = 16 * 1024**3
CAP_MIXED_RAW_MAX = 32 * 1024**3
CAP_MIXED_OVERRIDES = ('server/tools/FantasyCard.Numerics/CapEffectiveExperiment.cs',
                       'tools/pr13_cap_effective_experiment.py')
CAP_DOMAIN_HASHES = {
    'FantasyCard.Domain.pdb': '986c5b1be4366ef9e91a70c671a210d3bd2b53f72fcb53be7e1088433a80a7e5',
    'FantasyCard.Domain.dll': '6e8650494db8e95dbf6a47af0eaf880a119bc36f348a9aaa9cd9437ca969249a',
    'FantasyCard.Domain.deps.json': '84049a6e2e274b4fd62887cce60fbf77aeeee5336c87f7d5150d602fb887a553',
}
CAP_ORIGINAL_NUMERICS_DLL = 'cb9d50683a13957eeeb442824d26b06c209356e61a0289c2dc9fe9988a68c0df'
MUTABLE_METADATA = {'delivery-manifest.json', 'local-backup-receipt.json',
                    'local-storage-cleanup.json', 'cleanup-intent.json'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or linked metadata file: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    temporary = path.with_name(path.name + '.controller-tmp')
    require(not temporary.exists(), 'Preserve existing interrupted metadata write')
    raw = (json.dumps(data, indent=2) + '\n').encode('utf-8')
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def exact(path, root, exists=True):
    require(path.is_absolute() and path.is_relative_to(root) and path != root,
            'Target outside exact owned root')
    require(not path.is_symlink(), 'Linked owned path is rejected')
    require(path.resolve(strict=exists) == path, 'Owned path resolves through a link')
    if exists:
        require(path.is_dir(), 'Owned directory missing')
    return path


def segment_plan(evidence):
    plan = read(evidence / 'plan.json')
    require(plan.get('native_source_sha') == NATIVE_SOURCE and plan.get('whole_task_accepted') is False,
            'Plan source or scope changed')
    require(re.fullmatch('[0-9a-f]{40}', plan.get('render_source_sha', '')) is not None, 'Missing frozen render source')
    require(plan.get('languages') == list(LANGUAGES), 'Product queue must declare the existing Chinese and English locales')
    expected = []
    for hero, capacity, case, language in itertools.product(
            ('Guardian', 'Mage', 'Priest'), (8, 5, 3), ('T02', 'T01', 'T03'), LANGUAGES):
        expected.append({'id': f'{hero}-{capacity}-{case}-{language}', 'hero': hero, 'capacity': capacity,
                         'case': 'PR13-B09.2-' + case, 'language': language,
                         'expected_rows': 162 if case == 'T03' else 81, 'expected_PNGs': 9})
    require(plan.get('segments') == expected, 'Frozen 54 product-locale segment order/matrix changed')
    require(plan.get('all_required_rows') == 5832 and plan.get('all_required_PNGs') == 486,
            'Frozen full matrix size changed')
    return plan


def unit_status(segment):
    name = UNIT_PREFIX + segment['id'].lower()
    result = subprocess.run(['systemctl', 'show', name,
                             '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'],
                            capture_output=True, text=True, timeout=15)
    require(result.returncode == 0, 'Could not authoritatively inspect exact unit')
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require('MainPID' in values and 'ActiveState' in values, 'Incomplete exact unit status')
    return {'unit': name, 'MainPID': int(values['MainPID']), 'ActiveState': values['ActiveState'],
            'SubState': values.get('SubState'), 'LoadState': values.get('LoadState'),
            'ExecMainStatus': int(values.get('ExecMainStatus', '0'))}


def live(status):
    return status['MainPID'] != 0 or status['ActiveState'] in ('active', 'activating', 'deactivating', 'reloading')


def terminal(status):
    require(not live(status) and status['MainPID'] == 0, 'Exact native segment is still live')
    require(status['ExecMainStatus'] == 0, 'Native exact unit exited unsuccessfully')


def ordinary_files(root):
    require(root.is_dir() and not root.is_symlink(), 'Missing or linked file tree')
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            path = Path(current) / name
            require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root), 'Linked child directory')
        for name in files:
            path = Path(current) / name
            require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                    'Nonregular or linked owned file')
            yield path


def manifest_files(metadata, output):
    rows = []
    # Exclude source without traversing it; it remains available to later jobs.
    for child in sorted(metadata.iterdir()):
        if child.name == 'source' or child.name in MUTABLE_METADATA:
            continue
        require(not child.is_symlink(), 'Linked metadata input')
        paths = ordinary_files(child) if child.is_dir() else [child]
        for path in paths:
            require(path.is_file() and not path.is_symlink(), 'Nonregular metadata member')
            rows.append({'source': str(path), 'path': 'metadata/' + path.relative_to(metadata).as_posix(),
                         'bytes': path.stat().st_size, 'sha256': sha(path)})
    size = 0
    for path in sorted(ordinary_files(output)):
        size += path.stat().st_size
        rows.append({'source': str(path), 'path': 'outputs/' + path.relative_to(output).as_posix(),
                     'bytes': path.stat().st_size, 'sha256': sha(path)})
    require(size <= OUTPUT_LIMIT, 'Owned segment output exceeds frozen 64 MiB budget')
    require(sum(row['bytes'] for row in rows if row['path'].startswith('metadata/')) <= METADATA_RESERVE,
            'Owned segment metadata exceeds reserve')
    return sorted(rows, key=lambda row: row['path'])


def successful(metadata, output, segment, plan):
    prereg = read(metadata / 'preregistration.json')
    require(all(prereg.get(key) == value for key, value in segment.items()), 'Segment preregistration mismatch')
    require(prereg.get('render_source_sha') == plan['render_source_sha']
            and prereg.get('native_source_sha') == NATIVE_SOURCE and prereg.get('fixture_matrix_only') is True
            and prereg.get('whole_task_accepted') is False, 'Frozen execution source/scope changed')
    result = read(metadata / 'result.json')
    require(result.get('ok') is True and result.get('shutdown_resources_clean') is True
            and result.get('source_sha') == plan['render_source_sha'] and result.get('segment') == segment['id']
            and result.get('diagnostic_only') is False and result.get('whole_task_accepted') is False,
            'Failed or incomplete cloud segment must be retained')
    runtime = read(output / segment['case'] / 'result.json')
    require(runtime.get('ok') is True and runtime.get('exit_code') == 0 and runtime.get('native_clean') is True
            and runtime.get('native_ok') is True and runtime.get('source_inputs_unchanged') is True
            and runtime.get('owned_container_removed') is True and runtime.get('oom_killed') is False,
            'Renderer lifecycle/source evidence is incomplete')
    native = read(output / segment['case'] / 'native-result.json')
    observations = native.get('observations', [])
    require(native.get('ok') is True and native.get('diagnostic_only') is False
            and native.get('whole_task_accepted') is False and native.get('display_driver') != 'headless'
            and len(observations) == segment['expected_rows'] == runtime.get('observations')
            and runtime.get('screenshots') == 9, 'Native matrix is incomplete')
    keys = set()
    for row in observations:
        require(row.get('passed') is True and row.get('command_exact') is True
                and row.get('native_source_sha') == NATIVE_SOURCE and row.get('case_id') == segment['case']
                and row.get('hero') == segment['hero'] and row.get('capacity') == segment['capacity']
                and row.get('language') == segment['language'] and row.get('diagnostic_only') is False,
                'Failed/foreign observation must be retained')
        require(row.get('actual_command_wire') and row.get('actual_command_payload')
                and row.get('expected_native_wire_payload'), 'Missing actual native command capture; retain and rerun separately')
        require(len(base64.b64decode(row['actual_command_wire'], validate=True)) > 0,
                'Empty actual Protobuf capture')
        key = (tuple(row['resolution']), row['frame_cap'], row['controlled_response_delay_ms'],
               row['seed'], row['native_occupancy'])
        require(key not in keys, 'Duplicate native matrix key')
        keys.add(key)
    occupancy = (0, segment['capacity']) if segment['case'].endswith('T03') else (
                (segment['capacity'] - 1,) if segment['case'].endswith('T01') else (segment['capacity'],))
    expected = set(itertools.product(((1920, 1080), (1280, 720), (960, 540)), (30, 60, 144),
                                    (0, 250, 1000), (460001, 461001, 462001), occupancy))
    require(keys == expected, 'Native matrix coverage differs from frozen plan')
    return result


def manifest_validate(metadata, output, manifest):
    require(manifest['files'] == manifest_files(metadata, output), 'Current metadata/output differs from original delivery manifest')


def manifest_paths(metadata, output, manifest):
    names = set()
    for row in manifest['files']:
        name = row['path']
        parts = PurePosixPath(name).parts
        require(isinstance(name, str) and not name.startswith('/') and '\\' not in name and ':' not in name
                and len(parts) >= 2 and parts[0] in ('metadata', 'outputs')
                and '..' not in parts and '.' not in parts and name not in names
                and PurePosixPath(*parts).as_posix() == name, 'Unsafe/duplicate delivery manifest path')
        names.add(name)
        root = metadata if parts[0] == 'metadata' else output
        path = root.joinpath(*parts[1:])
        require(str(path) == row['source'] and path.is_relative_to(root), 'Delivery source is outside exact owned tree')
        require(isinstance(row['bytes'], int) and row['bytes'] >= 0
                and re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) is not None, 'Invalid delivery member hash/size')


def backup_validate(receipt, metadata, manifest, segment, plan):
    require(receipt.get('ok') is True and receipt.get('segment') == segment
            and receipt.get('manifest_sha256') == sha(metadata / 'delivery-manifest.json')
            and receipt.get('members') == receipt.get('members_verified') == len(manifest['files']),
            'G receipt is not anchored to this exact delivery manifest')
    require(receipt.get('render_source_sha') == plan['render_source_sha'] and receipt.get('native_source_sha') == NATIVE_SOURCE,
            'G receipt source mismatch')
    require(receipt.get('matrix_rows_verified') == receipt.get('independent_wire_command_rows_verified') == segment['expected_rows']
            and receipt.get('PNG_CRC_deflate_verified') == 9 and receipt.get('normal_shutdown_clean') is True
            and receipt.get('archive_gzip_CRC_verified') is True and receipt.get('no_native_business_executed_locally') is True,
            'G archive/native/image/wire verification is incomplete')
    require(receipt.get('whole_task_accepted') is False and receipt.get('full_matrix_accepted') is False
            and receipt.get('scope') == 'one cloud software-rendered fixture language segment', 'G scope changed')
    require(re.fullmatch('[0-9a-f]{64}', receipt.get('sha256', '')) is not None
            and isinstance(receipt.get('bytes'), int) and receipt['bytes'] > 0,
            'G archive byte count/SHA missing')
    require(re.match(r'^G:[\\/]', receipt.get('local_archive', ''), re.IGNORECASE)
            and re.match(r'^G:[\\/]', receipt.get('local_directory', ''), re.IGNORECASE), 'Backup is not the verified G archive')


def no_active_bind(output):
    ids = subprocess.check_output(['sudo', '-n', 'docker', 'ps', '-q'], text=True, timeout=20).split()
    if not ids:
        return
    containers = json.loads(subprocess.check_output(['sudo', '-n', 'docker', 'inspect', *ids], text=True, timeout=30))
    for container in containers:
        for mount in container.get('Mounts', []):
            if mount.get('Type') != 'bind':
                continue
            path = Path(mount['Source']).resolve()
            if container['Id'] == MONITOR and path == Path('/') and mount.get('RW') is False:
                continue
            require(not (path == output or path.is_relative_to(output) or output.is_relative_to(path)),
                    'Passed output still intersects an active container bind')


def cleaned(metadata, output, segment, plan):
    manifest = read(metadata / 'delivery-manifest.json')
    require(manifest['segment'] == segment, 'Previous segment manifest changed')
    manifest_paths(metadata, output, manifest)
    receipt = read(metadata / 'local-backup-receipt.json')
    backup_validate(receipt, metadata, manifest, segment, plan)
    cleanup = read(metadata / 'local-storage-cleanup.json')
    require(cleanup.get('ok') is True and cleanup.get('segment') == segment['id']
            and cleanup.get('manifest_sha256') == receipt['manifest_sha256']
            and cleanup.get('local_G_archive_sha256') == receipt['sha256']
            and cleanup.get('local_G_archive_bytes') == receipt['bytes']
            and cleanup.get('render_source_sha') == plan['render_source_sha']
            and cleanup.get('output_directory') == str(output) and not output.exists(), 'Previous cleanup is not verified')
    result = read(metadata / 'result.json')
    require(result.get('ok') is True and result.get('source_sha') == plan['render_source_sha'], 'Previous segment is not passed')
    for row in manifest['files']:
        if row['path'].startswith('metadata/'):
            path = Path(row['source'])
            require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(metadata)
                    and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                    'Previously backed-up execution metadata changed')
    terminal(unit_status(segment))
    return cleanup


def cap_resource_reservation(root):
    evidence = root / 'evidence' / CAP_ATTEMPT
    output = root / 'work' / CAP_ATTEMPT
    path = evidence / 'resource-reservation.json'
    if not path.exists() and not path.is_symlink():
        return {'deferred': False, 'reservation_present': False}
    report = {'deferred': True, 'reservation_present': True, 'attempt': CAP_ATTEMPT,
              'systemd_unit': CAP_UNIT, 'G_backup_required_before_render': True,
              'uncertain_hold': False}
    try:
        exact(evidence, root)
        exact(output, root, exists=False)
        marker = read(path)
        require(marker.get('attempt') == CAP_OWNER and marker.get('systemd_unit') == CAP_UNIT
                and marker.get('output_root') == str(output), 'Reservation identity/path mismatch')
        result = subprocess.run(['systemctl', 'show', CAP_UNIT,
                                 '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'],
                                capture_output=True, text=True, timeout=15)
        require(result.returncode == 0, 'Reservation exact unit could not be inspected')
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        require('MainPID' in values and 'ActiveState' in values, 'Incomplete reservation unit status')
        unit = {'unit': CAP_UNIT, 'MainPID': int(values['MainPID']), 'ActiveState': values['ActiveState'],
                'SubState': values.get('SubState'), 'LoadState': values.get('LoadState'),
                'ExecMainStatus': int(values.get('ExecMainStatus', '0'))}
        report.update(current_unit_state=unit, reservation_status=marker.get('status'),
                      G_backup_verified=marker.get('G_backup_verified') is True)
        if marker.get('status') == 'Active':
            boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
            require(isinstance(marker.get('runner_pid'), int) and marker['runner_pid'] > 0
                    and marker.get('boot_id') == boot and marker['runner_pid'] == unit['MainPID']
                    and live(unit), 'Active reservation boot/PID does not match exact live native unit')
            require(marker.get('G_backup_verified') is not True, 'Live reservation cannot already be G verified')
            report['reason'] = 'exact recovery native unit is live; wait for its terminal G backup and cleanup'
            return report
        if marker.get('status') == 'Prepared':
            require(not live(unit), 'Prepared reservation has a live unrecorded native process')
            report['reason'] = 'recovery reservation prepared; owner must finish or explicitly resolve it'
            return report
        require(marker.get('status') == 'Ended', 'Unknown reservation state')
        terminal(unit)
        require(marker.get('result_path') == str(evidence / 'result.json'), 'Reservation terminal result path differs')
        ended = read(evidence / 'result.json')
        require(ended.get('ok') is True and ended.get('attempt') == CAP_OWNER
                and ended.get('unit') == CAP_RAW_UNIT and ended.get('exit_code') == 0
                and ended.get('oom_killed') is False and ended.get('owned_container_removed') is True
                and marker.get('result_ok') is True, 'Recovery terminal native result is not successful')
        if marker.get('G_backup_verified') is not True:
            report['reason'] = 'recovery native result ended; wait for original G archive verification and cleanup'
            return report
        backup = read(evidence / 'local-backup-receipt.json')
        cleanup = read(evidence / 'local-storage-cleanup.json')
        manifest = evidence / 'delivery-manifest.json'
        require(manifest.is_file() and not manifest.is_symlink(), 'Recovery original delivery manifest missing or linked')
        require(backup.get('ok') is True and cleanup.get('ok') is True
                and re.fullmatch('[0-9a-f]{64}', backup.get('sha256', '')) is not None
                and isinstance(backup.get('bytes'), int) and backup['bytes'] > 0
                and backup.get('sha256') == cleanup.get('local_G_archive_sha256')
                and backup.get('bytes') == cleanup.get('local_G_archive_bytes')
                and backup.get('manifest_sha256') == cleanup.get('manifest_sha256') == sha(manifest),
                'Recovery G backup, cloud cleanup and original manifest are not identical')
        native = output / CAP_RAW_UNIT / 'native'
        require(not native.exists() and not native.is_symlink(), 'Recovery native original output still occupies cloud storage')
        no_active_bind(output)
        report.update(deferred=False, reason='recovery original G backup and exact output cleanup verified',
                      G_backup_verified=True, archive_sha256=backup['sha256'], manifest_sha256=backup['manifest_sha256'])
        return report
    except Exception as error:
        report.update(deferred=True, uncertain_hold=True,
                      reason='reservation identity, native terminal or G backup gate requires owner inspection',
                      error=type(error).__name__)
        return report


def cap_full_cleaned(metadata, output, name, marker):
    """Release a reservation only from exact retained execution and G evidence."""
    result = read(metadata / 'result.json')
    require(result.get('ok') is True and result.get('attempt') == CAP_FULL_OWNER
            and result.get('unit') == name and result.get('source_sha') == CAP_FULL_SOURCE
            and result.get('exit_code') == 0 and result.get('oom_killed') is False
            and result.get('compiled_runtime_unchanged_and_identical_to_original') is True
            and result.get('source_subset_inputs_unchanged') is True
            and result.get('owned_container_removed') is True
            and result.get('main_acceptance_granted') is False
            and marker.get('result_ok') is True
            and marker.get('result_path') == str(metadata / 'result.json')
            and not (metadata / 'finalization-error.json').exists(),
            'Full cap reservation lacks successful exact native execution')
    hero, group, element, level, block = name.split('-')
    block_index = int(block[1:])
    prereg = read(metadata / 'preregistration.json')
    expected = {'unit': name, 'hero': hero, 'group': group, 'element': element,
                'level': int(level[1:]), 'block': block_index,
                'seed_start': 440001 + block_index * 1000,
                'seed_end': 441000 + block_index * 1000,
                'samples_per_arm': 1000, 'expected_encounters': 2000}
    require(all(prereg.get(key) == value for key, value in expected.items())
            and prereg.get('source_sha') == CAP_FULL_SOURCE
            and prereg.get('owner') == CAP_FULL_OWNER
            and prereg.get('persistent_output_budget_bytes') == marker['persistent_output_budget_bytes'],
            'Full cap original seed/stratum preregistration differs')
    manifest_path = metadata / 'delivery-manifest.json'
    manifest = read(manifest_path)
    require(manifest.get('kind') == CAP_FULL_GROUP and manifest.get('unit') == name
            and manifest.get('source_sha') == CAP_FULL_SOURCE and manifest.get('native_encounters') == 2000
            and manifest.get('whole_task_accepted') is False and manifest.get('files'),
            'Full cap delivery manifest identity or scope differs')
    names = set()
    for row in manifest['files']:
        member = row['path']
        require(isinstance(member, str), 'Nonstring full cap member')
        parts = PurePosixPath(member).parts
        require(len(parts) >= 2 and not member.startswith('/') and '\\' not in member and ':' not in member
                and '..' not in parts and '.' not in parts and member not in names
                and member == PurePosixPath(*parts).as_posix(), 'Unsafe full cap delivery member')
        names.add(member)
        if parts[0] == 'metadata':
            path = metadata.joinpath(*parts[1:])
            require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(metadata)
                    and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                    'Backed-up full cap execution metadata changed')
        else:
            require(len(parts) >= 3 and parts[:2] == ('outputs', name), 'Foreign full cap output member')
            path = output.joinpath(*parts[2:])
        require(str(path) == row['source'] and isinstance(row['bytes'], int) and row['bytes'] >= 0
                and re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) is not None,
                'Full cap delivery source/hash/size differs')
    require({'metadata/result.json', 'metadata/preregistration.json'} <= names,
            'Full cap manifest omitted original execution evidence')
    backup = read(metadata / 'local-backup-receipt.json')
    cleanup = read(metadata / 'local-storage-cleanup.json')
    flags = ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
             'inner_gzip_CRC_raw_SHA_counts_verified', 'no_native_business_executed_locally')
    require(backup.get('ok') is True and backup.get('unit') == name and backup.get('source_sha') == CAP_FULL_SOURCE
            and backup.get('manifest_sha256') == sha(manifest_path)
            and backup.get('members') == backup.get('members_verified') == len(manifest['files'])
            and all(backup.get(key) is True for key in flags)
            and backup.get('raw_encounters_verified') == 2000
            and backup.get('actual_casts_verified') == manifest['native_casts']
            and backup.get('actual_ticks_verified') == manifest['native_ticks']
            and backup.get('raw_events_verified') == manifest['native_casts'] + manifest['native_ticks']
            and backup.get('whole_task_accepted') is False
            and re.match(r'^G:[\\/]', backup.get('local_archive', ''), re.IGNORECASE)
            and re.match(r'^G:[\\/]', backup.get('local_directory', ''), re.IGNORECASE)
            and re.fullmatch('[0-9a-f]{64}', backup.get('sha256', '')) is not None
            and isinstance(backup.get('bytes'), int) and backup['bytes'] > 0,
            'Full cap original G archive/raw evidence gate is incomplete')
    require(cleanup.get('ok') is True and cleanup.get('unit') == name
            and cleanup.get('manifest_sha256') == backup['manifest_sha256']
            and cleanup.get('local_G_archive_sha256') == marker.get('local_G_archive_sha256') == backup['sha256']
            and cleanup.get('local_G_archive_bytes') == marker.get('local_G_archive_bytes') == backup['bytes']
            and cleanup.get('output_directory') == str(output) and marker.get('output_cleaned') is True
            and not output.exists() and not output.is_symlink(),
            'Full cap exact passed output cleanup is not verified')


def cap_full_resource_reservation(root):
    evidence = root / 'evidence' / CAP_FULL_GROUP
    units = evidence / 'units'
    report = {'deferred': False, 'reservation_present': False, 'attempt': CAP_FULL_GROUP,
              'G_backup_required_before_render': True, 'uncertain_hold': False,
              'cleaned_reservations_verified': 0}
    if not evidence.exists() and not evidence.is_symlink():
        return report
    try:
        exact(evidence, root)
        if not units.exists() and not units.is_symlink():
            return report
        exact(units, evidence)
        for metadata in sorted(units.iterdir()):
            report.update(reservation_present=True, deferred=True, unit=metadata.name)
            require(re.fullmatch(r'(Mage|Priest|Guardian)-(O1|O6|E1|BOSS)-(Fire|Wood|Earth|Metal|Water)-L(0|5)-B[012]',
                                 metadata.name) is not None, 'Foreign full cap reservation unit')
            exact(metadata, units)
            output = root / 'work' / CAP_FULL_GROUP / metadata.name
            exact(output, root, exists=False)
            marker = read(metadata / 'resource-reservation.json')
            name = CAP_FULL_PREFIX + metadata.name.lower()
            budget = marker.get('persistent_output_budget_bytes')
            require(marker.get('attempt') == CAP_FULL_OWNER and marker.get('unit') == metadata.name
                    and marker.get('source_sha') == CAP_FULL_SOURCE and marker.get('systemd_unit') == name
                    and marker.get('output_root') == str(output) and type(budget) is int
                    and 96 * 1024**2 <= budget <= 512 * 1024**2
                    and marker.get('reserved_root_bytes') == budget + METADATA_RESERVE,
                    'Full cap reservation identity/source/budget differs')
            result = subprocess.run(['systemctl', 'show', name,
                                     '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'],
                                    capture_output=True, text=True, timeout=15)
            require(result.returncode == 0, 'Full cap exact unit could not be inspected')
            values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            require('MainPID' in values and 'ActiveState' in values, 'Incomplete full cap exact unit state')
            unit = {'unit': name, 'MainPID': int(values['MainPID']), 'ActiveState': values['ActiveState'],
                    'SubState': values.get('SubState'), 'LoadState': values.get('LoadState'),
                    'ExecMainStatus': int(values.get('ExecMainStatus', '0'))}
            report.update(systemd_unit=name, current_unit_state=unit, reservation_status=marker.get('status'))
            if marker.get('status') == 'Prepared':
                require(marker.get('G_backup_verified') is False, 'Prepared full cap reservation cannot be G verified')
                report['reason'] = 'full cap reservation prepared; exact owner must finish or resolve it'
                return report
            if marker.get('status') == 'Active':
                boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
                require(type(marker.get('runner_pid')) is int and marker['runner_pid'] > 0
                        and marker.get('boot_id') == boot and marker['runner_pid'] == unit['MainPID']
                        and live(unit) and marker.get('G_backup_verified') is False,
                        'Full cap active boot/PID differs from exact live native unit')
                report['reason'] = 'full cap exact native unit is live; await original G backup and cleanup'
                return report
            require(marker.get('status') == 'Ended', 'Unknown full cap reservation state')
            terminal(unit)
            if marker.get('G_backup_verified') is not True:
                report['reason'] = 'full cap unit ended; exact G backup and cleanup are still required'
                return report
            cap_full_cleaned(metadata, output, metadata.name, marker)
            report['cleaned_reservations_verified'] += 1
        # Inspect Docker once after every unit has passed its immutable G gate;
        # checking the parent also catches any intersecting unit output bind.
        no_active_bind(root / 'work' / CAP_FULL_GROUP)
        report.update(deferred=False, reason='all full cap reservations have exact G backup and output cleanup')
        return report
    except Exception as error:
        report.update(deferred=True, uncertain_hold=True,
                      reason='full cap reservation, terminal execution or G cleanup requires owner inspection',
                      error=type(error).__name__)
        return report


def cap_mixed_contract(root, contract):
    """Check the frozen mixed collector separately from the original r2 runtime."""
    require(isinstance(contract, dict), 'Missing mixed runtime contract')
    attempt = contract.get('attempt')
    require(isinstance(attempt, str) and re.fullmatch(r'cap-budget-runtime-r[0-9]+-[0-9]{8}', attempt),
            'Mixed runtime attempt is not explicitly owned')
    evidence = exact(root / 'evidence' / attempt, root)
    work = exact(root / 'work' / attempt, root)
    inputs = read(evidence / 'inputs.json')
    build = read(evidence / 'build-result.json')
    pilot = read(evidence / 'pilot-result.json')
    equivalence = read(evidence / 'equivalence.json')
    backup = read(evidence / 'local-backup-receipt.json')
    manifest = read(evidence / 'delivery-manifest.json')
    source = inputs.get('source_sha')
    publication = inputs.get('instrumentation_source_sha')
    require(isinstance(source, str) and re.fullmatch('[0-9a-f]{40}', source)
            and source != CAP_FULL_SOURCE and isinstance(publication, str)
            and re.fullmatch('[0-9a-f]{40}', publication), 'Mixed actual Git source is not frozen')
    original = inputs.get('original_source_hashes', {})
    hashes = inputs.get('source_hashes', {})
    baseline = read(root / 'evidence/cap-runtime-recovery-r1-20261011/inputs.json')
    require(inputs.get('business_source_sha') == CAP_FULL_SOURCE and len(hashes) == len(original) == 372
            and baseline.get('source_sha') == CAP_FULL_SOURCE and baseline.get('source_hashes') == original
            and hashes.keys() == original.keys() and set(inputs.get('override_paths', [])) == set(CAP_MIXED_OVERRIDES)
            and {name for name in hashes if hashes[name] != original[name]} == set(CAP_MIXED_OVERRIDES)
            and inputs.get('original370_inputs_unchanged') is True
            and inputs.get('exact_two_overrides_match_instrumentation_Git_bytes') is True,
            'Mixed collector must preserve all 370 original business inputs')
    runtime = build.get('runtime_hashes', {})
    expected_names = set(CAP_DOMAIN_HASHES) | {
        'FantasyCard.Numerics', 'FantasyCard.Numerics.pdb', 'FantasyCard.Numerics.dll',
        'FantasyCard.Numerics.runtimeconfig.json', 'FantasyCard.Numerics.deps.json'}
    numerics = {name: value for name, value in runtime.items() if name.startswith('FantasyCard.Numerics')}
    require(build.get('ok') is True and build.get('source_sha') == source
            and build.get('business_source_sha') == CAP_FULL_SOURCE and set(runtime) == expected_names
            and all(runtime[name] == value for name, value in CAP_DOMAIN_HASHES.items())
            and build.get('domain_original_hashes') == CAP_DOMAIN_HASHES
            and build.get('domain_hashes_identical_to_original') is True
            and build.get('domain_regression_exact_56_passed') is True
            and build.get('source_inputs_unchanged') is True and build.get('owned_container_removed') is True
            and build.get('numerics_hashes_actual') == numerics
            and all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) for value in runtime.values())
            and runtime['FantasyCard.Numerics.dll'] != CAP_ORIGINAL_NUMERICS_DLL,
            'Mixed runtime lacks unchanged Domain and explicitly changed Numerics evidence')
    validations = pilot.get('validations', {})
    require(set(validations) == {'original', 'new-default', 'new-16g'}
            and all(row.get('ok') is True and row.get('encounters') == 6 and row.get('pairs') == 3
                    and len(row.get('negative_controls', [])) == 4
                    and all(control.get('rejected') is True for control in row['negative_controls'])
                    for row in validations.values())
            and all(len(validations[name].get('collector_negative_controls', [])) == 3
                    and all(row.get('rejected') is True for row in validations[name]['collector_negative_controls'])
                    for name in ('new-default', 'new-16g'))
            and pilot.get('owned_container_removed') is True
            and pilot.get('source_and_runtime_inputs_unchanged') is True,
            'Actual original, default and 16 GiB pilot sets are incomplete')
    require(pilot.get('ok') is True and pilot.get('equivalence_ok') is True
            and pilot.get('equivalence_json_sha256') == sha(evidence / 'equivalence.json')
            and equivalence.get('ok') is True and len(equivalence.get('comparisons', [])) == 2
            and all(row.get('ok') is True for row in equivalence['comparisons'])
            and len(equivalence.get('negative_controls', [])) == 4
            and all(row.get('rejected') is True for row in equivalence['negative_controls']),
            'Mixed collector native pilot equivalence is incomplete')
    flags = ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
             'inner_gzip_CRC_raw_SHA_counts_verified', 'pilot_equivalence_verified',
             'domain_hashes_identical_to_original', 'no_native_business_executed_locally')
    require(backup.get('ok') is True and all(backup.get(key) is True for key in flags)
            and backup.get('source_sha') == source and backup.get('business_source_sha') == CAP_FULL_SOURCE
            and backup.get('instrumentation_source_sha') == publication
            and backup.get('source_files_verified') == 372 and backup.get('runtime_files_verified') == 8
            and backup.get('runtime_identical_to_original') is False
            and backup.get('manifest_sha256') == sha(evidence / 'delivery-manifest.json')
            and backup.get('members') == backup.get('members_verified') == len(manifest['files'])
            and re.match(r'^G:[\\/]', backup.get('local_archive', ''), re.IGNORECASE)
            and re.match(r'^G:[\\/]', backup.get('local_directory', ''), re.IGNORECASE)
            and isinstance(backup.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', backup['sha256'])
            and type(backup.get('bytes')) is int and backup['bytes'] > 0,
            'Mixed runtime sources, build and pilot lack exact G backup')
    scratch = Path('/dev/shm') / ('pr13-' + attempt)
    members = {}
    for row in manifest['files']:
        member = row['path']
        require(isinstance(member, str), 'Nonstring mixed runtime member')
        parts = PurePosixPath(member).parts
        require(len(parts) >= 2 and not member.startswith('/') and '\\' not in member and ':' not in member
                and '..' not in parts and '.' not in parts and member not in members
                and PurePosixPath(*parts).as_posix() == member and type(row.get('bytes')) is int and row['bytes'] >= 0
                and isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'Unsafe/duplicate mixed runtime member')
        members[member] = row
        directory = {'metadata': evidence, 'persistent': work, 'passed-build-scratch': scratch}.get(parts[0])
        require(directory is not None and row.get('source') == str(directory.joinpath(*parts[1:])),
                'Mixed runtime G member escapes its exact owned attempt')
        if parts[0] == 'passed-build-scratch' and not scratch.exists():
            cleanup = read(evidence / 'passed-scratch-cleanup.json')
            require(cleanup.get('ok') is True and cleanup.get('attempt') == attempt
                    and cleanup.get('source_sha') == source and cleanup.get('passed_scratch_removed') == str(scratch)
                    and cleanup.get('manifest_sha256') == backup['manifest_sha256']
                    and cleanup.get('local_G_archive_sha256') == backup['sha256']
                    and cleanup.get('local_G_archive_bytes') == backup['bytes'],
                    'Missing passed build scratch lacks exact G cleanup proof')
    for name in ('inputs.json', 'build-result.json', 'pilot-result.json', 'equivalence.json'):
        require(members.get('metadata/' + name, {}).get('sha256') == sha(evidence / name),
                'Original G-backed mixed runtime metadata changed')
    require(all(members.get('persistent/source/' + name, {}).get('sha256') == value for name, value in hashes.items())
            and all(members.get('persistent/runtime/' + name, {}).get('sha256') == value for name, value in runtime.items()),
            'Mixed runtime G manifest must cover every original source and compiled runtime member')
    require({path.name: sha(path) for path in ordinary_files(work / 'runtime')} == runtime,
            'Mixed compiled runtime files changed')
    for name, expected in hashes.items():
        parts = PurePosixPath(name).parts
        require(parts and not name.startswith('/') and '\\' not in name and ':' not in name
                and '..' not in parts and '.' not in parts and PurePosixPath(*parts).as_posix() == name,
                'Unsafe mixed source input')
        path = work / 'source' / name
        require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(work / 'source')
                and sha(path) == expected, 'Mixed source input differs from frozen G evidence')
    expected = {'attempt': attempt, 'source_sha': source, 'business_source_sha': CAP_FULL_SOURCE,
                'instrumentation_source_sha': publication,
                'mixed_input_manifest_sha256': sha(evidence / 'inputs.json'),
                'collector_revision': CAP_MIXED_COLLECTOR, 'source_subset_files': 372,
                'original_business_files': 370, 'override_paths': list(CAP_MIXED_OVERRIDES),
                'runtime_hashes': runtime, 'domain_original_hashes': CAP_DOMAIN_HASHES,
                'domain_hashes_identical_to_original': True, 'runtime_path': str(work / 'runtime'),
                'source_path': str(work / 'source'), 'build_result_sha256': sha(evidence / 'build-result.json'),
                'pilot_result_sha256': sha(evidence / 'pilot-result.json'),
                'equivalence_json_sha256': sha(evidence / 'equivalence.json'),
                'G_backup_receipt_sha256': sha(evidence / 'local-backup-receipt.json'),
                'G_manifest_sha256': sha(evidence / 'delivery-manifest.json'),
                'runtime_identical_to_original': False, 'original_2068_directory_restored': False}
    require(contract == expected, 'Complete mixed runtime contract differs from actual retained evidence')
    return contract


def cap_mixed_cleaned(metadata, output, name, marker, contract):
    """Release only after independently checking retained original collector evidence."""
    source = contract['source_sha']
    result = read(metadata / 'result.json')
    prereg = read(metadata / 'preregistration.json')
    manifest_path = metadata / 'delivery-manifest.json'
    manifest = read(manifest_path)
    hero, group, element, level, block = name.split('-')
    block_index = int(block[1:])
    spec = {'unit': name, 'hero': hero, 'group': group, 'element': element, 'level': int(level[1:]),
            'block': block_index, 'seed_start': 440001 + block_index * 1000,
            'seed_end': 441000 + block_index * 1000, 'samples_per_arm': 1000, 'expected_encounters': 2000}
    provenance = {'source_sha': source, 'business_source_sha': CAP_FULL_SOURCE,
                  'instrumentation_source_sha': contract['instrumentation_source_sha'],
                  'mixed_input_manifest_sha256': contract['mixed_input_manifest_sha256'],
                  'collector_revision': CAP_MIXED_COLLECTOR, 'raw_unit_limit_bytes': marker['raw_unit_limit_bytes']}
    require(all(prereg.get(key) == value for key, value in spec.items())
            and all(all(document.get(key) == value for key, value in provenance.items())
                    for document in (prereg, result, manifest))
            and prereg.get('owner') == CAP_MIXED_OWNER and prereg.get('runtime_contract') == contract
            and prereg.get('persistent_output_budget_bytes') == CAP_MIXED_OUTPUT
            and prereg.get('native_raw_part_bytes') == 134217728
            and prereg.get('native_unit_raw_ceiling_bytes') == marker['raw_unit_limit_bytes']
            and prereg.get('raw_unit_limit_explicit') is True,
            'Mixed cap original seed, budget or provenance preregistration differs')
    require(result.get('ok') is True and result.get('attempt') == CAP_MIXED_OWNER and result.get('unit') == name
            and result.get('exit_code') == 0 and result.get('oom_killed') is False
            and result.get('compiled_mixed_runtime_unchanged') is True
            and result.get('source_subset_inputs_unchanged') is True
            and result.get('domain_hashes_identical_to_original') is True
            and result.get('runtime_identical_to_original') is False
            and result.get('numerics_runtime_identical_to_original') is False
            and result.get('owned_container_removed') is True and result.get('runtime_contract') == contract
            and result.get('main_acceptance_granted') is False and marker.get('result_ok') is True
            and marker.get('result_path') == str(metadata / 'result.json')
            and not (metadata / 'finalization-error.json').exists(), 'Mixed cap exact native execution is not successful')
    require(manifest.get('kind') == CAP_MIXED_GROUP and manifest.get('unit') == name
            and manifest.get('native_encounters') == 2000 and manifest.get('whole_task_accepted') is False
            and manifest.get('output_budget_bytes') == CAP_MIXED_OUTPUT
            and manifest.get('metadata_reserve_bytes') == METADATA_RESERVE
            and manifest.get('collection_complete') is True and manifest.get('files'),
            'Mixed cap delivery manifest identity, budget or scope differs')
    names = set()
    members = {}
    for row in manifest['files']:
        member = row['path']
        require(isinstance(member, str), 'Nonstring mixed cap member')
        parts = PurePosixPath(member).parts
        require(len(parts) >= 2 and not member.startswith('/') and '\\' not in member and ':' not in member
                and '..' not in parts and '.' not in parts and member not in names
                and member == PurePosixPath(*parts).as_posix(), 'Unsafe/duplicate mixed cap delivery member')
        names.add(member)
        members[member] = row
        if parts[0] == 'metadata':
            path = metadata.joinpath(*parts[1:])
            require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(metadata)
                    and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                    'Backed-up mixed cap execution metadata changed')
        else:
            require(len(parts) >= 3 and parts[:2] == ('outputs', name), 'Foreign mixed cap output member')
            path = output.joinpath(*parts[2:])
        require(str(path) == row['source'] and type(row['bytes']) is int and row['bytes'] >= 0
                and isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'Mixed cap delivery source/hash/size differs')
    require({'metadata/result.json', 'metadata/preregistration.json', 'metadata/collector-proof.json'} <= names,
            'Mixed cap manifest omitted original execution/collector evidence')
    proof = read(metadata / 'collector-proof.json')
    require(proof.get('kind') == 'cap-effective-r3-retained-collector-proof' and proof.get('unit') == name
            and proof.get('source_sha') == source and proof.get('business_source_sha') == CAP_FULL_SOURCE,
            'Retained original collector proof belongs to a different execution')
    for key, member in (('native_manifest_sha256', f'outputs/{name}/native/manifest.json'),
                        ('native_summary_sha256', f'outputs/{name}/native/summary.json'),
                        ('validation_sha256', f'outputs/{name}/validation.json')):
        require(member in members and proof.get(key) == members[member]['sha256'],
                'Retained collector proof is not anchored to original delivery member bytes')
    original, summary, validation = (proof[key] for key in ('native_manifest', 'native_summary', 'validation'))
    require(all(all(document.get(key) == value for key, value in provenance.items())
                for document in (original, summary, validation))
            and original.get('schema') == 'actual_cap_effective_experiment_v2'
            and original.get('collection_complete') is True and summary.get('collection_complete') is True
            and original.get('raw_unit_limit_explicit') is True and summary.get('raw_unit_limit_explicit') is True
            and validation.get('collector_metadata_complete') is True,
            'Original mixed collector provenance or completion differs')
    parts = summary.get('event_parts', [])
    require(parts and all(type(part.get('raw_bytes')) is int and 0 < part['raw_bytes'] <= 134217728
                        and type(part.get('events')) is int and part['events'] > 0
                        and part.get('path') == f'cap-events-{index:03}.jsonl.gz'
                        and isinstance(part.get('raw_sha256'), str) and re.fullmatch('[0-9a-f]{64}', part['raw_sha256'])
                        for index, part in enumerate(parts)),
            'Original mixed event parts do not obey the 128 MiB raw part bound')
    raw_bytes = sum(part['raw_bytes'] for part in parts)
    require(raw_bytes == original.get('event_raw_bytes') == summary.get('event_raw_bytes')
            == validation.get('event_raw_bytes') == manifest.get('event_raw_bytes')
            and raw_bytes <= marker['raw_unit_limit_bytes']
            and validation.get('original_two_GiB_budget_satisfied') == (raw_bytes <= 2 * 1024**3),
            'Actual sum of original event part raw bytes differs from declared budget')
    require(summary.get('passed') is True and summary.get('rows') == 2000 and summary.get('errors') == 0
            and summary.get('main_acceptance_granted') is False and validation.get('ok') is True
            and validation.get('encounters') == 2000 and validation.get('pairs') == 1000
            and validation.get('full_unit') is True and validation.get('main_acceptance_granted') is False
            and original.get('hero') == hero and original.get('group') == group and original.get('element') == element
            and original.get('equipment_level') == spec['level'] and original.get('block_index') == block_index
            and original.get('seed_start') == spec['seed_start'] and original.get('samples') == 1000
            and original.get('candidate_activation') is False, 'Original mixed native stratum/counts differ')
    for key, expected in (('negative_controls', {'wrong-resistance-cap', 'wrong-conversion-stage',
                                              'wrong-shield-overflow', 'candidate-policy-enabled'}),
                          ('collector_negative_controls', {'collector-declared-budget-tampered',
                                                           'collector-event-part-missing',
                                                           'collector-cumulative-budget-exceeded'})):
        controls = validation.get(key, [])
        require(len(controls) == len(expected) and {row.get('name') for row in controls} == expected
                and all(row.get('rejected') is True for row in controls), 'Mixed native negative controls incomplete')
    require(type(manifest.get('native_casts')) is int and manifest['native_casts'] >= 0
            and type(manifest.get('native_ticks')) is int and manifest['native_ticks'] >= 0
            and summary.get('actual_casts') == validation.get('actual_casts') == manifest['native_casts']
            and summary.get('actual_ticks') == validation.get('actual_ticks') == manifest['native_ticks']
            and sum(part['events'] for part in parts) == manifest['native_casts'] + manifest['native_ticks'],
            'Mixed native original cast/tick counts differ')
    backup = read(metadata / 'local-backup-receipt.json')
    cleanup = read(metadata / 'local-storage-cleanup.json')
    flags = ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
             'inner_gzip_CRC_raw_SHA_counts_verified', 'no_native_business_executed_locally')
    require(backup.get('ok') is True and backup.get('unit') == name
            and all(backup.get(key) == value for key, value in provenance.items())
            and backup.get('manifest_sha256') == sha(manifest_path)
            and backup.get('members') == backup.get('members_verified') == len(manifest['files'])
            and all(backup.get(key) is True for key in flags) and backup.get('raw_encounters_verified') == 2000
            and backup.get('actual_casts_verified') == manifest['native_casts']
            and backup.get('actual_ticks_verified') == manifest['native_ticks']
            and backup.get('raw_events_verified') == manifest['native_casts'] + manifest['native_ticks']
            and backup.get('event_raw_bytes_verified') == raw_bytes and backup.get('collector_metadata_complete') is True
            and backup.get('runtime_identical_to_original') is False
            and backup.get('domain_hashes_identical_to_original') is True and backup.get('runtime_contract') == contract
            and backup.get('whole_task_accepted') is False
            and re.match(r'^G:[\\/]', backup.get('local_archive', ''), re.IGNORECASE)
            and re.match(r'^G:[\\/]', backup.get('local_directory', ''), re.IGNORECASE)
            and isinstance(backup.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', backup['sha256'])
            and type(backup.get('bytes')) is int and backup['bytes'] > 0,
            'Mixed cap original G archive/raw evidence gate is incomplete')
    require(cleanup.get('ok') is True and cleanup.get('unit') == name and cleanup.get('source_sha') == source
            and cleanup.get('manifest_sha256') == backup['manifest_sha256']
            and cleanup.get('local_G_archive_sha256') == marker.get('local_G_archive_sha256') == backup['sha256']
            and cleanup.get('local_G_archive_bytes') == marker.get('local_G_archive_bytes') == backup['bytes']
            and cleanup.get('output_directory') == str(output) and marker.get('output_cleaned') is True
            and cleanup.get('cloud_raw_removed') is True and cleanup.get('source_runtime_and_metadata_retained') is True
            and cleanup.get('whole_task_accepted') is False and not output.exists() and not output.is_symlink(),
            'Mixed cap exact passed output cleanup is not verified')


def cap_mixed_resource_reservation(root):
    evidence = root / 'evidence' / CAP_MIXED_GROUP
    units = evidence / 'units'
    report = {'deferred': False, 'reservation_present': False, 'attempt': CAP_MIXED_GROUP,
              'G_backup_required_before_render': True, 'uncertain_hold': False,
              'cleaned_reservations_verified': 0}
    if not evidence.exists() and not evidence.is_symlink():
        return report
    try:
        exact(evidence, root)
        if not units.exists() and not units.is_symlink():
            return report
        exact(units, evidence)
        contract = None
        for metadata in sorted(units.iterdir()):
            report.update(reservation_present=True, deferred=True, unit=metadata.name)
            require(re.fullmatch(r'(Mage|Priest|Guardian)-(O1|O6|E1|BOSS)-(Fire|Wood|Earth|Metal|Water)-L(0|5)-B[012]',
                                 metadata.name), 'Foreign mixed cap reservation unit')
            exact(metadata, units)
            output = root / 'work' / CAP_MIXED_GROUP / metadata.name
            exact(output, root, exists=False)
            marker = read(metadata / 'resource-reservation.json')
            if contract is None:
                contract = cap_mixed_contract(root, marker.get('runtime_contract'))
                plan = read(evidence / 'plan.json')
                selection = read(evidence / 'runtime-selection.json')
                require(plan.get('kind') == CAP_MIXED_GROUP and plan.get('source_sha') == contract['source_sha']
                        and plan.get('business_source_sha') == CAP_FULL_SOURCE and plan.get('runtime_contract') == contract
                        and plan.get('collector_revision') == CAP_MIXED_COLLECTOR
                        and plan.get('native_units') == 360 and plan.get('expected_encounters') == 720000
                        and plan.get('samples_per_arm') == 1000
                        and selection.get('attempt') == contract['attempt']
                        and selection.get('source_sha') == contract['source_sha'],
                        'Mixed reservation differs from its frozen full experiment plan/runtime selection')
            name = CAP_MIXED_PREFIX + metadata.name.lower()
            raw_limit = marker.get('raw_unit_limit_bytes')
            require(marker.get('attempt') == CAP_MIXED_OWNER and marker.get('unit') == metadata.name
                    and marker.get('systemd_unit') == name and marker.get('output_root') == str(output)
                    and marker.get('source_sha') == contract['source_sha']
                    and marker.get('business_source_sha') == CAP_FULL_SOURCE
                    and marker.get('instrumentation_source_sha') == contract['instrumentation_source_sha']
                    and marker.get('mixed_input_manifest_sha256') == contract['mixed_input_manifest_sha256']
                    and marker.get('runtime_contract') == contract and marker.get('runtime_identical_to_original') is False
                    and marker.get('collector_revision') == CAP_MIXED_COLLECTOR and type(raw_limit) is int
                    and CAP_MIXED_RAW_MIN <= raw_limit <= CAP_MIXED_RAW_MAX
                    and marker.get('persistent_output_budget_bytes') == CAP_MIXED_OUTPUT
                    and marker.get('reserved_root_bytes') == CAP_MIXED_OUTPUT + METADATA_RESERVE,
                    'Mixed cap reservation identity, runtime provenance or budget differs')
            result = subprocess.run(['systemctl', 'show', name,
                                     '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'],
                                    capture_output=True, text=True, timeout=15)
            require(result.returncode == 0, 'Mixed cap exact unit could not be inspected')
            values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            require('MainPID' in values and 'ActiveState' in values, 'Incomplete mixed cap exact unit state')
            unit = {'unit': name, 'MainPID': int(values['MainPID']), 'ActiveState': values['ActiveState'],
                    'SubState': values.get('SubState'), 'LoadState': values.get('LoadState'),
                    'ExecMainStatus': int(values.get('ExecMainStatus', '0'))}
            report.update(systemd_unit=name, current_unit_state=unit, reservation_status=marker.get('status'))
            if marker.get('status') == 'Prepared':
                require(not live(unit) and marker.get('G_backup_verified') is False,
                        'Prepared mixed cap reservation has live or falsely verified native execution')
                report['reason'] = 'mixed cap reservation prepared; exact owner must finish or resolve it'
                return report
            if marker.get('status') == 'Active':
                boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
                require(type(marker.get('runner_pid')) is int and marker['runner_pid'] > 0
                        and marker.get('boot_id') == boot and marker['runner_pid'] == unit['MainPID']
                        and live(unit) and marker.get('G_backup_verified') is False,
                        'Mixed cap active boot/PID differs from exact live native unit')
                report['reason'] = 'mixed cap exact native unit is live; await original G backup and cleanup'
                return report
            require(marker.get('status') == 'Ended', 'Unknown mixed cap reservation state')
            terminal(unit)
            ended = read(metadata / 'result.json')
            require(marker.get('result_ok') is True and marker.get('result_path') == str(metadata / 'result.json')
                    and ended.get('ok') is True and ended.get('attempt') == CAP_MIXED_OWNER
                    and ended.get('unit') == metadata.name and ended.get('source_sha') == contract['source_sha']
                    and ended.get('exit_code') == 0 and ended.get('oom_killed') is False
                    and ended.get('compiled_mixed_runtime_unchanged') is True
                    and ended.get('source_subset_inputs_unchanged') is True
                    and ended.get('domain_hashes_identical_to_original') is True
                    and ended.get('runtime_identical_to_original') is False
                    and ended.get('owned_container_removed') is True and ended.get('runtime_contract') == contract
                    and ended.get('main_acceptance_granted') is False,
                    'Mixed cap ended reservation is failed or lacks exact successful native execution')
            if marker.get('G_backup_verified') is not True:
                report['reason'] = 'mixed cap unit ended; exact G backup and cleanup are still required'
                return report
            cap_mixed_cleaned(metadata, output, metadata.name, marker, contract)
            report['cleaned_reservations_verified'] += 1
        no_active_bind(root / 'work' / CAP_MIXED_GROUP)
        report.update(deferred=False, reason='all mixed cap reservations have exact G backup and output cleanup')
        return report
    except Exception as error:
        report.update(deferred=True, uncertain_hold=True,
                      reason='mixed cap reservation, runtime provenance, native terminal or G cleanup requires owner inspection',
                      error=type(error).__name__)
        return report


def resource_status(root):
    reservation = cap_resource_reservation(root)
    if reservation['deferred']:
        return reservation
    full_reservation = cap_full_resource_reservation(root)
    if full_reservation['deferred']:
        return full_reservation
    mixed_reservation = cap_mixed_resource_reservation(root)
    if mixed_reservation['deferred']:
        return mixed_reservation
    memory = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                      if line.startswith('MemAvailable:'))) * 1024
    disk = os.statvfs(root)
    memory_required = 500000000 + RENDER_MEMORY
    disk_required = .15 * disk.f_blocks * disk.f_frsize + OUTPUT_LIMIT + METADATA_RESERVE
    available = disk.f_bavail * disk.f_frsize
    deferred = memory < memory_required or available < disk_required
    return {'deferred': deferred, 'uncertain_hold': False, 'cap_reservation': reservation,
            'cap_full_reservation': full_reservation,
            'cap_mixed_reservation': mixed_reservation,
            'memory_available_bytes': memory, 'memory_required_bytes': memory_required,
            'root_free_bytes': available, 'root_free_required_bytes': int(disk_required),
            'reason': ('renderer output/metadata and 500 MB memory reserves unavailable; no startup created'
                       if deferred else 'renderer startup resource reserves available')}


def defer_launch(evidence, work, plan, resources, pending):
    report = status(evidence, work, plan)
    report.update(action='launch-next', launch_deferred_resources=True,
                  resource_deferred=resources, reason=resources['reason'], no_startup_created=True,
                  pending_segment=pending['id'])
    return report


def status(evidence, work, plan, segment=None):
    current_path = evidence / 'current-segment.json'
    current = read(current_path) if current_path.exists() else None
    if segment is None:
        segment = current
    result = {'ok': True, 'action': 'status', 'render_source_sha': plan['render_source_sha'],
              'required_segments': len(plan['segments']), 'required_rows': plan['all_required_rows'],
              'required_PNGs': plan['all_required_PNGs'],
              'completed_segments': sum((evidence / s['id'] / 'result.json').exists() for s in plan['segments']),
              'cleanup_receipts_present': sum((evidence / s['id'] / 'local-storage-cleanup.json').exists() for s in plan['segments']),
              'whole_task_accepted': False}
    result['resource_deferred'] = resource_status(evidence.parents[1])
    hold = evidence / 'scheduling-hold.json'
    if hold.exists() or hold.is_symlink():
        record = read(hold)
        require(record.get('active') is True and record.get('whole_task_accepted') is False,
                'Unresolved scheduling hold requires inspection')
        result['scheduling_hold'] = record
    if segment is not None:
        require(segment in plan['segments'], 'Current segment is not in frozen plan')
        metadata = evidence / segment['id']
        output = work / segment['id']
        result.update(segment=segment, unit=unit_status(segment))
        result['state'] = 'native_live' if live(result['unit']) else 'terminal_or_not_started'
        if (metadata / 'result.json').exists():
            data = read(metadata / 'result.json')
            result['result_ok'] = data.get('ok')
            result['shutdown_resources_clean'] = data.get('shutdown_resources_clean')
        checkpoint = output / segment['case'] / 'checkpoint.json'
        if checkpoint.exists():
            data = read(checkpoint)
            result['rows'] = data.get('rows')
            result['last_passed'] = data.get('last', {}).get('passed')
        result['local_G_receipt_present'] = (metadata / 'local-backup-receipt.json').exists()
        result['local_cleanup_receipt_present'] = (metadata / 'local-storage-cleanup.json').exists()
        if (metadata / 'startup.json').exists():
            result['startup_state'] = read(metadata / 'startup.json').get('state')
    return result


def prepare_delivery(evidence, work, plan, segment):
    metadata = exact(evidence / segment['id'], evidence)
    output = exact(work / segment['id'], work)
    state = unit_status(segment)
    if live(state):
        return status(evidence, work, plan, segment)
    terminal(state)
    successful(metadata, output, segment, plan)
    path = metadata / 'delivery-manifest.json'
    if path.exists():
        manifest = read(path)
        require(manifest['segment'] == segment, 'Existing delivery manifest has different segment')
        manifest_validate(metadata, output, manifest)
    else:
        manifest = {'segment': segment, 'files': manifest_files(metadata, output)}
        write(path, manifest)
    return {'ok': True, 'action': 'prepare-delivery', 'segment': segment['id'],
            'manifest': str(path), 'manifest_sha256': sha(path), 'members': len(manifest['files']),
            'member_bytes': sum(row['bytes'] for row in manifest['files']),
            'cloud_archive_created': False, 'whole_task_accepted': False}


def cleanup(evidence, work, plan, segment, backup_path):
    metadata = exact(evidence / segment['id'], evidence)
    output = exact(work / segment['id'], work, exists=False)
    state = unit_status(segment)
    if live(state):
        return status(evidence, work, plan, segment)
    terminal(state)
    if (metadata / 'local-storage-cleanup.json').exists():
        return {'ok': True, 'action': 'cleanup', 'already_cleaned': True,
                'cleanup': cleaned(metadata, output, segment, plan)}
    require(backup_path is not None, 'Upload exact verified G receipt before cleanup')
    receipt = read(backup_path)
    manifest = read(metadata / 'delivery-manifest.json')
    require(manifest['segment'] == segment, 'Cleanup delivery segment mismatch')
    manifest_paths(metadata, output, manifest)
    backup_validate(receipt, metadata, manifest, segment, plan)
    result = read(metadata / 'result.json')
    require(result.get('ok') is True and result.get('shutdown_resources_clean') is True
            and result.get('source_sha') == plan['render_source_sha'], 'Passed source/result evidence changed')
    intent_path = metadata / 'cleanup-intent.json'
    anchor = {'segment': segment['id'], 'output_directory': str(output),
              'manifest_sha256': receipt['manifest_sha256'], 'local_G_archive_sha256': receipt['sha256'],
              'backup_receipt_sha256': sha(backup_path), 'render_source_sha': plan['render_source_sha']}
    if intent_path.exists():
        require(read(intent_path) == anchor, 'Interrupted cleanup anchor differs; preserve remaining originals')
        # A prior verified deletion may have been interrupted. Check every
        # remaining member against that same manifest; never synthesize results.
        expected = {row['source']: row for row in manifest['files'] if row['path'].startswith('outputs/')}
        if output.exists():
            for path in ordinary_files(output):
                row = expected.get(str(path))
                require(row is not None and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                        'Remaining interrupted-cleanup output differs from G backup')
        for row in manifest['files']:
            if row['path'].startswith('metadata/'):
                path = Path(row['source'])
                require(path.is_file() and not path.is_symlink() and path.stat().st_size == row['bytes']
                        and sha(path) == row['sha256'], 'Metadata changed during interrupted cleanup')
    else:
        successful(metadata, output, segment, plan)
        manifest_validate(metadata, output, manifest)
    destination = metadata / 'local-backup-receipt.json'
    if destination.exists():
        require(read(destination) == receipt, 'Existing G receipt differs; preserve it')
    else:
        write(destination, receipt)
    no_active_bind(output)
    terminal(unit_status(segment))
    if not intent_path.exists():
        write(intent_path, anchor)
    before = os.statvfs(work)
    output_bytes = sum(row['bytes'] for row in manifest['files'] if row['path'].startswith('outputs/'))
    if output.exists():
        exact(output, work)
        shutil.rmtree(output)
    after = os.statvfs(work)
    cleanup_receipt = {'ok': True, 'segment': segment['id'], 'render_source_sha': plan['render_source_sha'],
        'native_source_sha': NATIVE_SOURCE, 'output_directory': str(output),
        'manifest_sha256': receipt['manifest_sha256'], 'local_G_archive_sha256': receipt['sha256'],
        'local_G_archive_bytes': receipt['bytes'], 'members_verified': receipt['members_verified'],
        'passed_output_logical_bytes_removed': output_bytes,
        'root_disk_bytes_reclaimed': (after.f_bavail - before.f_bavail) * after.f_frsize,
        'source_and_metadata_retained': True, 'failed_originals_retained': True,
        'production_unchanged': True, 'whole_task_accepted': False}
    write(metadata / 'local-storage-cleanup.json', cleanup_receipt)
    return {'ok': True, 'action': 'cleanup', 'cleanup': cleanup_receipt}


def launch_next(root, evidence, work, plan):
    hold = evidence / 'scheduling-hold.json'
    if hold.exists():
        record = read(hold)
        require(record.get('active') is True and record.get('whole_task_accepted') is False,
                'Unresolved scheduling hold requires inspection')
        report = status(evidence, work, plan)
        report.update(action='launch-next', launch_suppressed=True,
                      reason='explicit evidence scheduling hold; existing native work is preserved')
        return report
    pending = None
    for segment in plan['segments']:
        metadata = evidence / segment['id']
        output = work / segment['id']
        if (metadata / 'local-storage-cleanup.json').exists():
            cleaned(metadata, output, segment, plan)
            continue
        if metadata.exists() or output.exists():
            report = status(evidence, work, plan, segment)
            report['launch_suppressed'] = True
            report['reason'] = 'existing exact segment requires observation, backup or recovery; never relaunch automatically'
            return report
        pending = segment
        break
    if pending is None:
        return {'ok': True, 'action': 'launch-next', 'all_required_fixture_segments_cleaned': True,
                'required_segments': len(plan['segments']), 'required_rows': plan['all_required_rows'],
                'required_PNGs': plan['all_required_PNGs'], 'whole_task_accepted': False}
    resources = resource_status(root)
    if resources['deferred']:
        return defer_launch(evidence, work, plan, resources, pending)
    state = unit_status(pending)
    require(not live(state) and state.get('LoadState') == 'not-found', 'Existing unit name must not be relaunched')
    current = evidence / 'current-segment.json'
    if current.exists():
        prior = read(current)
        require(prior in plan['segments'], 'Foreign current segment')
        require(plan['segments'].index(prior) < plan['segments'].index(pending), 'Current launch state is unresolved')
        cleaned(evidence / prior['id'], work / prior['id'], prior, plan)
    original = subprocess.run(['systemctl', 'show', 'pr13-pool-capacity-render-full-guardian8-t02',
                               '--property=MainPID,ActiveState'], capture_output=True, text=True, timeout=15)
    values = dict(line.split('=', 1) for line in original.stdout.splitlines() if '=' in line)
    require(original.returncode == 0 and values.get('MainPID') == '0'
            and values.get('ActiveState') not in ('active', 'activating'), 'Original full render unit is still live or unverified')
    resources = resource_status(root)
    if resources['deferred']:
        return defer_launch(evidence, work, plan, resources, pending)
    shared = exact(evidence / 'shared-source', evidence)
    hashes = read(evidence / 'shared-inputs.json')
    for name, expected in hashes.items():
        require(isinstance(name, str) and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                'Invalid frozen source input path')
        path = shared / name
        require(path.resolve(strict=True).is_relative_to(shared) and path.is_file() and sha(path) == expected,
                'Shared source no longer matches frozen input manifest')
    metadata = exact(evidence / pending['id'], evidence, exists=False)
    output = exact(work / pending['id'], work, exists=False)
    resources = resource_status(root)
    if resources['deferred']:
        return defer_launch(evidence, work, plan, resources, pending)
    metadata.mkdir()
    startup = {'state': 'preparing', 'segment': pending, 'unit': state['unit'],
               'render_source_sha': plan['render_source_sha'], 'created_at_unix': time.time(),
               'retry_launch_forbidden': True, 'whole_task_accepted': False}
    write(metadata / 'startup.json', startup)
    output.mkdir()
    source = metadata / 'source'
    shutil.copytree(shared, source, copy_function=os.link, symlinks=True)
    scene = 'client/tests/pr13_pool_segment.tscn'
    scene_path = source / scene
    if scene_path.exists() or scene_path.is_symlink():
        require(scene_path.is_file() and not scene_path.is_symlink(), 'Shared scene is not an ordinary file')
        scene_path.unlink()  # Never overwrite a hardlinked previous segment scene.
    text = ('[gd_scene load_steps=3 format=3]\n'
            '[ext_resource type="Script" path="res://tests/pr13_pool_capacity_render.gd" id="1"]\n'
            '[ext_resource type="PackedScene" path="res://main.tscn" id="2"]\n'
            '[node name="PoolCapacitySegment" type="Node"]\nscript = ExtResource("1")\npool_probe = false\n'
            f'pool_hero = "{pending["hero"]}"\npool_capacity = {pending["capacity"]}\n'
            f'pool_case = "{pending["case"]}"\npool_language = "{pending["language"]}"\n'
            '[node name="UI" parent="." instance=ExtResource("2")]\n')
    scene_path.write_bytes(text.encode('utf-8'))
    hashes[scene] = sha(scene_path)
    write(metadata / 'inputs.json', hashes)
    prereg = pending | {'render_source_sha': plan['render_source_sha'], 'native_source_sha': NATIVE_SOURCE,
            'case_id': pending['case'], 'scene': 'res://tests/pr13_pool_segment.tscn',
            'memory_floor_bytes': 500000000, 'root_disk_floor_ratio': .15,
            'RAM_output_limit_bytes': OUTPUT_LIMIT, 'deadline_seconds': 900,
            'fixture_matrix_only': True, 'authenticated_account_multigame_cycles_not_claimed': True,
            'whole_task_accepted': False}
    write(metadata / 'preregistration.json', prereg)
    write(current, pending)
    startup['state'] = 'launch_requested'
    write(metadata / 'startup.json', startup)
    try:
        result = subprocess.run(['sudo', '-n', 'systemd-run', '--unit=' + state['unit'].removesuffix('.service'),
                                 '--property=User=ubuntu', '--property=Type=exec',
                                 '/usr/bin/python3', str(evidence / 'run.py'), pending['id']],
                                capture_output=True, text=True, timeout=20)
        startup['dispatch_returncode'] = result.returncode
        startup['state'] = 'dispatch_observed' if result.returncode == 0 else 'dispatch_failed_requires_inspection'
    except subprocess.TimeoutExpired:
        startup['state'] = 'dispatch_observation_timeout_requires_inspection'
    write(metadata / 'startup.json', startup)
    report = status(evidence, work, plan, pending)
    report.update(action='launch-next', dispatch_state=startup['state'], whole_task_accepted=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--action', choices=('status', 'prepare-delivery', 'cleanup', 'launch-next'), required=True)
    parser.add_argument('--segment', help='Defaults to exact current-segment')
    parser.add_argument('--backup-receipt', type=Path, help='Root-uploaded verified G receipt, cleanup only')
    args = parser.parse_args()
    root = args.root
    require(root == DEFAULT_ROOT and root.resolve(strict=True) == root, 'Only exact authorized cloud acceptance root is supported')
    evidence = exact(root / 'evidence' / GROUP, root)
    work = exact(root / 'work' / GROUP, root)
    plan = segment_plan(evidence)
    segment = None
    if args.segment is not None:
        matches = [s for s in plan['segments'] if s['id'] == args.segment]
        require(len(matches) == 1, 'Unknown exact segment')
        segment = matches[0]
    if args.action == 'status':
        print(json.dumps(status(evidence, work, plan, segment)))
        return 0
    lock_path = evidence / '.controller.lock'
    shared_lock_path = root / 'evidence' / 'shared-resource-coordination.lock'
    require(not lock_path.is_symlink() and not shared_lock_path.is_symlink(), 'Linked controller/coordination lock')
    # All cap/render mutators acquire the shared lock first. The queue lock is
    # always second, so independent transports cannot race a new reservation.
    with shared_lock_path.open('a+b') as coordination, lock_path.open('a+b') as lock:
        try:
            fcntl.flock(coordination.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'ok': True, 'action': 'status', 'controller_busy': True, 'launch_suppressed': True}))
            return 0
        if args.action == 'launch-next':
            result = launch_next(root, evidence, work, plan)
        else:
            if segment is None:
                segment = read(evidence / 'current-segment.json')
                require(segment in plan['segments'], 'Foreign current segment')
            if args.action == 'prepare-delivery':
                result = prepare_delivery(evidence, work, plan, segment)
            else:
                result = cleanup(evidence, work, plan, segment, args.backup_receipt)
        print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
