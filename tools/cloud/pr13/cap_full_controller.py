"""Persistent cloud continuation of the frozen 360-unit B08.4 experiment.

The local-adoption phase performs file/receipt checks only. All native execution
is restricted to the Tencent host. An observation error never launches a second
job. Passed raw files are removed only after an exact G archive receipt; failed
raw files and the original 88-unit execution metadata are retained.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time
import urllib.request


ROOT = Path('/home/ubuntu/pr13-acceptance-20261009')
GROUP = 'cap-experiment-full-r2'
OWNER = 'pr13-' + GROUP
PREFIX = 'pr13-cap-full-r2-'
SOURCE = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
IMAGE = 'sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f'
RUNTIME_ATTEMPT = 'cap-runtime-recovery-r1-20261011'
RECOVERY_ATTEMPT = 'cap-missing-raw-recovery-r1'
RECOVERY_UNIT = 'Mage-E1-Water-L5-B0'
DEFAULT_OUTPUT_BUDGET = 96 * 1024**2
METADATA_RESERVE = 16 * 1024**2
RAW_PART_BYTES = 134217728
NATIVE_RAW_CEILING = 2147483648
MEMORY_LIMIT = 950 * 1024**2
MEMORY_FLOOR = 500000000
MONITOR = '2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
MUTABLE = {'delivery-manifest.json', 'local-backup-receipt.json', 'local-storage-cleanup.json',
           'resource-reservation.json', 'cleanup-intent.json'}
RUNTIME_HASHES = {
    'FantasyCard.Numerics.pdb': 'c54f071eb83687f4c0e56e555445df55db10d5bf861b264a47397ac628d1cbbb',
    'FantasyCard.Numerics.dll': 'cb9d50683a13957eeeb442824d26b06c209356e61a0289c2dc9fe9988a68c0df',
    'FantasyCard.Numerics.runtimeconfig.json': '6eaff27a497447817e02c096da9afb530324590c005c1c011cd87bf2669f9dfd',
    'FantasyCard.Numerics.deps.json': '3f2ef034feee6d02a18bce64a2a55c898c76b29bee8748fc912ca781f8e6dc92',
    'FantasyCard.Numerics': '31792193aae65a9a253370df35bd434f0c6cf5616e269f088c4a1cd5df728616',
    'FantasyCard.Domain.pdb': '986c5b1be4366ef9e91a70c671a210d3bd2b53f72fcb53be7e1088433a80a7e5',
    'FantasyCard.Domain.dll': '6e8650494db8e95dbf6a47af0eaf880a119bc36f348a9aaa9cd9437ca969249a',
    'FantasyCard.Domain.deps.json': '84049a6e2e274b4fd62887cce60fbf77aeeee5336c87f7d5150d602fb887a553',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    hashed = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            hashed.update(block)
    return hashed.hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing or linked metadata: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value, overwrite=False):
    require(overwrite or not path.exists(), 'Existing evidence cannot be overwritten: ' + str(path))
    temporary = path.with_name(path.name + '.controller-tmp')
    require(not temporary.exists(), 'Preserve interrupted metadata write')
    payload = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    with temporary.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def matrix():
    units = []
    for hero, group, element, level, block in itertools.product(
            ('Mage', 'Priest', 'Guardian'), ('O1', 'O6', 'E1', 'BOSS'),
            ('Fire', 'Wood', 'Earth', 'Metal', 'Water'), (0, 5), range(3)):
        units.append({'unit': f'{hero}-{group}-{element}-L{level}-B{block}',
                      'hero': hero, 'group': group, 'element': element, 'level': level, 'block': block,
                      'seed_start': 440001 + block * 1000, 'seed_end': 441000 + block * 1000,
                      'samples_per_arm': 1000, 'expected_encounters': 2000})
    return units


def identity(name):
    matches = [entry for entry in matrix() if entry['unit'] == name]
    require(len(matches) == 1, 'Unit outside frozen 360-unit matrix')
    return matches[0]


def host(root):
    require(os.name != 'nt' and root == ROOT and root.resolve(strict=True) == root,
            'Native/controller mutation must run on the exact Tencent cloud root')


def paths(root, name=None):
    evidence, raw = root / 'evidence' / GROUP, root / 'work' / GROUP
    return (evidence, raw) if name is None else (evidence / 'units' / identity(name)['unit'], raw / name)


def exact(path, root, exists=True):
    require(path.is_absolute() and path != root and path.is_relative_to(root)
            and not path.is_symlink() and path.resolve(strict=exists) == path,
            'Owned target is missing, linked or outside the exact cloud root')
    return path


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout)


def docker(*args):
    return command(['sudo', '-n', 'docker', *args])


def unit_status(name):
    unit = PREFIX + identity(name)['unit'].lower()
    result = command(['systemctl', 'show', unit,
                      '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'], 15)
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require('MainPID' in values and 'ActiveState' in values, 'Incomplete authoritative exact unit state')
    return {'unit': unit, 'MainPID': int(values['MainPID']), 'ActiveState': values['ActiveState'],
            'SubState': values.get('SubState'), 'LoadState': values.get('LoadState'),
            'ExecMainStatus': int(values.get('ExecMainStatus', '0'))}


def live(state):
    return state['MainPID'] != 0 or state['ActiveState'] in ('active', 'activating', 'deactivating', 'reloading')


def terminal(state):
    require(not live(state) and state['MainPID'] == 0 and state['ExecMainStatus'] == 0,
            'Exact native unit must have ended successfully before delivery/cleanup')


def ordinary_files(root):
    require(root.is_dir() and not root.is_symlink(), 'Missing or linked evidence tree')
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            path = Path(current) / name
            require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root), 'Linked owned directory')
        for name in files:
            path = Path(current) / name
            require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(root),
                    'Linked or nonregular owned file')
            yield path


def g_path(value):
    return isinstance(value, str) and re.match(r'^G:[\\/]', value, re.I) is not None


def canonical_json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def local_adoption(local_root, destination):
    """Build explicit adoption from existing verified archives, without native tests."""
    require(not destination.exists(), 'Adoption evidence cannot be overwritten')
    entries = []
    for spec in matrix()[:87]:
        folder = local_root / 'cap-experiment-full-raw' / spec['unit']
        proof_path = folder / 'local-backup-receipt.json'
        cleanup_path = folder / 'cloud-cleanup-receipt.json'
        proof, cleanup = read(proof_path), read(cleanup_path)
        result_path = folder / spec['unit'] / 'result.json'
        result = read(result_path)
        archive = Path(proof['local_archive'])
        require(proof.get('ok') is True and proof.get('unit') == spec['unit']
                and proof.get('source_sha') == SOURCE and proof.get('gzip_CRC_SHA_counts_verified') is True
                and proof.get('members_verified') == proof.get('members') and proof.get('raw_encounters_verified') == 2000,
                'Original G receipt is incomplete: ' + spec['unit'])
        require(g_path(str(archive)) and archive.is_file() and archive.stat().st_size == proof['bytes']
                and digest(archive) == proof['sha256'], 'Original G archive SHA/size differs')
        require(cleanup.get('ok') is True and cleanup.get('unit') == spec['unit']
                and cleanup.get('local_G_verified') is True and cleanup.get('cloud_raw_removed') is True
                and cleanup.get('sha256') == proof['sha256'] and cleanup.get('bytes') == proof['bytes'],
                'Original cleanup does not match the existing G archive')
        require(result.get('ok') is True and result.get('unit') == spec['unit']
                and result.get('source_sha') == SOURCE and result.get('validation', {}).get('encounters') == 2000,
                'Original native execution result is incomplete')
        entries.append({'unit': spec['unit'], 'kind': 'original_G_verified',
                        'backup_receipt': proof, 'backup_receipt_sha256': digest(proof_path),
                        'cloud_cleanup': cleanup, 'cloud_cleanup_sha256': digest(cleanup_path),
                        'original_result_sha256': digest(result_path)})
    recovery_dir = local_root / 'cap-missing-raw-recovery-backup'
    recovery_proof = recovery_dir / 'local-backup-receipt.json'
    proof = read(recovery_proof)
    cleanup_path = local_root / 'cap-missing-raw-cloud-cleanup.json'
    cleanup = read(cleanup_path)
    result_path = recovery_dir / 'verified/metadata/result.json'
    result = read(result_path)
    archive = Path(proof['local_archive'])
    require(proof.get('ok') is True and proof.get('raw_encounters_verified') == 2000
            and proof.get('source_sha') == SOURCE and proof.get('replacement_evidence_only') is True
            and proof.get('original_result_preserved') is True and proof.get('runtime_identical_to_original') is True
            and proof.get('inner_gzip_CRC_raw_SHA_counts_verified') is True
            and proof.get('archive_gzip_CRC_verified') is True and proof.get('all_original_members_sha256_verified') is True,
            'Separate named raw recovery lacks exact G evidence')
    require(g_path(str(archive)) and archive.is_file() and archive.stat().st_size == proof['bytes']
            and digest(archive) == proof['sha256'], 'Recovery G archive differs')
    require(result.get('ok') is True and result.get('unit') == RECOVERY_UNIT
            and result.get('original_raw_missing') is True and result.get('original_seed_block_preserved') is True
            and result.get('expected_encounters') == 2000 and result.get('samples_per_arm') == 1000,
            'Recovery execution did not preserve the original seed/sample scope')
    require(cleanup.get('ok') is True and cleanup.get('unit') == RECOVERY_UNIT
            and cleanup.get('local_G_archive_sha256') == proof['sha256']
            and cleanup.get('local_G_archive_bytes') == proof['bytes'] and cleanup.get('original_result_preserved') is True,
            'Recovery cleanup is not anchored to the separate G archive')
    entries.append({'unit': RECOVERY_UNIT, 'kind': 'separate_named_missing_raw_recovery',
                    'attempt': RECOVERY_ATTEMPT, 'backup_receipt': proof,
                    'backup_receipt_sha256': digest(recovery_proof), 'cloud_cleanup': cleanup,
                    'cloud_cleanup_sha256': digest(cleanup_path), 'recovery_result_sha256': digest(result_path),
                    'original_result_sha256': result['original_result_sha256'],
                    'original_raw_still_missing': True, 'original_cleanup_not_fabricated': True})
    value = {'schema_version': 1, 'kind': GROUP + '-explicit-adoption', 'source_sha': SOURCE,
             'logical_verified_units': 88, 'original_G_verified_units': 87, 'named_raw_recovery_units': 1,
             'native_encounters_G_verified': 176000, 'entries': entries,
             'no_native_business_executed_locally': True, 'whole_task_accepted': False,
             'full_formal_pending': True}
    write(destination, value)
    return {'ok': True, 'adoption_file': str(destination), 'sha256': digest(destination),
            'logical_verified_units': 88, 'next_pending': matrix()[88], 'full_formal_pending': True}


def revise_adoption(previous_path, audit_path, destination):
    """Preserve the old G receipt SHA and separately bind observed cloud bytes."""
    previous = read(previous_path)
    audit = read(audit_path)
    parent_hash = digest(previous_path)
    require(previous.get('schema_version') == 1 and previous.get('kind') == GROUP + '-explicit-adoption'
            and previous.get('source_sha') == SOURCE and previous.get('logical_verified_units') == 88,
            'Revision requires the preserved initial 88-unit adoption')
    require(audit.get('ok') is True and audit.get('kind') == 'cap-full-r2-adoption-receipt-provenance-audit'
            and audit.get('adoption_input_sha256') == parent_hash and audit.get('original_G_units') == 87
            and audit.get('semantic_equal_units') == 87 and audit.get('cloud_mutation_performed') is False
            and audit.get('no_native_business_executed') is True,
            'Read-only 87-receipt cloud audit is not anchored to the initial adoption')
    rows = audit['rows']
    originals = [entry for entry in previous['entries'] if entry['kind'] == 'original_G_verified']
    require(len(rows) == 87 and [row['unit'] for row in rows] == [entry['unit'] for entry in originals],
            'Cloud receipt provenance audit does not cover the exact 87 original units')
    for entry, row in zip(originals, rows):
        require(row.get('semantic_equal') is True and not row.get('different_key_names')
                and not row.get('missing_remote_key_names') and not row.get('missing_local_key_names')
                and row.get('local_receipt_raw_sha256') == entry['cloud_cleanup_sha256']
                and row.get('canonical_json_sha256') == row.get('local_canonical_json_sha256')
                == canonical_json_sha(entry['cloud_cleanup'])
                and re.fullmatch('[0-9a-f]{64}', row.get('cloud_raw_sha256', '')) is not None,
                'Cloud receipt values/provenance differ; cannot revise this adoption')
        entry.update(cloud_cleanup_original_raw_sha256=row['cloud_raw_sha256'],
                     cloud_cleanup_local_receipt_raw_sha256=entry['cloud_cleanup_sha256'],
                     cloud_cleanup_semantic_json_sha256=row['canonical_json_sha256'],
                     cloud_cleanup_download_serialization_equal_to_original=row['raw_sha_equal'])
    previous.update(schema_version=2, parent_adoption_sha256=parent_hash,
                    parent_adoption_file=str(previous_path),
                    cloud_cleanup_provenance_audit_sha256=digest(audit_path),
                    cloud_cleanup_provenance_audit_file=str(audit_path),
                    original_cloud_cleanup_raw_hashes_observed=True,
                    local_downloaded_cleanup_raw_hashes_preserved=True,
                    receipt_serialization_difference_is_not_claimed_byte_identity=True)
    write(destination, previous)
    return {'ok': True, 'adoption_revision': 2, 'adoption_file': str(destination),
            'sha256': digest(destination), 'parent_adoption_sha256': parent_hash,
            'cloud_cleanup_semantically_identical_units': 87,
            'cloud_cleanup_byte_identical_units': audit['raw_sha_equal_units'],
            'original_G_verified_units': 87, 'logical_verified_units': 88,
            'no_native_business_executed_locally': True, 'whole_task_accepted': False}


def adoption_validate(root, adoption):
    require(adoption.get('kind') == GROUP + '-explicit-adoption' and adoption.get('source_sha') == SOURCE
            and adoption.get('logical_verified_units') == 88 and adoption.get('original_G_verified_units') == 87
            and adoption.get('named_raw_recovery_units') == 1 and adoption.get('whole_task_accepted') is False
            and adoption.get('no_native_business_executed_locally') is True,
            'Adoption scope/source/count changed')
    revision = adoption.get('schema_version')
    require(revision in (1, 2), 'Unknown adoption schema revision')
    if revision == 2:
        require(re.fullmatch('[0-9a-f]{64}', adoption.get('parent_adoption_sha256', '')) is not None
                and re.fullmatch('[0-9a-f]{64}', adoption.get('cloud_cleanup_provenance_audit_sha256', '')) is not None
                and adoption.get('original_cloud_cleanup_raw_hashes_observed') is True
                and adoption.get('local_downloaded_cleanup_raw_hashes_preserved') is True
                and adoption.get('receipt_serialization_difference_is_not_claimed_byte_identity') is True,
                'Revised adoption has lost its original/audit raw-byte anchors')
    require([entry.get('unit') for entry in adoption['entries']] == [row['unit'] for row in matrix()[:88]],
            'Adoption is not exactly the first 87 original units plus the named B0 recovery')
    old = root / 'evidence/cap-experiment-full'
    for entry in adoption['entries']:
        name = entry['unit']
        original = old / (name + '-result.json')
        result = read(original)
        require(digest(original) == entry['original_result_sha256'] and result.get('ok') is True
                and result.get('source_sha') == SOURCE and result.get('unit') == name,
                'Original cloud result differs from the G-adopted execution')
        proof = entry['backup_receipt']
        require(proof.get('ok') is True and proof.get('source_sha') == SOURCE
                and proof.get('raw_encounters_verified') == 2000 and g_path(proof.get('local_archive'))
                and re.fullmatch('[0-9a-f]{64}', proof.get('sha256', '')) is not None,
                'Adopted original G proof is invalid')
        if entry['kind'] == 'original_G_verified':
            path = old / (name + '-local-storage-cleanup.json')
            require(read(path) == entry['cloud_cleanup'], 'Existing original cloud cleanup values changed')
            if revision == 1:
                require(digest(path) == entry['cloud_cleanup_sha256'],
                        'Existing original cloud cleanup receipt bytes changed')
            else:
                require(digest(path) == entry.get('cloud_cleanup_original_raw_sha256')
                        and entry.get('cloud_cleanup_local_receipt_raw_sha256') == entry['cloud_cleanup_sha256']
                        and canonical_json_sha(read(path)) == entry.get('cloud_cleanup_semantic_json_sha256')
                        == canonical_json_sha(entry['cloud_cleanup'])
                        and entry.get('cloud_cleanup_download_serialization_equal_to_original')
                        == (digest(path) == entry['cloud_cleanup_sha256']),
                        'Original cloud bytes or preserved local receipt/canonical association changed')
            require(proof.get('gzip_CRC_SHA_counts_verified') is True
                    and entry['cloud_cleanup'].get('sha256') == proof['sha256'], 'Original G verification missing')
        else:
            require(name == RECOVERY_UNIT and entry['kind'] == 'separate_named_missing_raw_recovery'
                    and entry.get('original_raw_still_missing') is True
                    and entry.get('original_cleanup_not_fabricated') is True,
                    'Missing B0 raw must be a separate recovery, never a synthetic original cleanup')
            evidence = root / 'evidence' / RECOVERY_ATTEMPT
            require(digest(evidence / 'result.json') == entry['recovery_result_sha256']
                    and read(evidence / 'local-backup-receipt.json') == proof
                    and read(evidence / 'local-storage-cleanup.json') == entry['cloud_cleanup'],
                    'Separate recovery cloud/G evidence changed')
            require(read(evidence / 'result.json').get('original_result_preserved') is True
                    and proof.get('inner_gzip_CRC_raw_SHA_counts_verified') is True,
                    'Recovery provenance is incomplete')
    return adoption


def runtime_contract(root, verify_files=True):
    base = root / 'work' / RUNTIME_ATTEMPT
    evidence = root / 'evidence' / RUNTIME_ATTEMPT
    build, inputs = read(evidence / 'build-result.json'), read(evidence / 'inputs.json')
    require(build.get('ok') is True and build.get('runtime_hashes_identical_to_original') is True
            and build.get('domain_regression_exact_56_passed') is True,
            'Recovered native runtime has not passed the exact 56-regression gate')
    hashes = inputs.get('source_hashes', {})
    require(inputs.get('source_sha') == SOURCE and len(hashes) == 372,
            'Recovered source must retain the original exact 372-file subset')
    require(read(root / 'evidence/cap-experiment-full/runtime-hashes.json') == RUNTIME_HASHES,
            'Original eight runtime hashes changed')
    if verify_files:
        actual = {path.name: digest(path) for path in ordinary_files(base / 'runtime')}
        require(actual == RUNTIME_HASHES, 'Recovered runtime differs from any original runtime hash')
        for name, expected in hashes.items():
            parts = PurePosixPath(name).parts
            require(not name.startswith('/') and '..' not in parts and '\\' not in name,
                    'Unsafe source manifest path')
            path = base / 'source' / name
            require(path.resolve(strict=True).is_relative_to(base / 'source') and not path.is_symlink()
                    and digest(path) == expected, 'Recovered original source hash changed: ' + name)
    return {'source_sha': SOURCE, 'source_subset_files': 372, 'runtime_hashes': RUNTIME_HASHES,
            'runtime_path': str(base / 'runtime'), 'source_path': str(base / 'source'),
            'inputs_sha256': digest(evidence / 'inputs.json'),
            'build_result_sha256': digest(evidence / 'build-result.json'),
            'original_2068_directory_restored': False, 'runtime_identical_to_original': True}


def guard(root, metadata=None, output=None, budget=DEFAULT_OUTPUT_BUDGET, start=False):
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    stat = os.statvfs(root)
    headroom = int((stat.f_bavail - .15 * stat.f_blocks) * stat.f_frsize)
    used = sum(path.stat().st_size for path in ordinary_files(output)) if output and output.exists() else 0
    require(available >= MEMORY_FLOOR + (MEMORY_LIMIT if start else 0), 'memory safety floor')
    require(stat.f_bavail / stat.f_blocks >= .15, 'root disk safety floor')
    require(headroom >= METADATA_RESERVE + (budget if start else 0), 'root output/metadata reservation unavailable')
    require(used <= budget, 'persistent output budget exceeded; retained failed raw cannot pass')
    with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10) as response:
        require(response.status == 200, 'production health/ready failed')
    observation = {'at': time.time(), 'memory_available_bytes': available,
                   'root_free_ratio': stat.f_bavail / stat.f_blocks,
                   'headroom_above_15_percent_bytes': headroom, 'persistent_output_bytes': used,
                   'output_budget_bytes': budget, 'health_status': 200}
    if metadata:
        with (metadata / 'resources.jsonl').open('a') as stream:
            stream.write(json.dumps(observation) + '\n')
    return observation


def plan(root):
    evidence, _ = paths(root)
    value = read(evidence / 'plan.json')
    require(value.get('kind') == GROUP and value.get('source_sha') == SOURCE
            and value.get('units') == matrix() and value.get('native_units') == 360
            and value.get('expected_encounters') == 720000 and value.get('expected_pairs') == 360000
            and value.get('whole_task_accepted') is False, 'Frozen full experiment plan changed')
    require(value.get('runtime_contract') == runtime_contract(root, verify_files=False), 'Runtime provenance metadata changed')
    adoption = read(evidence / 'adoption.json')
    require(digest(evidence / 'adoption.json') == value['adoption_sha256'], 'Frozen adoption changed')
    adoption_validate(root, adoption)
    return value


def initialize(root, adoption_path):
    host(root)
    evidence, raw = paths(root)
    require(not raw.exists(), 'Existing continuation raw root cannot be initialized again')
    if evidence.exists():
        exact(evidence, root)
        require({path.name for path in evidence.iterdir()} <= {
                    'controller.py', 'adoption-input.json',
                    'controller-revision2.py', 'adoption-revision2-input.json'}
                and all(path.is_file() and not path.is_symlink() for path in evidence.iterdir()),
                'Existing continuation evidence cannot be initialized again')
    adoption = adoption_validate(root, read(adoption_path))
    contract = runtime_contract(root)
    guard(root)
    evidence.mkdir(exist_ok=True)
    (evidence / 'units').mkdir()
    raw.mkdir()
    write(evidence / 'adoption.json', adoption)
    value = {'schema_version': 1, 'kind': GROUP, 'source_sha': SOURCE, 'image_sha': IMAGE,
             'units': matrix(), 'native_units': 360, 'expected_encounters': 720000,
             'expected_pairs': 360000, 'samples_per_arm': 1000, 'runtime_contract': contract,
             'adoption_sha256': digest(evidence / 'adoption.json'), 'adopted_units': 88,
             'default_persistent_output_budget_bytes': DEFAULT_OUTPUT_BUDGET,
             'original_RAM_output_bytes': 536870912, 'native_raw_part_bytes': RAW_PART_BYTES,
             'native_unit_raw_ceiling_bytes': NATIVE_RAW_CEILING,
             'budget_adjustment': 'persistent 96 MiB operational ceiling; original native sample/seed/raw limits unchanged',
             'larger_future_unit_budget_state': 'DiagnosticPendingExplicitReservation',
             'root_metadata_reserve_bytes': METADATA_RESERVE,
             'memory_floor_bytes': MEMORY_FLOOR, 'container_memory_bytes': MEMORY_LIMIT,
             'disk_free_ratio': .15, 'native_deadline_seconds': 1100,
             'validation_deadline_seconds': 300, 'outer_deadline_seconds': 1200,
             'capacity_tests_deferred': True, 'human_experience_in_scope': False,
             'full_formal_pending': True, 'whole_task_accepted': False}
    write(evidence / 'plan.json', value)
    return {'ok': True, 'adopted_units': 88, 'logical_verified_units': 88,
            'remaining_units': 272, 'next_pending': matrix()[88], 'full_formal_pending': True}


def successful(metadata, output, spec):
    prereg = read(metadata / 'preregistration.json')
    require(all(prereg.get(key) == value for key, value in spec.items()), 'Unit preregistration matrix differs')
    result = read(metadata / 'result.json')
    require(result.get('ok') is True and result.get('unit') == spec['unit'] and result.get('source_sha') == SOURCE
            and result.get('exit_code') == 0 and result.get('oom_killed') is False
            and result.get('compiled_runtime_unchanged_and_identical_to_original') is True
            and result.get('source_subset_inputs_unchanged') is True and result.get('owned_container_removed') is True
            and result.get('main_acceptance_granted') is False, 'Failed/incomplete native unit is retained')
    if output.exists():
        require(read(output / 'result.json') == result, 'Raw/root result mismatch')
        native_success(output, spec)
    return result


def native_success(output, spec):
    summary = read(output / 'native/summary.json')
    validation = read(output / 'validation.json')
    original = read(output / 'native/manifest.json')
    require(summary.get('passed') is True and summary.get('source_sha') == SOURCE
            and summary.get('rows') == 2000 and summary.get('errors') == 0
            and summary.get('main_acceptance_granted') is False,
            'Native summary does not cover exactly 2000 encounters')
    require(validation.get('ok') is True and validation.get('source_sha') == SOURCE
            and validation.get('encounters') == 2000 and validation.get('pairs') == 1000
            and validation.get('full_unit') is True and validation.get('main_acceptance_granted') is False,
            'Independent validator scope differs')
    require(original.get('source_sha') == SOURCE and original.get('hero') == spec['hero']
            and original.get('group') == spec['group'] and original.get('element') == spec['element']
            and original.get('equipment_level') == spec['level'] and original.get('block_index') == spec['block']
            and original.get('seed_start') == spec['seed_start'] and original.get('samples') == 1000
            and original.get('candidate_activation') is False, 'Original native seed/stratum scope differs')
    expected_controls = {'wrong-resistance-cap', 'wrong-conversion-stage', 'wrong-shield-overflow', 'candidate-policy-enabled'}
    controls = validation.get('negative_controls', [])
    require(len(controls) == 4 and {row.get('name') for row in controls} == expected_controls
            and all(row.get('rejected') is True for row in controls), 'All four native controls must reject')
    require(summary['actual_casts'] == validation['actual_casts']
            and summary['actual_ticks'] == validation['actual_ticks'], 'Summary/validator original event counts differ')
    return summary, validation


def manifest_files(metadata, output, spec, budget):
    rows = []
    for prefix, directory in (('metadata', metadata), ('outputs/' + spec['unit'], output)):
        for path in sorted(ordinary_files(directory)):
            if prefix == 'metadata' and path.relative_to(metadata).as_posix() in MUTABLE:
                continue
            rows.append({'source': str(path), 'path': prefix + '/' + path.relative_to(directory).as_posix(),
                         'bytes': path.stat().st_size, 'sha256': digest(path)})
    require(sum(row['bytes'] for row in rows if row['path'].startswith('outputs/')) <= budget,
            'Output exceeds the registered operational budget; preserve failed originals')
    require(sum(row['bytes'] for row in rows if row['path'].startswith('metadata/')) <= METADATA_RESERVE,
            'Metadata exceeds the registered reserve')
    return sorted(rows, key=lambda row: row['path'])


def manifest_paths(metadata, output, manifest, spec):
    names = set()
    for row in manifest['files']:
        name = row['path']
        parts = PurePosixPath(name).parts
        require(not name.startswith('/') and '\\' not in name and ':' not in name and '..' not in parts
                and '.' not in parts and name == PurePosixPath(*parts).as_posix() and name not in names,
                'Unsafe or duplicate delivery path')
        names.add(name)
        if parts[0] == 'metadata':
            path = metadata.joinpath(*parts[1:])
        else:
            require(len(parts) >= 3 and parts[:2] == ('outputs', spec['unit']), 'Foreign output manifest member')
            path = output.joinpath(*parts[2:])
        require(str(path) == row['source'] and re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) is not None
                and isinstance(row['bytes'], int) and row['bytes'] >= 0, 'Manifest source/hash/size changed')


def backup_validate(receipt, metadata, manifest, spec):
    require(receipt.get('ok') is True and receipt.get('unit') == spec['unit'] and receipt.get('source_sha') == SOURCE
            and receipt.get('manifest_sha256') == digest(metadata / 'delivery-manifest.json')
            and receipt.get('members') == receipt.get('members_verified') == len(manifest['files']),
            'G receipt does not match this exact unit manifest')
    flags = ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
             'inner_gzip_CRC_raw_SHA_counts_verified', 'no_native_business_executed_locally')
    require(all(receipt.get(key) is True for key in flags) and receipt.get('raw_encounters_verified') == 2000
            and receipt.get('actual_casts_verified') == manifest['native_casts']
            and receipt.get('actual_ticks_verified') == manifest['native_ticks']
            and receipt.get('raw_events_verified') == manifest['native_casts'] + manifest['native_ticks'],
            'G CRC/hash/raw encounter/event verification incomplete')
    require(g_path(receipt.get('local_archive')) and g_path(receipt.get('local_directory'))
            and receipt.get('whole_task_accepted') is False
            and re.fullmatch('[0-9a-f]{64}', receipt.get('sha256', '')) is not None
            and isinstance(receipt.get('bytes'), int) and receipt['bytes'] > 0,
            'G archive identity or acceptance scope changed')


def cleaned(metadata, output, spec):
    manifest = read(metadata / 'delivery-manifest.json')
    require(manifest.get('unit') == spec['unit'] and manifest.get('source_sha') == SOURCE, 'Cleanup manifest source changed')
    manifest_paths(metadata, output, manifest, spec)
    receipt = read(metadata / 'local-backup-receipt.json')
    backup_validate(receipt, metadata, manifest, spec)
    cleanup = read(metadata / 'local-storage-cleanup.json')
    require(cleanup.get('ok') is True and cleanup.get('unit') == spec['unit']
            and cleanup.get('manifest_sha256') == receipt['manifest_sha256']
            and cleanup.get('local_G_archive_sha256') == receipt['sha256']
            and cleanup.get('local_G_archive_bytes') == receipt['bytes']
            and cleanup.get('output_directory') == str(output) and not output.exists(), 'Passed raw cleanup is not verified')
    successful(metadata, output, spec)
    for row in manifest['files']:
        if row['path'].startswith('metadata/'):
            path = Path(row['source'])
            require(path.is_file() and not path.is_symlink() and path.stat().st_size == row['bytes']
                    and digest(path) == row['sha256'], 'Backed-up execution metadata changed')
    terminal(unit_status(spec['unit']))
    return cleanup


def status(root):
    host(root)
    plan(root)
    completed = 88
    current = None
    next_pending = None
    for spec in matrix()[88:]:
        metadata, output = paths(root, spec['unit'])
        if not metadata.exists():
            next_pending = spec
            break
        if (metadata / 'local-storage-cleanup.json').exists():
            cleaned(metadata, output, spec)
            completed += 1
            continue
        state = unit_status(spec['unit'])
        current = {'unit': spec['unit'], 'stratum': spec, 'systemd_unit': state['unit'],
                   'unit_status': state, 'result': read(metadata / 'result.json') if (metadata / 'result.json').exists() else None,
                   'G_backup_verified': False, 'cleanup_verified': False,
                   'metadata_directory': str(metadata), 'output_directory': str(output),
                   'preregistration': read(metadata / 'preregistration.json'),
                   'output_budget_bytes': read(metadata / 'preregistration.json')['persistent_output_budget_bytes']}
        if (metadata / 'delivery-manifest.json').exists():
            current['manifest'] = str(metadata / 'delivery-manifest.json')
        if (metadata / 'local-backup-receipt.json').exists() and (metadata / 'delivery-manifest.json').exists():
            backup_validate(read(metadata / 'local-backup-receipt.json'), metadata,
                            read(metadata / 'delivery-manifest.json'), spec)
            current['G_backup_verified'] = True
        current['attention_required'] = not live(state) and current['result'] is None
        current['failed_raw_retained'] = bool(current['result'] and current['result'].get('ok') is not True)
        for filename in ('startup-failure.json', 'dispatch-observation-error.json', 'finalization-error.json'):
            if (metadata / filename).exists():
                current[filename.removesuffix('.json').replace('-', '_')] = read(metadata / filename)
                current['attention_required'] = True
        break
    native_completed = completed + int(bool(current and not live(current['unit_status'])
                                           and (current.get('result') or {}).get('ok') is True))
    return {'ok': True, 'kind': GROUP, 'source_sha': SOURCE, 'current': current,
            'next_pending': next_pending, 'adopted_units': 88, 'logical_verified_units': completed,
            'native_completed_units': native_completed,
            'total_units': 360, 'remaining_units': 360 - completed,
            'native_encounters_G_verified': completed * 2000,
            'whole_task_accepted': False, 'full_formal_pending': True,
            'no_automatic_restart': True}


def exclusive(root):
    units = command(['systemctl', 'list-units', '--state=running', '--no-legend',
                     'pr13-cap-*', 'pr13-pool-segment-*'], 15).stdout
    if units.strip():
        return {'reason': 'another exact cap/render systemd job is live', 'live_systemd_units': units.splitlines()}
    names = docker('ps', '--format', '{{.Names}}').stdout.splitlines()
    active = [name for name in names if name.startswith(('pr13-cap-', 'pr13-pool-segment-'))]
    if active:
        return {'reason': 'another cap/render container is live', 'live_container_names': active}
    return None


def launch_next(root, budget):
    host(root)
    require(isinstance(budget, int) and DEFAULT_OUTPUT_BUDGET <= budget <= 536870912,
            'Budget must be explicit and retain the original 512 MiB operational maximum')
    state = status(root)
    require(state['current'] is None, 'Current exact unit must finish G verification/cleanup; never duplicate or skip it')
    require(state['next_pending'] is not None, 'All native units already G-verified; formal aggregation remains')
    spec = state['next_pending']
    metadata, output = paths(root, spec['unit'])
    require(not metadata.exists() and not output.exists(), 'Existing native unit cannot be overwritten/restarted')
    deferred = exclusive(root)
    if deferred:
        return {'ok': True, 'launch_deferred_resources': True, 'no_startup_created': True,
                'resource_deferred': deferred, 'next_pending': spec, 'full_formal_pending': True}
    contract = runtime_contract(root)
    try:
        guard(root, budget=budget, start=True)
    except ValueError as error:
        if str(error) not in ('memory safety floor', 'root disk safety floor', 'root output/metadata reservation unavailable'):
            raise
        return {'ok': True, 'launch_deferred_resources': True, 'no_startup_created': True,
                'resource_deferred': {'reason': str(error)}, 'next_pending': spec, 'full_formal_pending': True}
    metadata.mkdir()
    prereg = dict(spec, source_sha=SOURCE, image_sha=IMAGE, owner=OWNER,
                  systemd_unit=PREFIX + spec['unit'].lower(), runtime_contract=contract,
                  runner_sha256=digest(Path(__file__)),
                  persistent_output_budget_bytes=budget, native_raw_part_bytes=RAW_PART_BYTES,
                  native_unit_raw_ceiling_bytes=NATIVE_RAW_CEILING, whole_task_accepted=False,
                  full_formal_pending=True, G_backup_verified=False,
                  budget_is_storage_guard_not_native_sample_or_raw_limit=True)
    write(metadata / 'preregistration.json', prereg)
    shutil.copyfile(Path(__file__), metadata / 'runner.py')
    marker = {'status': 'Prepared', 'attempt': OWNER, 'unit': spec['unit'],
              'systemd_unit': prereg['systemd_unit'], 'runner_pid': None,
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'reserved_root_bytes': budget + METADATA_RESERVE, 'output_root': str(output),
              'persistent_output_budget_bytes': budget, 'G_backup_verified': False,
              'source_sha': SOURCE, 'prepared_at': time.time()}
    write(metadata / 'resource-reservation.json', marker)
    write(metadata / 'launch-intent.json', {'unit': spec, 'systemd_unit': prereg['systemd_unit'],
                                           'at': time.time(), 'automatic_restart_permitted': False})
    try:
        started = command(['sudo', '-n', 'systemd-run', '--unit=' + prereg['systemd_unit'],
                           '--property=User=ubuntu', '/usr/bin/python3', str(metadata / 'runner.py'),
                           '_run-unit', '--unit', spec['unit']], 20)
        write(metadata / 'launch-response.json', {'ok': True, 'stdout': started.stdout,
                                                  'stderr': started.stderr, 'at': time.time()})
        observed = unit_status(spec['unit'])
        require(live(observed), 'Startup dispatch returned without an exact live unit; observe, never repeat')
    except Exception as error:
        # A transport/observation failure is not evidence that dispatch failed.
        # Preserve its prepared identity and require an exact read-only audit.
        write(metadata / 'dispatch-observation-error.json', {
            'ok': False, 'unit': spec['unit'], 'systemd_unit': prereg['systemd_unit'],
            'error': type(error).__name__, 'detail': str(error)[:4096],
            'dispatch_outcome_unproven': True, 'no_automatic_restart': True,
            'prepared_evidence_preserved': True, 'at': time.time()})
        raise
    return {'ok': True, 'started': True, 'dispatch_state': 'dispatch_observed',
            'unit_status': observed, 'stratum': spec, 'unit': spec['unit'],
            'systemd_unit': prereg['systemd_unit'], 'output_budget_bytes': budget,
            'remaining_units': state['remaining_units'], 'full_formal_pending': True,
            'observation_error_requires_exact_state_inspection_not_retry': True}


INNER = r'''import json,subprocess,sys,time
from pathlib import Path
commands=json.loads(sys.argv[1]);out=Path(sys.argv[2])
for index,command in enumerate(commands):
 (out/'phase.json').write_text(json.dumps({'phase':'native' if index==0 else 'validation','started':time.time()})+'\n')
 with (out/('native.log' if index==0 else 'validation.log')).open('w') as stream:
  process=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=1100 if index==0 else 300)
 if process.returncode:sys.exit(process.returncode)
'''


def owned_state(cid):
    value = json.loads(docker('inspect', cid).stdout)[0]
    require(value['Id'] == cid and value['Config']['Labels'].get('codex.owner') == OWNER,
            'Exact native container ownership changed')
    return value


def run_unit(root, name):
    host(root)
    spec = identity(name)
    metadata, output = paths(root, name)
    prereg = read(metadata / 'preregistration.json')
    require(all(prereg.get(key) == value for key, value in spec.items()), 'Frozen native stratum mismatch')
    require(prereg.get('source_sha') == SOURCE and prereg.get('image_sha') == IMAGE
            and prereg.get('owner') == OWNER and prereg.get('runner_sha256') == digest(Path(__file__)),
            'Native source/image/owner/runner mismatch')
    marker = read(metadata / 'resource-reservation.json')
    require(marker.get('status') == 'Prepared' and marker.get('attempt') == OWNER
            and marker.get('unit') == name and marker.get('systemd_unit') == PREFIX + name.lower()
            and marker.get('output_root') == str(output) and marker.get('source_sha') == SOURCE
            and marker.get('persistent_output_budget_bytes') == prereg['persistent_output_budget_bytes']
            and marker.get('reserved_root_bytes') == prereg['persistent_output_budget_bytes'] + METADATA_RESERVE
            and marker.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and marker.get('G_backup_verified') is False and not output.exists()
            and not (metadata / 'result.json').exists(), 'Prepared native unit cannot be restarted')
    exact(metadata, root)
    exact(output, root, exists=False)
    state = unit_status(name)
    require(live(state) and state['MainPID'] == os.getpid(), 'Runner PID differs from exact live systemd unit')
    marker.update(status='Active', runner_pid=os.getpid(), started_at=time.time(),
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    write(metadata / 'resource-reservation.json', marker, overwrite=True)
    cid = None
    result = dict(ok=False, attempt=OWNER, unit=name, source_sha=SOURCE, image_sha=IMAGE,
                  samples_per_arm=1000, expected_encounters=2000, seed_start=spec['seed_start'],
                  seed_end=spec['seed_end'], persistent_output_budget_bytes=prereg['persistent_output_budget_bytes'],
                  native_raw_part_bytes=RAW_PART_BYTES, native_unit_raw_ceiling_bytes=NATIVE_RAW_CEILING,
                  source_subset_files=372, original_2068_directory_restored=False,
                  G_backup_verified=False, whole_task_accepted=False, main_acceptance_granted=False,
                  full_formal_pending=True)
    try:
        contract = runtime_contract(root)
        require(contract == prereg['runtime_contract'], 'Runtime/source provenance differs from preregistration')
        budget = prereg['persistent_output_budget_bytes']
        guard(root, metadata, budget=budget, start=True)
        output.mkdir()
        commands = [
            ['dotnet', '/base/runtime/FantasyCard.Numerics.dll', '--cap-effective-experiment',
             '--source-sha', SOURCE, '--hero', spec['hero'], '--group', spec['group'],
             '--element', spec['element'], '--equipment-level', str(spec['level']),
             '--block-index', str(spec['block']), '--samples', '1000', '--output', '/raw/native'],
            ['python3', '/work/tools/pr13_cap_effective_experiment.py', '--input', '/raw/native',
             '--source-sha', SOURCE, '--output', '/raw/validation.json', '--controls']]
        cid = docker('create', '--name', prereg['systemd_unit'], '--label', 'codex.owner=' + OWNER,
                     '--memory', '950m', '--cpus', '1', '--network', 'none', '--user', '1000:1000',
                     '-v', contract['runtime_path'] + ':/base/runtime:ro',
                     '-v', contract['source_path'] + ':/work:ro', '-v', str(output) + ':/raw',
                     IMAGE, 'python3', '-c', INNER, json.dumps(commands), '/raw').stdout.strip()
        require(re.fullmatch('[0-9a-f]{64}', cid) is not None, 'Invalid native container identity')
        result['owned_container_id'] = cid
        write(metadata / 'container-created.json', {'container_id': cid, 'owner': OWNER,
                                                    'systemd_unit': prereg['systemd_unit'], 'at': time.time()})
        docker('start', cid)
        deadline = time.monotonic() + 1200
        while True:
            container = owned_state(cid)
            if not container['State']['Running']:
                break
            guard(root, metadata, output, budget)
            require(time.monotonic() < deadline, 'outer 1200 second deadline; retain failed raw')
            time.sleep(5)
        result.update(exit_code=container['State']['ExitCode'], oom_killed=container['State']['OOMKilled'])
        guard(root, metadata, output, budget)
        runtime_contract(root)
        result['compiled_runtime_unchanged_and_identical_to_original'] = True
        result['source_subset_inputs_unchanged'] = True
        if (output / 'validation.json').exists():
            result['validation'] = read(output / 'validation.json')
        if (output / 'native/summary.json').exists():
            summary = read(output / 'native/summary.json')
            result['native_summary'] = {key: summary.get(key) for key in ('passed', 'rows', 'actual_casts', 'actual_ticks', 'errors')}
        result['ok'] = (result.get('exit_code') == 0 and not result.get('oom_killed')
                        and result.get('native_summary', {}).get('passed') is True
                        and result.get('native_summary', {}).get('rows') == 2000
                        and result.get('validation', {}).get('ok') is True
                        and result.get('validation', {}).get('encounters') == 2000)
        if result['ok']:
            native_success(output, spec)
    except Exception as error:
        result.update(ok=False, error=type(error).__name__, detail=str(error), failed_raw_preserved=True)
    finally:
        try:
            if cid:
                container = owned_state(cid)
                if container['State']['Running']:
                    docker('stop', '--time', '5', cid)
                require(not owned_state(cid)['State']['Running'], 'Exact owned container has not stopped')
                docker('rm', '-v', cid)
                result['owned_container_removed'] = True
            result['persistent_output_bytes'] = sum(path.stat().st_size for path in ordinary_files(output)) if output.exists() else 0
            result['ok'] = result['ok'] and result.get('owned_container_removed') is True
            result['failed_raw_preserved'] = not result['ok']
            require(len(json.dumps(result).encode()) <= 128 * 1024, 'Result metadata too large; retained originals')
            write(metadata / 'result.json', result)
            if output.exists():
                write(output / 'result.json', result)
            if result['ok']:
                successful(metadata, output, spec)
            marker.update(status='Ended', ended_at=time.time(), result_path=str(metadata / 'result.json'),
                          result_ok=result['ok'], G_backup_verified=False)
            write(metadata / 'resource-reservation.json', marker, overwrite=True)
        except Exception as error:
            # Never replace immutable native evidence or restart after a partial finalization.
            write(metadata / 'finalization-error.json', {'ok': False, 'unit': name,
                  'error': type(error).__name__, 'detail': str(error), 'failed_raw_preserved': True,
                  'no_automatic_restart': True})
            result.update(ok=False, finalization_error=type(error).__name__, finalization_detail=str(error))
    return result


def startup_failure(root, name, error):
    """Record pre-native startup failure without replacing earlier evidence."""
    spec = identity(name)
    metadata, output = paths(root, name)
    exact(metadata, root)
    dispatch_record = (metadata / 'container-created.json').exists()
    failure = {'ok': False, 'unit': name, 'source_sha': SOURCE, 'error': type(error).__name__,
               'detail': str(error)[:4096],
               'native_dispatched': True if dispatch_record else (None if output.exists() else False),
               'native_dispatch_outcome_unproven': output.exists() and not dispatch_record,
               'no_automatic_restart': True, 'failed_raw_preserved': True,
               'whole_task_accepted': False, 'main_acceptance_granted': False,
               'full_formal_pending': True, 'at': time.time()}
    if not (metadata / 'startup-failure.json').exists():
        write(metadata / 'startup-failure.json', failure)
    if not (metadata / 'result.json').exists() and not output.exists():
        # Only a preflight failure reaches here; immutable prior native results
        # and any created raw tree are never replaced by this diagnostic.
        write(metadata / 'result.json', failure)
        marker_path = metadata / 'resource-reservation.json'
        marker = read(marker_path)
        if (marker.get('status') == 'Prepared' and marker.get('attempt') == OWNER
                and marker.get('unit') == spec['unit'] and marker.get('output_root') == str(output)):
            marker.update(status='Ended', ended_at=time.time(), result_path=str(metadata / 'result.json'),
                          result_ok=False, G_backup_verified=False, startup_failed=True)
            write(marker_path, marker, overwrite=True)
    return failure


def prepare_delivery(root, name):
    host(root)
    plan(root)
    spec = identity(name)
    metadata, output = paths(root, name)
    exact(metadata, root)
    exact(output, root)
    terminal(unit_status(name))
    result = successful(metadata, output, spec)
    marker = read(metadata / 'resource-reservation.json')
    require(marker.get('status') == 'Ended' and marker.get('result_ok') is True
            and marker.get('unit') == name and marker.get('attempt') == OWNER
            and not (metadata / 'finalization-error.json').exists(), 'Native finalization/reservation is incomplete')
    snapshot = metadata / 'resource-reservation-before-G.json'
    if not snapshot.exists():
        with snapshot.open('xb') as stream:
            stream.write((metadata / 'resource-reservation.json').read_bytes())
    budget = read(metadata / 'preregistration.json')['persistent_output_budget_bytes']
    summary = read(output / 'native/summary.json')
    value = {'schema_version': 1, 'kind': GROUP, 'unit': name, 'source_sha': SOURCE,
             'native_encounters': 2000, 'native_casts': summary['actual_casts'], 'native_ticks': summary['actual_ticks'],
             'output_budget_bytes': budget, 'metadata_reserve_bytes': METADATA_RESERVE,
             'whole_task_accepted': False, 'files': manifest_files(metadata, output, spec, budget)}
    path = metadata / 'delivery-manifest.json'
    if path.exists():
        require(read(path) == value, 'Existing delivery manifest differs; preserve originals')
    else:
        write(path, value)
    manifest_paths(metadata, output, value, spec)
    return {'ok': True, 'unit': name, 'source_sha': SOURCE, 'manifest': str(path),
            'manifest_sha256': digest(path), 'members': len(value['files']), 'files': value['files'],
            'bytes': sum(row['bytes'] for row in value['files']), 'output_budget_bytes': budget,
            'metadata_reserve_bytes': METADATA_RESERVE, 'cloud_archive_created': False,
            'whole_task_accepted': False}


def no_active_bind(output):
    ids = docker('ps', '-q').stdout.split()
    if not ids:
        return
    containers = json.loads(docker('inspect', *ids).stdout)
    for container in containers:
        for mount in container.get('Mounts', []):
            if mount.get('Type') != 'bind':
                continue
            source = Path(mount['Source']).resolve()
            if container['Id'] == MONITOR and source == Path('/') and mount.get('RW') is False:
                continue
            require(not (source == output or source.is_relative_to(output) or output.is_relative_to(source)),
                    'Passed raw output intersects an active container bind')


def cleanup(root, name, receipt_path):
    host(root)
    plan(root)
    spec = identity(name)
    metadata, output = paths(root, name)
    if (metadata / 'local-storage-cleanup.json').exists():
        return cleaned(metadata, output, spec)
    exact(metadata, root)
    exact(output, root)
    terminal(unit_status(name))
    successful(metadata, output, spec)
    manifest = read(metadata / 'delivery-manifest.json')
    manifest_paths(metadata, output, manifest, spec)
    require(manifest['files'] == manifest_files(metadata, output, spec, manifest['output_budget_bytes']),
            'Current output/metadata differs from archived original manifest')
    receipt = read(receipt_path)
    backup_validate(receipt, metadata, manifest, spec)
    destination = metadata / 'local-backup-receipt.json'
    if destination.exists():
        require(read(destination) == receipt, 'Preserve conflicting G receipt')
    else:
        write(destination, receipt)
    no_active_bind(output)
    guard(root)
    before = os.statvfs(root)
    allocated = sum(path.stat().st_blocks * 512 for path in ordinary_files(output))
    intent = {'unit': name, 'source_sha': SOURCE, 'output_directory': str(output),
              'manifest_sha256': receipt['manifest_sha256'], 'local_G_archive_sha256': receipt['sha256'],
              'local_G_archive_bytes': receipt['bytes'], 'at': time.time()}
    if (metadata / 'cleanup-intent.json').exists():
        require(all(read(metadata / 'cleanup-intent.json').get(key) == value
                    for key, value in intent.items() if key != 'at'), 'Conflicting cleanup intent')
    else:
        write(metadata / 'cleanup-intent.json', intent)
    # The exact absolute target and all ordinary members were verified above.
    shutil.rmtree(output)
    after = os.statvfs(root)
    result = dict(intent, ok=True, root_allocated_bytes_removed=allocated,
                  root_disk_bytes_reclaimed=(after.f_bavail - before.f_bavail) * after.f_frsize,
                  cloud_raw_removed=True, source_runtime_and_metadata_retained=True,
                  whole_task_accepted=False, full_formal_pending=True)
    write(metadata / 'local-storage-cleanup.json', result)
    marker = read(metadata / 'resource-reservation.json')
    marker.update(G_backup_verified=True, local_G_archive_sha256=receipt['sha256'],
                  local_G_archive_bytes=receipt['bytes'], output_cleaned=True)
    write(metadata / 'resource-reservation.json', marker, overwrite=True)
    return cleaned(metadata, output, spec)


def main():
    choices = ('local-adoption', 'revise-adoption', 'init', 'status', 'launch-next', '_run-unit', 'prepare-delivery', 'cleanup')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', nargs='?', choices=choices)
    parser.add_argument('--action', choices=choices)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--unit')
    parser.add_argument('--adoption-file', type=Path)
    parser.add_argument('--local-output-root', type=Path)
    parser.add_argument('--previous-adoption-file', type=Path)
    parser.add_argument('--provenance-audit-file', type=Path)
    parser.add_argument('--receipt-file', type=Path)
    parser.add_argument('--output-budget-bytes', type=int, default=DEFAULT_OUTPUT_BUDGET)
    args = parser.parse_args()
    phase = args.phase or args.action
    require(phase in choices and (not args.phase or not args.action or args.phase == args.action), 'Choose one exact controller phase')
    if phase == 'local-adoption':
        require(args.local_output_root is not None and args.adoption_file is not None, 'Local root/adoption file required')
        result = local_adoption(args.local_output_root, args.adoption_file)
    elif phase == 'revise-adoption':
        require(args.previous_adoption_file is not None and args.provenance_audit_file is not None
                and args.adoption_file is not None, 'Previous adoption/read-only audit/new destination required')
        result = revise_adoption(args.previous_adoption_file, args.provenance_audit_file, args.adoption_file)
    else:
        host(args.root)
        if phase == 'status':
            result = status(args.root)
        elif phase == '_run-unit':
            require(args.unit is not None, 'Exact unit required')
            try:
                result = run_unit(args.root, args.unit)
            except Exception as error:
                result = startup_failure(args.root, args.unit, error)
        else:
            import fcntl
            lock_path = args.root / 'evidence/shared-resource-coordination.lock'
            with lock_path.open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if phase == 'init':
                    require(args.adoption_file is not None, 'Explicit G adoption file required')
                    result = initialize(args.root, args.adoption_file)
                elif phase == 'launch-next':
                    result = launch_next(args.root, args.output_budget_bytes)
                elif phase == 'prepare-delivery':
                    require(args.unit is not None, 'Exact unit required')
                    result = prepare_delivery(args.root, args.unit)
                else:
                    require(args.unit is not None and args.receipt_file is not None, 'Exact unit/G receipt required')
                    result = cleanup(args.root, args.unit, args.receipt_file)
    print(json.dumps(result), flush=True)
    return 1 if result.get('ok') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
