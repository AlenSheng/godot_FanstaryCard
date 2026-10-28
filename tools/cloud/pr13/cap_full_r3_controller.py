"""Persistent cloud continuation of the frozen 360-unit B08.4 experiment.

The local-adoption phase performs file/receipt checks only. All native execution
is restricted to the Tencent host. An observation error never launches a second
job. Passed raw files are removed only after an exact G archive receipt; failed
raw files and all original 90-logical-unit / 91-execution evidence are retained.
"""
import argparse
import hashlib
import importlib.util
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
GROUP = 'cap-experiment-full-r3'
OWNER = 'pr13-' + GROUP
PREFIX = 'pr13-cap-full-r3-'
BUSINESS_SOURCE = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
SOURCE = None  # Set only from the verified immutable mixed runtime contract.
IMAGE = 'sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f'
RUNTIME_ATTEMPT = None
RECOVERY_ATTEMPT = 'cap-missing-raw-recovery-r1'
RECOVERY_UNIT = 'Mage-E1-Water-L5-B0'
DEFAULT_OUTPUT_BUDGET = 512 * 1024**2
METADATA_RESERVE = 16 * 1024**2
RAW_PART_BYTES = 134217728
NATIVE_RAW_CEILING = 16 * 1024**3
NATIVE_RAW_MAX = 32 * 1024**3
COLLECTOR_REVISION = 'cap-effective-raw-budget-v2'
ADOPTED_UNITS = 90
OVERRIDES = ('server/tools/FantasyCard.Numerics/CapEffectiveExperiment.cs',
             'tools/pr13_cap_effective_experiment.py')
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


def local_adoption(local_root, destination, previous_path):
    require(not destination.exists(), 'Explicit r3 adoption cannot be overwritten')
    previous = read(previous_path)
    require(previous.get('schema_version') == 2 and previous.get('kind') == 'cap-experiment-full-r2-explicit-adoption'
            and previous.get('source_sha') == BUSINESS_SOURCE and previous.get('logical_verified_units') == 88
            and previous.get('original_G_verified_units') == 87 and previous.get('named_raw_recovery_units') == 1
            and [e['unit'] for e in previous['entries']] == [s['unit'] for s in matrix()[:88]],
            'Preserved revision-2 adoption must cover exactly 87 originals plus separate B0 recovery')
    for entry in previous['entries']:
        proof = entry['backup_receipt']; archive = Path(proof['local_archive'])
        require(g_path(str(archive)) and archive.is_file() and archive.stat().st_size == proof['bytes']
                and digest(archive) == proof['sha256'] and proof.get('raw_encounters_verified') == 2000,
                'Adopted original G archive is absent or changed')
    loader = importlib.util.spec_from_file_location('cap_r2_G_evidence', Path(__file__).resolve().parent / 'cap_full_transport.py')
    legacy = importlib.util.module_from_spec(loader); loader.loader.exec_module(legacy)
    entries = []
    for spec in matrix()[88:90]:
        folder = local_root / 'cap-experiment-full-r2-raw' / spec['unit']
        receipt_path = folder / 'verified/local-backup-receipt.json'; cleanup_path = folder / 'cloud-cleanup-receipt.json'
        proof, cleanup = read(receipt_path), read(cleanup_path)
        archive, extraction = Path(proof['local_archive']), Path(proof['local_directory'])
        manifest = legacy.verify_archive(archive, proof, extraction, proof['output_budget_bytes'] + METADATA_RESERVE)
        verified = legacy.verify_unit(extraction, manifest, spec['unit'])
        require(proof.get('unit') == spec['unit'] and proof.get('source_sha') == BUSINESS_SOURCE
                and proof.get('raw_events_verified') == verified['raw_events_verified']
                and proof.get('raw_encounters_verified') == 2000 and proof.get('runtime_identical_to_original') is True
                and cleanup.get('ok') is True and cleanup.get('unit') == spec['unit']
                and cleanup.get('manifest_sha256') == proof['manifest_sha256']
                and cleanup.get('local_G_archive_sha256') == proof['sha256']
                and cleanup.get('local_G_archive_bytes') == proof['bytes'], 'Original r2 B1/B2 G cleanup differs')
        entries.append({'unit': spec['unit'], 'kind': 'r2_original_G_verified', 'backup_receipt': proof,
                        'backup_receipt_raw_sha256': digest(receipt_path), 'cloud_cleanup': cleanup,
                        'cloud_cleanup_raw_sha256': digest(cleanup_path),
                        'manifest_sha256': digest(extraction / 'manifest.json'),
                        'original_result_sha256': digest(extraction / 'metadata/result.json')})
    value = {'schema_version': 1, 'kind': GROUP + '-explicit-adoption', 'business_source_sha': BUSINESS_SOURCE,
             'base88_adoption': previous, 'base88_adoption_sha256': digest(previous_path),
             'r2_entries': entries, 'logical_verified_units': 90, 'successful_native_executions': 91,
             'original_G_verified_units': 87, 'named_raw_recovery_units': 1, 'r2_G_verified_units': 2,
             'native_encounters_G_verified': 180000, 'next_pending': matrix()[90],
             'no_native_business_executed_locally': True, 'whole_task_accepted': False, 'full_formal_pending': True}
    write(destination, value)
    return {'ok': True, 'adoption_file': str(destination), 'sha256': digest(destination),
            'logical_verified_units': 90, 'successful_native_executions': 91, 'next_pending': matrix()[90]}



def legacy_r2(root):
    directory = exact(root / 'evidence/cap-experiment-full-r2', root)
    path = directory / 'controller-revision2.py'
    require(path.is_file() and not path.is_symlink(), 'Preserved original r2 validation controller is required')
    loader = importlib.util.spec_from_file_location('cap_original_r2_validation', path)
    module = importlib.util.module_from_spec(loader); loader.loader.exec_module(module)
    require(module.GROUP == 'cap-experiment-full-r2' and module.SOURCE == BUSINESS_SOURCE,
            'Original r2 validator source or scope changed')
    return module, {'path': str(path), 'sha256': digest(path)}



def adoption_validate(root, adoption):
    require(adoption.get('schema_version') == 1 and adoption.get('kind') == GROUP + '-explicit-adoption'
            and adoption.get('business_source_sha') == BUSINESS_SOURCE and adoption.get('logical_verified_units') == ADOPTED_UNITS
            and adoption.get('successful_native_executions') == 91
            and adoption.get('original_G_verified_units') == 87 and adoption.get('named_raw_recovery_units') == 1
            and adoption.get('r2_G_verified_units') == 2 and adoption.get('native_encounters_G_verified') == 180000
            and adoption.get('no_native_business_executed_locally') is True
            and adoption.get('whole_task_accepted') is False and adoption.get('full_formal_pending') is True,
            'Exact 90 logical unit / 91 successful execution adoption scope changed')
    legacy, contract = legacy_r2(root)
    base = adoption['base88_adoption']; old_path = root / 'evidence/cap-experiment-full-r2/adoption.json'
    require(digest(old_path) == adoption['base88_adoption_sha256'] and read(old_path) == base,
            'Original r2 revision-2 adoption raw bytes changed')
    legacy.adoption_validate(root, base)
    entries = adoption['r2_entries']
    require([e['unit'] for e in entries] == [s['unit'] for s in matrix()[88:90]],
            'New adopted evidence must be exactly original B1/B2 without skipped or duplicate units')
    for entry in entries:
        spec = legacy.identity(entry['unit']); metadata, output = legacy.paths(root, entry['unit'])
        legacy.cleaned(metadata, output, spec)
        require(read(metadata / 'local-backup-receipt.json') == entry['backup_receipt']
                and digest(metadata / 'local-backup-receipt.json') == entry['backup_receipt_raw_sha256']
                and read(metadata / 'local-storage-cleanup.json') == entry['cloud_cleanup']
                and digest(metadata / 'local-storage-cleanup.json') == entry['cloud_cleanup_raw_sha256']
                and digest(metadata / 'delivery-manifest.json') == entry['manifest_sha256']
                and digest(metadata / 'result.json') == entry['original_result_sha256'],
                'Original r2 execution / G archive / cleanup bytes changed')
    return adoption



def runtime_contract(root, verify_files=True, attempt=None):
    attempt = attempt or RUNTIME_ATTEMPT or read(paths(root)[0] / 'runtime-selection.json')['attempt']
    require(re.fullmatch(r'cap-budget-runtime-r[0-9]+-[0-9]{8}', attempt) is not None,
            'Only an explicit owned mixed runtime attempt is supported')
    base = exact(root / 'work' / attempt, root)
    evidence = exact(root / 'evidence' / attempt, root)
    inputs = read(evidence / 'inputs.json')
    build = read(evidence / 'build-result.json')
    pilot = read(evidence / 'pilot-result.json')
    equivalence = read(evidence / 'equivalence.json')
    backup = read(evidence / 'local-backup-receipt.json')
    manifest_path = evidence / 'delivery-manifest.json'
    manifest = read(manifest_path)
    mixed = inputs.get('source_sha')
    publication = inputs.get('instrumentation_source_sha')
    require(re.fullmatch('[0-9a-f]{40}', mixed or '') is not None and mixed != BUSINESS_SOURCE
            and re.fullmatch('[0-9a-f]{40}', publication or '') is not None,
            'Actual mixed Git source and instrumentation revision must be frozen')
    hashes, original = inputs.get('source_hashes', {}), inputs.get('original_source_hashes', {})
    baseline = read(root / 'evidence/cap-runtime-recovery-r1-20261011/inputs.json')
    require(inputs.get('business_source_sha') == BUSINESS_SOURCE and len(hashes) == len(original) == 372
            and baseline.get('source_sha') == BUSINESS_SOURCE and baseline.get('source_hashes') == original
            and hashes.keys() == original.keys() and set(inputs.get('override_paths', [])) == set(OVERRIDES)
            and {name for name in hashes if hashes[name] != original[name]} == set(OVERRIDES)
            and inputs.get('original370_inputs_unchanged') is True
            and inputs.get('exact_two_overrides_match_instrumentation_Git_bytes') is True,
            'Mixed runtime must prove exactly 370 original files and two declared overrides')
    actual = build.get('runtime_hashes', {})
    domain = {name: value for name, value in RUNTIME_HASHES.items() if name.startswith('FantasyCard.Domain.')}
    numerics = {name: value for name, value in actual.items() if name.startswith('FantasyCard.Numerics')}
    require(build.get('ok') is True and build.get('source_sha') == mixed
            and build.get('business_source_sha') == BUSINESS_SOURCE and set(actual) == set(RUNTIME_HASHES)
            and all(actual[name] == value for name, value in domain.items())
            and build.get('domain_original_hashes') == domain
            and build.get('domain_hashes_identical_to_original') is True
            and build.get('domain_regression_exact_56_passed') is True
            and build.get('source_inputs_unchanged') is True and build.get('owned_container_removed') is True
            and build.get('numerics_hashes_actual') == numerics
            and all(re.fullmatch('[0-9a-f]{64}', value or '') is not None for value in actual.values())
            and actual['FantasyCard.Numerics.dll'] != RUNTIME_HASHES['FantasyCard.Numerics.dll'],
            'Mixed runtime build lacks exact original Domain and explicit changed Numerics evidence')
    validations = pilot.get('validations', {})
    require(set(validations) == {'original', 'new-default', 'new-16g'}
            and all(v.get('ok') is True and v.get('encounters') == 6 and v.get('pairs') == 3
                    and len(v.get('negative_controls', [])) == 4
                    and all(c.get('rejected') is True for c in v['negative_controls']) for v in validations.values())
            and all(len(validations[name].get('collector_negative_controls', [])) == 3
                    and all(c.get('rejected') is True for c in validations[name]['collector_negative_controls'])
                    for name in ('new-default', 'new-16g'))
            and pilot.get('owned_container_removed') is True
            and pilot.get('source_and_runtime_inputs_unchanged') is True,
            'All three actual six-encounter pilot sets and original/new metadata controls are required')
    require(pilot.get('ok') is True and pilot.get('equivalence_ok') is True
            and pilot.get('equivalence_json_sha256') == digest(evidence / 'equivalence.json')
            and equivalence.get('ok') is True and len(equivalence.get('comparisons', [])) == 2
            and all(c.get('ok') is True for c in equivalence['comparisons'])
            and len(equivalence.get('negative_controls', [])) == 4
            and all(c.get('rejected') is True for c in equivalence['negative_controls']),
            'Native original/default/16 GiB pilot equivalence has not passed')
    flags = ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
             'inner_gzip_CRC_raw_SHA_counts_verified', 'pilot_equivalence_verified',
             'domain_hashes_identical_to_original', 'no_native_business_executed_locally')
    require(backup.get('ok') is True and all(backup.get(key) is True for key in flags)
            and backup.get('source_sha') == mixed and backup.get('business_source_sha') == BUSINESS_SOURCE
            and backup.get('instrumentation_source_sha') == publication
            and backup.get('source_files_verified') == 372 and backup.get('runtime_files_verified') == 8
            and backup.get('runtime_identical_to_original') is False
            and backup.get('manifest_sha256') == digest(manifest_path)
            and backup.get('members') == backup.get('members_verified') == len(manifest['files'])
            and g_path(backup.get('local_archive')) and g_path(backup.get('local_directory'))
            and re.fullmatch('[0-9a-f]{64}', backup.get('sha256', '')) is not None
            and type(backup.get('bytes')) is int and backup['bytes'] > 0,
            'Mixed build, original sources and native pilot must have verified original G backup')
    scratch = Path('/dev/shm') / ('pr13-' + attempt)
    members = {}
    for row in manifest['files']:
        member = PurePosixPath(row['path'])
        require(not member.is_absolute() and '..' not in member.parts and '\\' not in row['path']
                and member.as_posix() == row['path'] and len(member.parts) >= 2
                and row['path'] not in members
                and re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) is not None,
                'Unsafe runtime delivery manifest member')
        members[row['path']] = row
        path = Path(row['source'])
        directory = {'metadata': evidence, 'persistent': base, 'passed-build-scratch': scratch}.get(member.parts[0])
        require(directory is not None and path == directory.joinpath(*member.parts[1:]),
                'Runtime G manifest member escapes its exact attempt')
        if member.parts[0] == 'passed-build-scratch' and not scratch.exists():
            cleanup = read(evidence / 'passed-scratch-cleanup.json')
            require(cleanup.get('ok') is True and cleanup.get('attempt') == attempt
                    and cleanup.get('source_sha') == mixed and cleanup.get('passed_scratch_removed') == str(scratch)
                    and cleanup.get('manifest_sha256') == backup['manifest_sha256']
                    and cleanup.get('local_G_archive_sha256') == backup['sha256']
                    and cleanup.get('local_G_archive_bytes') == backup['bytes'],
                    'Missing passed runtime scratch must have exact verified G cleanup')
            continue
        if verify_files:
            require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path
                    and path.stat().st_size == row['bytes'] and digest(path) == row['sha256'],
                    'G-backed mixed runtime original member changed')
    for name in ('inputs.json', 'build-result.json', 'pilot-result.json', 'equivalence.json'):
        require(members.get('metadata/' + name, {}).get('sha256') == digest(evidence / name),
                'Original G-backed runtime gate metadata changed')
    require(all(members.get('persistent/source/' + name, {}).get('sha256') == value for name, value in hashes.items())
            and all(members.get('persistent/runtime/' + name, {}).get('sha256') == value for name, value in actual.items()),
            'G manifest must independently cover every frozen mixed source and compiled runtime file')
    if verify_files:
        require({p.name: digest(p) for p in ordinary_files(base / 'runtime')} == actual,
                'Frozen mixed compiled runtime bytes changed')
        for name, expected in hashes.items():
            parts = PurePosixPath(name).parts
            require(not name.startswith('/') and '..' not in parts and '\\' not in name, 'Unsafe mixed source path')
            path = base / 'source' / name
            require(path.resolve(strict=True).is_relative_to(base / 'source') and not path.is_symlink()
                    and digest(path) == expected, 'Frozen mixed source bytes changed')
    return {'attempt': attempt, 'source_sha': mixed, 'business_source_sha': BUSINESS_SOURCE,
            'instrumentation_source_sha': publication, 'mixed_input_manifest_sha256': digest(evidence / 'inputs.json'),
            'collector_revision': COLLECTOR_REVISION, 'source_subset_files': 372,
            'original_business_files': 370, 'override_paths': list(OVERRIDES), 'runtime_hashes': actual,
            'domain_original_hashes': domain, 'domain_hashes_identical_to_original': True,
            'runtime_path': str(base / 'runtime'), 'source_path': str(base / 'source'),
            'build_result_sha256': digest(evidence / 'build-result.json'),
            'pilot_result_sha256': digest(evidence / 'pilot-result.json'),
            'equivalence_json_sha256': digest(evidence / 'equivalence.json'),
            'G_backup_receipt_sha256': digest(evidence / 'local-backup-receipt.json'),
            'G_manifest_sha256': digest(manifest_path), 'runtime_identical_to_original': False,
            'original_2068_directory_restored': False}


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
    require(value.get('business_source_sha') == BUSINESS_SOURCE and value.get('adopted_units') == ADOPTED_UNITS
            and value.get('adopted_successful_native_executions') == 91
            and value.get('legacy_validation_contract') == legacy_r2(root)[1]
            and value.get('native_unit_raw_ceiling_bytes') == NATIVE_RAW_CEILING
            and value.get('native_unit_raw_absolute_max_bytes') == NATIVE_RAW_MAX,
            'Mixed-source adoption, collector budget or original validation contract changed')
    adoption = read(evidence / 'adoption.json')
    require(digest(evidence / 'adoption.json') == value['adoption_sha256'], 'Frozen adoption changed')
    adoption_validate(root, adoption)
    return value


def initialize(root, adoption_path, runtime_attempt):
    host(root)
    evidence, raw = paths(root)
    require(not raw.exists(), 'Existing r3 continuation raw root cannot be initialized again')
    if evidence.exists():
        exact(evidence, root)
        require({p.name for p in evidence.iterdir()} <= {'controller.py', 'adoption-input.json'}
                and all(p.is_file() and not p.is_symlink() for p in evidence.iterdir()),
                'Existing r3 evidence cannot be initialized again')
    adoption = adoption_validate(root, read(adoption_path))
    contract = runtime_contract(root, attempt=runtime_attempt)
    require(contract['source_sha'] == SOURCE, 'Configured mixed Git source differs')
    legacy, legacy_contract = legacy_r2(root)
    guard(root)
    evidence.mkdir(exist_ok=True); (evidence / 'units').mkdir(); raw.mkdir()
    write(evidence / 'runtime-selection.json', {'attempt': runtime_attempt, 'source_sha': SOURCE})
    write(evidence / 'adoption.json', adoption)
    value = {'schema_version': 1, 'kind': GROUP, 'source_sha': SOURCE, 'business_source_sha': BUSINESS_SOURCE,
             'image_sha': IMAGE, 'units': matrix(), 'native_units': 360, 'expected_encounters': 720000,
             'expected_pairs': 360000, 'samples_per_arm': 1000, 'runtime_contract': contract,
             'legacy_validation_contract': legacy_contract, 'adoption_sha256': digest(evidence / 'adoption.json'),
             'adopted_units': ADOPTED_UNITS, 'adopted_successful_native_executions': 91,
             'default_persistent_output_budget_bytes': DEFAULT_OUTPUT_BUDGET,
             'native_raw_part_bytes': RAW_PART_BYTES, 'native_unit_raw_ceiling_bytes': NATIVE_RAW_CEILING,
             'native_unit_raw_absolute_max_bytes': NATIVE_RAW_MAX, 'collector_revision': COLLECTOR_REVISION,
             'capture_budget_is_not_a_balance_or_guardian_timeout_result': True,
             'mixed_source_is_not_original_full_runtime': True,
             'root_metadata_reserve_bytes': METADATA_RESERVE, 'memory_floor_bytes': MEMORY_FLOOR,
             'container_memory_bytes': MEMORY_LIMIT, 'disk_free_ratio': .15,
             'native_deadline_seconds': 1200, 'validation_deadline_seconds': 2400,
             'outer_deadline_seconds': 4200, 'capacity_tests_deferred': True, 'human_experience_in_scope': False,
             'full_formal_pending': True, 'whole_task_accepted': False}
    write(evidence / 'plan.json', value)
    return {'ok': True, 'adopted_units': ADOPTED_UNITS, 'logical_verified_units': ADOPTED_UNITS,
            'successful_native_executions': 91, 'remaining_units': 270, 'next_pending': matrix()[90],
            'runtime_contract': contract, 'full_formal_pending': True}



def successful(metadata, output, spec, check_output=True):
    prereg = read(metadata / 'preregistration.json')
    require(all(prereg.get(key) == value for key, value in spec.items()), 'Unit preregistration matrix differs')
    result = read(metadata / 'result.json')
    require(result.get('ok') is True and result.get('unit') == spec['unit'] and result.get('source_sha') == SOURCE
            and result.get('exit_code') == 0 and result.get('oom_killed') is False
            and result.get('compiled_mixed_runtime_unchanged') is True
            and result.get('domain_hashes_identical_to_original') is True
            and result.get('runtime_identical_to_original') is False
            and result.get('numerics_runtime_identical_to_original') is False
            and result.get('runtime_contract') == prereg.get('runtime_contract')
            and result.get('business_source_sha') == BUSINESS_SOURCE
            and result.get('source_subset_inputs_unchanged') is True and result.get('owned_container_removed') is True
            and result.get('main_acceptance_granted') is False, 'Failed/incomplete native unit is retained')
    if check_output and output.exists():
        require(read(output / 'result.json') == result, 'Raw/root result mismatch')
        native_success(output, spec)
    return result


def native_success(output, spec):
    summary = read(output / 'native/summary.json')
    validation = read(output / 'validation.json')
    original = read(output / 'native/manifest.json')
    prereg = read(paths(output.parents[2], spec['unit'])[0] / 'preregistration.json')
    expected_source = {'source_sha': SOURCE, 'business_source_sha': BUSINESS_SOURCE,
                       'instrumentation_source_sha': prereg['instrumentation_source_sha'],
                       'mixed_input_manifest_sha256': prereg['mixed_input_manifest_sha256'],
                       'collector_revision': COLLECTOR_REVISION,
                       'raw_unit_limit_bytes': prereg['raw_unit_limit_bytes']}
    require(original.get('schema') == 'actual_cap_effective_experiment_v2'
            and all(all(document.get(key) == value for key, value in expected_source.items())
                    for document in (original, summary, validation))
            and original.get('collection_complete') is True and summary.get('collection_complete') is True
            and original.get('raw_unit_limit_explicit') is True and summary.get('raw_unit_limit_explicit') is True
            and validation.get('collector_metadata_complete') is True,
            'Native mixed-source collector provenance / explicit budget / completion differs')
    total_raw = sum(part['raw_bytes'] for part in summary.get('event_parts', []))
    require(type(total_raw) is int and total_raw == original.get('event_raw_bytes') == summary.get('event_raw_bytes')
            == validation.get('event_raw_bytes') and 0 <= total_raw <= prereg['raw_unit_limit_bytes']
            and summary.get('event_parts') and all(type(part.get('raw_bytes')) is int
                    and 0 < part['raw_bytes'] <= RAW_PART_BYTES for part in summary['event_parts'])
            and validation.get('original_two_GiB_budget_satisfied') == (total_raw <= 2 * 1024**3),
            'Declared dynamic raw budget or original 128 MiB event parts differ')
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
    collector_controls = validation.get('collector_negative_controls', [])
    require(len(collector_controls) == 3 and {row.get('name') for row in collector_controls} == {
                'collector-declared-budget-tampered', 'collector-event-part-missing', 'collector-cumulative-budget-exceeded'}
            and all(row.get('rejected') is True for row in collector_controls),
            'All three collector metadata controls must reject')
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
    prereg = read(metadata / 'preregistration.json')
    require(receipt.get('business_source_sha') == BUSINESS_SOURCE
            and receipt.get('instrumentation_source_sha') == prereg['instrumentation_source_sha']
            and receipt.get('mixed_input_manifest_sha256') == prereg['mixed_input_manifest_sha256']
            and receipt.get('collector_revision') == COLLECTOR_REVISION
            and receipt.get('raw_unit_limit_bytes') == prereg['raw_unit_limit_bytes'] == manifest['raw_unit_limit_bytes']
            and receipt.get('event_raw_bytes_verified') == manifest['event_raw_bytes']
            and receipt.get('collector_metadata_complete') is True
            and receipt.get('runtime_identical_to_original') is False
            and receipt.get('domain_hashes_identical_to_original') is True
            and receipt.get('runtime_contract') == prereg['runtime_contract'],
            'G proof mixed source, collector or original Domain provenance differs')
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
    completed = ADOPTED_UNITS
    current = None
    next_pending = None
    for spec in matrix()[ADOPTED_UNITS:]:
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
            'next_pending': next_pending, 'adopted_units': ADOPTED_UNITS, 'logical_verified_units': completed,
            'successful_native_executions_G_verified': completed + 1,
            'runtime_contract': read(paths(root)[0] / 'plan.json')['runtime_contract'],
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


def launch_next(root, budget, raw_limit=NATIVE_RAW_CEILING):
    host(root)
    require(isinstance(budget, int) and DEFAULT_OUTPUT_BUDGET <= budget <= 536870912,
            'Budget must be explicit and retain the original 512 MiB operational maximum')
    require(type(raw_limit) is int and NATIVE_RAW_CEILING <= raw_limit <= NATIVE_RAW_MAX,
            'Explicit r3 raw event capture limit must remain between 16 and 32 GiB')
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
                  native_unit_raw_ceiling_bytes=raw_limit, raw_unit_limit_bytes=raw_limit,
                  native_unit_raw_absolute_max_bytes=NATIVE_RAW_MAX,
                  collector_revision=COLLECTOR_REVISION, raw_unit_limit_explicit=True,
                  business_source_sha=BUSINESS_SOURCE,
                  instrumentation_source_sha=contract['instrumentation_source_sha'],
                  mixed_input_manifest_sha256=contract['mixed_input_manifest_sha256'],
                  whole_task_accepted=False,
                  full_formal_pending=True, G_backup_verified=False,
                  budget_is_storage_guard_not_native_sample_or_raw_limit=True)
    write(metadata / 'preregistration.json', prereg)
    shutil.copyfile(Path(__file__), metadata / 'runner.py')
    marker = {'status': 'Prepared', 'attempt': OWNER, 'unit': spec['unit'],
              'systemd_unit': prereg['systemd_unit'], 'runner_pid': None,
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'reserved_root_bytes': budget + METADATA_RESERVE, 'output_root': str(output),
              'persistent_output_budget_bytes': budget, 'G_backup_verified': False,
              'source_sha': SOURCE, 'business_source_sha': BUSINESS_SOURCE,
              'instrumentation_source_sha': contract['instrumentation_source_sha'],
              'mixed_input_manifest_sha256': contract['mixed_input_manifest_sha256'],
              'runtime_contract': contract, 'raw_unit_limit_bytes': raw_limit,
              'collector_revision': COLLECTOR_REVISION, 'runtime_identical_to_original': False,
              'prepared_at': time.time()}
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
  process=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=1200 if index==0 else 2400)
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
                  native_raw_part_bytes=RAW_PART_BYTES, native_unit_raw_ceiling_bytes=prereg['raw_unit_limit_bytes'],
                  source_subset_files=372, original_2068_directory_restored=False,
                  business_source_sha=BUSINESS_SOURCE,
                  instrumentation_source_sha=prereg['instrumentation_source_sha'],
                  mixed_input_manifest_sha256=prereg['mixed_input_manifest_sha256'],
                  raw_unit_limit_bytes=prereg['raw_unit_limit_bytes'], raw_unit_limit_explicit=True,
                  collector_revision=COLLECTOR_REVISION, runtime_contract=prereg['runtime_contract'],
                  runtime_identical_to_original=False, balance_failure_claimed=False,
                  G_backup_verified=False, whole_task_accepted=False, main_acceptance_granted=False,
                  full_formal_pending=True)
    try:
        contract = runtime_contract(root)
        require(contract == prereg['runtime_contract'], 'Runtime/source provenance differs from preregistration')
        budget = prereg['persistent_output_budget_bytes']
        guard(root, metadata, budget=budget, start=True)
        output.mkdir()
        provenance_args = ['--business-source-sha', BUSINESS_SOURCE,
                           '--instrumentation-source-sha', contract['instrumentation_source_sha'],
                           '--mixed-input-manifest-sha256', contract['mixed_input_manifest_sha256'],
                           '--cap-raw-unit-limit-bytes', str(prereg['raw_unit_limit_bytes'])]
        commands = [
            ['dotnet', '/base/runtime/FantasyCard.Numerics.dll', '--cap-effective-experiment',
             '--source-sha', SOURCE, '--hero', spec['hero'], '--group', spec['group'],
             '--element', spec['element'], '--equipment-level', str(spec['level']),
             '--block-index', str(spec['block']), '--samples', '1000', '--output', '/raw/native'] + provenance_args,
            ['python3', '/work/tools/pr13_cap_effective_experiment.py', '--input', '/raw/native',
             '--source-sha', SOURCE, '--output', '/raw/validation.json', '--controls',
             '--collector-revision', COLLECTOR_REVISION] + provenance_args]
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
        deadline = time.monotonic() + 4200
        while True:
            container = owned_state(cid)
            if not container['State']['Running']:
                break
            guard(root, metadata, output, budget)
            require(time.monotonic() < deadline, 'outer 4200 second execution deadline; retain raw without balance inference')
            time.sleep(5)
        result.update(exit_code=container['State']['ExitCode'], oom_killed=container['State']['OOMKilled'])
        guard(root, metadata, output, budget)
        runtime_contract(root)
        result['compiled_mixed_runtime_unchanged'] = True
        result['domain_hashes_identical_to_original'] = True
        result['numerics_runtime_identical_to_original'] = False
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
    collector_proof = {'kind': 'cap-effective-r3-retained-collector-proof', 'unit': name,
                       'source_sha': SOURCE, 'business_source_sha': BUSINESS_SOURCE,
                       'native_manifest': read(output / 'native/manifest.json'), 'native_summary': summary,
                       'validation': read(output / 'validation.json'),
                       'native_manifest_sha256': digest(output / 'native/manifest.json'),
                       'native_summary_sha256': digest(output / 'native/summary.json'),
                       'validation_sha256': digest(output / 'validation.json')}
    proof_path = metadata / 'collector-proof.json'
    if proof_path.exists():
        require(read(proof_path) == collector_proof, 'Preserve conflicting original collector proof')
    else:
        write(proof_path, collector_proof)
    value = {'schema_version': 1, 'kind': GROUP, 'unit': name, 'source_sha': SOURCE,
             'native_encounters': 2000, 'native_casts': summary['actual_casts'], 'native_ticks': summary['actual_ticks'],
             'business_source_sha': BUSINESS_SOURCE,
             'instrumentation_source_sha': summary['instrumentation_source_sha'],
             'mixed_input_manifest_sha256': summary['mixed_input_manifest_sha256'],
             'collector_revision': COLLECTOR_REVISION, 'raw_unit_limit_bytes': summary['raw_unit_limit_bytes'],
             'event_raw_bytes': summary['event_raw_bytes'], 'collection_complete': True,
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
    host(root); plan(root)
    spec = identity(name); metadata, output = paths(root, name)
    if (metadata / 'local-storage-cleanup.json').exists():
        result = cleaned(metadata, output, spec)
        release_cleaned_marker(metadata, output, spec)
        return result
    exact(metadata, root); exact(output, root, exists=False); terminal(unit_status(name))
    manifest = read(metadata / 'delivery-manifest.json')
    manifest_paths(metadata, output, manifest, spec)
    receipt = read(receipt_path); backup_validate(receipt, metadata, manifest, spec)
    marker = read(metadata / 'resource-reservation.json')
    require(marker.get('status') == 'Ended' and marker.get('result_ok') is True
            and marker.get('attempt') == OWNER and marker.get('unit') == name
            and marker.get('source_sha') == SOURCE and marker.get('output_root') == str(output),
            'Only the exact successful ended native reservation may be reclaimed')
    intent_path = metadata / 'cleanup-intent.json'
    intent = {'unit': name, 'source_sha': SOURCE, 'output_directory': str(output),
              'manifest_sha256': receipt['manifest_sha256'], 'local_G_archive_sha256': receipt['sha256'],
              'local_G_archive_bytes': receipt['bytes'], 'backup_receipt_sha256': digest(receipt_path)}
    if intent_path.exists():
        require(all(read(intent_path).get(k) == v for k, v in intent.items()), 'Interrupted cleanup anchor differs')
        successful(metadata, output, spec, check_output=False)
        expected = {row['source']: row for row in manifest['files'] if row['path'].startswith('outputs/')}
        if output.exists():
            for path in ordinary_files(output):
                row = expected.get(str(path))
                require(row is not None and path.stat().st_size == row['bytes'] and digest(path) == row['sha256'],
                        'Remaining interrupted output differs from original G archive')
        for row in manifest['files']:
            if row['path'].startswith('metadata/'):
                path = Path(row['source'])
                require(path.is_file() and not path.is_symlink() and path.resolve(strict=True).is_relative_to(metadata)
                        and path.stat().st_size == row['bytes'] and digest(path) == row['sha256'],
                        'Interrupted cleanup original metadata changed')
    else:
        exact(output, root)
        successful(metadata, output, spec)
        require(manifest['files'] == manifest_files(metadata, output, spec, manifest['output_budget_bytes']),
                'Current complete originals differ from archived manifest')
    destination = metadata / 'local-backup-receipt.json'
    if destination.exists():require(read(destination) == receipt, 'Preserve conflicting G receipt')
    else:write(destination, receipt)
    no_active_bind(output); terminal(unit_status(name)); guard(root)
    if not intent_path.exists():write(intent_path, dict(intent, at=time.time()))
    before = os.statvfs(root)
    allocated = sum(p.stat().st_blocks * 512 for p in ordinary_files(output)) if output.exists() else 0
    if output.exists():
        exact(output, root); shutil.rmtree(output)
    after = os.statvfs(root)
    result = dict(intent, ok=True, root_allocated_bytes_removed=allocated,
                  root_disk_bytes_reclaimed=(after.f_bavail-before.f_bavail)*after.f_frsize,
                  cloud_raw_removed=True, source_runtime_and_metadata_retained=True,
                  whole_task_accepted=False, full_formal_pending=True)
    write(metadata / 'local-storage-cleanup.json', result)
    result = cleaned(metadata, output, spec)
    release_cleaned_marker(metadata, output, spec)
    return result


def release_cleaned_marker(metadata, output, spec):
    """Mutating caller has already verified the exact complete G cleanup proof."""
    receipt = read(metadata / 'local-backup-receipt.json')
    marker = read(metadata / 'resource-reservation.json')
    require(marker.get('status') == 'Ended' and marker.get('result_ok') is True
            and marker.get('attempt') == OWNER and marker.get('unit') == spec['unit']
            and marker.get('source_sha') == SOURCE and marker.get('output_root') == str(output)
            and not output.exists() and not output.is_symlink(),
            'Only an exact passed, G-cleaned reservation may be released')
    marker.update(G_backup_verified=True, local_G_archive_sha256=receipt['sha256'],
                  local_G_archive_bytes=receipt['bytes'], output_cleaned=True)
    write(metadata / 'resource-reservation.json', marker, overwrite=True)



def main():
    global SOURCE, RUNTIME_ATTEMPT
    choices = ('local-adoption', 'init', 'status', 'launch-next', '_run-unit', 'prepare-delivery', 'cleanup')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', nargs='?', choices=choices)
    parser.add_argument('--action', choices=choices)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--unit')
    parser.add_argument('--adoption-file', type=Path)
    parser.add_argument('--local-output-root', type=Path)
    parser.add_argument('--previous-adoption-file', type=Path)
    parser.add_argument('--runtime-attempt', help='Explicit G-verified mixed runtime attempt, required for first init')
    parser.add_argument('--receipt-file', type=Path)
    parser.add_argument('--output-budget-bytes', type=int, default=DEFAULT_OUTPUT_BUDGET)
    parser.add_argument('--raw-unit-limit-bytes', type=int, default=NATIVE_RAW_CEILING)
    args = parser.parse_args()
    phase = args.phase or args.action
    require(phase in choices and (not args.phase or not args.action or args.phase == args.action), 'Choose one exact controller phase')
    if phase == 'local-adoption':
        require(args.local_output_root is not None and args.adoption_file is not None
                and args.previous_adoption_file is not None, 'Local G root / preserved r2 adoption / new destination required')
        result = local_adoption(args.local_output_root, args.adoption_file, args.previous_adoption_file)
    else:
        host(args.root)
        if phase == 'init':
            require(args.runtime_attempt is not None, 'First r3 init requires the explicit G-verified mixed runtime attempt')
        RUNTIME_ATTEMPT = args.runtime_attempt
        contract = runtime_contract(args.root, verify_files=False, attempt=RUNTIME_ATTEMPT)
        SOURCE, RUNTIME_ATTEMPT = contract['source_sha'], contract['attempt']
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
            require(not lock_path.is_symlink() and lock_path.resolve(strict=False) == lock_path,
                    'Linked shared coordination lock is rejected')
            with lock_path.open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if phase == 'init':
                    require(args.adoption_file is not None, 'Explicit G adoption file required')
                    result = initialize(args.root, args.adoption_file, RUNTIME_ATTEMPT)
                elif phase == 'launch-next':
                    result = launch_next(args.root, args.output_budget_bytes, args.raw_unit_limit_bytes)
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
