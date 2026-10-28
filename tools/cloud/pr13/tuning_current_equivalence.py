"""Tencent-only bounded old/current B08.3 source gate, without rebuilding.

Prepare freezes restored byte provenance and selected current Git inputs.
Run executes Guardian/BOSS/Earth first and reuses that family in the complete
36-family matrix. Existing attempts never restart after uncertain observation.
G verification precedes exact owned passed-output cleanup. The root dispatcher
owns the pool scheduling hold and releases it after the recorded G cleanup.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = Path('/home/ubuntu/pr13-acceptance-20261009')
GIT = Path('/opt/fantasycard-github')
OLD = '3a984bc64f5346b7f1d134926deec54be928a060'
CURRENT = '18ae9d4e949cbdb4882b6469aff016f6568fb0fd'
MIXED = '581cd9f74962dd61424e77c529b1259afbb39fe7'
IMAGE = 'sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f'
CURRENT_WORK = BASE / 'work/cap-budget-runtime-r1-20261011'
MONITOR = '2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'
MEMORY = 950 * 1024**2
FLOOR = 500000000
BUDGET = 128 * 1024**2
METADATA = 16 * 1024**2
PILOT = ('Guardian', 'BOSS', 'ET-EARTH-G')
MUTABLE = {'delivery-manifest.json', 'local-backup-receipt.json', 'local-storage-cleanup.json'}
REUSE = 'tuning-current-equivalence-r1-20261011'
R1_TOOL_SHA = {
    'runner.py': 'cd997ed85f251b91daa41dd276d4b9729d26907c4263a42c275deed48acea5b9',
    'equivalence.py': 'de9da177134adb9c203d05e3637ffd43bb6f78e1da4dbc76b6bcee45df868e33',
    'preregistration.json': 'b14f7eaecca3751d2e42631b4eb5691e508af621712cc1a894f9ed7b5b548f17'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing/linked frozen metadata: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    require(not path.exists(), 'Existing attempt cannot be overwritten: ' + str(path))
    with path.open('xb') as handle:
        handle.write((json.dumps(value, indent=2, sort_keys=True) + '\n').encode('utf-8'))
        handle.flush()
        os.fsync(handle.fileno())


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, check=True, timeout=timeout)


def docker(*args):
    return command(['sudo', '-n', 'docker', *args])


def host():
    require(os.name != 'nt' and sys.platform.startswith('linux')
            and BASE.resolve(strict=True) == BASE and GIT.is_dir(), 'Exact Tencent acceptance Linux host only')


def paths(attempt):
    require(re.fullmatch(r'tuning-current-equivalence-r[1-9][0-9]*-[0-9]{8}', attempt), 'Fresh named equivalence attempt required')
    return BASE / 'evidence' / attempt, BASE / 'work' / attempt


def family_name(family):
    return '-'.join(family) + '-B0'


def families():
    all_families = list(itertools.product(('Mage', 'Priest', 'Guardian'), ('O1', 'O6', 'E1', 'BOSS'),
                                         ('ET-WOOD-G', 'ET-EARTH-G', 'ET-METAL-G')))
    return [PILOT] + [f for f in all_families if f != PILOT]


def health():
    with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10) as response:
        require(response.status == 200, 'Production readiness failed')


def guard(work=None, start=False):
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0]) * 1024
    stat = os.statvfs(BASE)
    free = stat.f_bavail * stat.f_frsize
    require(memory['MemAvailable'] >= FLOOR + (MEMORY if start else 0), '500000000-byte memory safety floor')
    require(stat.f_bavail / stat.f_blocks >= .15, '15 percent root free floor')
    if start:
        require(free - int(stat.f_blocks * stat.f_frsize * .15) >= BUDGET + METADATA,
                '128 MiB output plus 16 MiB metadata reservation unavailable')
    if work:
        measured = sum(p.stat().st_size for p in (work / 'outputs').rglob('*') if p.is_file())
        require(measured <= BUDGET, 'Persistent original output budget exceeded; failure prefix retained')
    health()


def unit_state(unit):
    completed = command(['systemctl', 'show', unit,
        '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'], 15)
    values = dict(line.split('=', 1) for line in completed.stdout.decode().splitlines() if '=' in line)
    require(all(key in values for key in ('MainPID', 'ActiveState', 'SubState', 'LoadState', 'ExecMainStatus'))
            and values['MainPID'].isdigit() and values['ExecMainStatus'].isdigit(),
            'Exact systemd observation incomplete; never restart')
    return {'unit': unit, **{k: int(values[k]) for k in ('MainPID', 'ExecMainStatus')},
            **{k: values[k] for k in ('ActiveState', 'SubState', 'LoadState')}}


def owned_container(cid, owner):
    state = json.loads(docker('inspect', cid).stdout)[0]
    require(state['Id'] == cid and state['Config']['Labels'].get('codex.owner') == owner, 'Exact owned container identity differs')
    return state


def exclusive(owner):
    unit = os.environ.get('PR13_TUNING_EQ_SYSTEMD_UNIT', '')
    require(unit == owner, 'Exact root-dispatched systemd lease identity required')
    active = command(['systemctl', 'list-units', '--state=running', '--no-legend', '--plain',
                      'pr13-cap-*', 'pr13-pool-segment-*'], 15).stdout.decode().splitlines()
    require(not any(row.split()[0].removesuffix('.service') != owner for row in active if row.split()),
            'Another exact cap/render native unit is live; keep queued attempt undispatched')
    names = docker('ps', '--format', '{{.Names}}').stdout.decode().splitlines()
    require(not any(name.startswith(('pr13-cap-', 'pr13-pool-segment-')) for name in names),
            'Another cap/render container is live')


def active_bind_guard(targets):
    for cid in docker('ps', '-q', '--no-trunc').stdout.decode().splitlines():
        require(re.fullmatch('[0-9a-f]{64}', cid), 'Full active container identity required')
        state = json.loads(docker('inspect', cid).stdout)[0]
        require(state['Id'] == cid, 'Active inspection changed identity')
        for mount in state.get('Mounts', []):
            require(mount.get('Type') in ('bind', 'volume', 'tmpfs'), 'Unknown active mount type')
            if mount['Type'] != 'bind':
                continue
            if cid == MONITOR and mount.get('Source') == '/' and mount.get('RW') is False:
                continue
            source = Path(mount['Source']).resolve()
            require(not any(source == target or source.is_relative_to(target) or target.is_relative_to(source)
                            for target in targets), 'Active bind intersects exact delivery/cleanup originals')


def runtime_hashes(path):
    require(path.is_dir() and not path.is_symlink(), 'Runtime directory missing/linked')
    require(all(p.is_file() and not p.is_symlink() for p in path.iterdir()), 'Runtime directory contains nonordinary members')
    return {p.name: sha(p) for p in path.iterdir()}


def prepare(args):
    host()
    evidence, work = paths(args.attempt)
    require(not evidence.exists() and not work.exists(), 'Existing attempt cannot be replaced')
    proof = read(args.restoration_proof)
    require(proof['ok'] is True and proof['current_release_source_sha'] == CURRENT
            and proof['current_native_source_sha'] == MIXED and proof['old_native_source_sha'] == OLD
            and proof['related_source_files'] == len(proof['source_hashes']) == 51
            and proof['related_source_Git_blob_bytes_equal'] is True
            and proof['whole_current_tree_equal'] is False and proof['combined_byte_restoration'] is True
            and proof['original_directory_restored'] is False and proof['archive_gzip_CRC_verified'] is True
            and proof['no_native_or_business_logic_executed_locally'] is True,
            'Complete metadata-only G restoration/selected source proof required')
    require(runtime_hashes(args.old_runtime) == proof['old_runtime_hashes']
            and runtime_hashes(CURRENT_WORK / 'runtime') == proof['current_runtime_hashes'], 'Exact old/current eight runtime SHA differ')
    for name, expected in proof['source_hashes'].items():
        require(hashlib.sha256(command(['git', '-C', str(GIT), 'show', CURRENT + ':' + name]).stdout).hexdigest() == expected
                and hashlib.sha256(command(['git', '-C', str(GIT), 'show', MIXED + ':' + name]).stdout).hexdigest() == expected
                and sha(CURRENT_WORK / 'source' / name) == expected, 'Current/mixed actual related source differs: ' + name)
    old_validator = command(['git', '-C', str(GIT), 'show', OLD + ':tools/pr13_tuning_recovery_experiment.py']).stdout
    require(hashlib.sha256(old_validator).hexdigest() == proof['old_validator_sha256'], 'Original oracle Git bytes differ')
    plan = read(args.plan)
    require(plan['families'] == [list(f) for f in families()] and plan['samples_per_arm'] == 3
            and plan['total_unique_native_encounters'] == 432 and plan['initial_pilot_reused_in_matrix'] is True,
            'Exact declared 36-family plan differs')
    require(plan['status'] == 'preregistered-not-executed' and plan['passed'] is False
            and plan['restoration_proof_sha256'] == sha(args.restoration_proof)
            and plan['tool_sha256']['tools/pr13_tuning_current_equivalence.py'] == sha(args.comparator)
            and plan['tool_sha256']['tools/cloud/pr13/tuning_current_equivalence.py'] == sha(Path(__file__)),
            'Preregistered actual comparator/controller/restoration SHA differs')
    require(plan['revision'] == 2 and plan['reuse_original_pilot_attempt'] == REUSE,
            'Explicit separately named R2 pilot reuse preregistration required')
    old_evidence, old_work = paths(REUSE)
    original_result = read(old_evidence / 'run-result.json')
    original_unit = unit_state('pr13-cap-' + REUSE)
    require(original_unit['MainPID'] == 0 and original_unit['ExecMainStatus'] == 1
            and original_unit['ActiveState'] not in ('active', 'activating', 'deactivating', 'reloading')
            and original_result['ok'] is False and original_result['failed_prefix_retained'] is True,
            'Original R1 failed driver must be terminal and retained; no rerun')
    require(all(sha(old_evidence / name) == expected for name, expected in R1_TOOL_SHA.items()),
            'Frozen R1 tool originals changed')
    prior_manifest = read(args.pilot_delivery_manifest)
    prior_receipt = read(args.pilot_backup_receipt)
    require(prior_manifest['attempt'] == REUSE and prior_receipt['ok'] is True
            and prior_receipt['attempt'] == REUSE
            and prior_receipt['manifest_sha256'] == sha(args.pilot_delivery_manifest)
            and prior_receipt['members_verified'] == len(prior_manifest['files'])
            and all(prior_receipt[field] is True for field in ('archive_gzip_CRC_verified',
                 'all_original_members_sha256_verified', 'inner_gzip_CRC_raw_SHA_counts_verified'))
            and prior_receipt['native_encounters_verified'] == 12
            and re.match(r'^[Gg]:[\\/]', prior_receipt['local_archive']),
            'Failed R1 complete original G archive proof required before separately adopting passed native prefix')
    pilot_dir = old_work / 'outputs' / family_name(PILOT)
    prior_files = {row['source']: row for row in prior_manifest['files']}
    require(len(prior_files) == len(prior_manifest['files']), 'Duplicate original failed manifest source')
    old_bootstrap = BASE / 'evidence/tuning-current-equivalence-bootstrap-r1-20261011'
    for row in prior_manifest['files']:
        original = Path(row['source'])
        require(original.is_relative_to(old_evidence) or original.is_relative_to(old_work)
                or original.is_relative_to(old_bootstrap),
                'Original R1 source member escapes fixed failed attempt')
        require(original.is_file() and not original.is_symlink() and original.resolve(strict=True) == original
                and original.stat().st_nlink == 1 and original.stat().st_size == row['bytes']
                and sha(original) == row['sha256'], 'Failed R1 complete original differs from G closure')
    prior_inputs = read(old_evidence / 'inputs.json')
    require(prior_inputs['old_source_sha'] == OLD and prior_inputs['current_native_source_sha'] == MIXED
            and prior_inputs['current_release_source_sha'] == CURRENT
            and prior_inputs['related_source_hashes'] == proof['source_hashes']
            and prior_inputs['old_runtime_hashes'] == proof['old_runtime_hashes']
            and prior_inputs['current_runtime_hashes'] == proof['current_runtime_hashes'],
            'R1 original actual source/runtime/preregistration closure differs')
    pilot_files = {}
    for path in sorted(pilot_dir.rglob('*')):
        require(not path.is_symlink() and path.resolve() == path, 'Linked original R1 pilot member')
        if not path.is_file():
            continue
        row = prior_files.get(str(path))
        require(row and path.stat().st_nlink == 1 and path.stat().st_size == row['bytes']
                and sha(path) == row['sha256'], 'R1 original native prefix differs from complete G backup')
        pilot_files[path.relative_to(pilot_dir).as_posix()] = row
    require(pilot_files and 'old/manifest.json' in pilot_files and 'current/manifest.json' in pilot_files
            and 'equivalence.json' not in pilot_files, 'Original failed R1 native prefix differs')
    for name, expected_source in (('old', OLD), ('current', MIXED)):
        summary = read(pilot_dir / name / 'summary.json')
        validation = read(pilot_dir / (name + '-validation.json'))
        require(summary['passed'] is True and summary['source_sha'] == expected_source
                and summary['rows'] == 6 and summary['errors'] == 0 and validation['ok'] is True
                and validation['encounters'] == 6 and len(validation['negative_controls']) == 4
                and all(v['rejected'] is True for v in validation['negative_controls']),
                'Original R1 native/oracle first pair did not pass')
    guard()
    evidence.mkdir()
    work.mkdir()
    (work / 'outputs').mkdir()
    (evidence / 'old-validator.py').write_bytes(old_validator)
    shutil.copyfile(args.comparator, evidence / 'equivalence.py')
    shutil.copyfile(args.plan, evidence / 'preregistration.json')
    shutil.copyfile(args.restoration_proof, evidence / 'restoration-proof.json')
    shutil.copyfile(Path(__file__), evidence / 'runner.py')
    shutil.copyfile(args.pilot_delivery_manifest, evidence / 'R1-delivery-manifest.json')
    shutil.copyfile(args.pilot_backup_receipt, evidence / 'R1-G-backup-receipt.json')
    shutil.copytree(pilot_dir, work / 'outputs' / family_name(PILOT))
    require(all(sha(work / 'outputs' / family_name(PILOT) / name) == row['sha256']
                for name, row in pilot_files.items()), 'Copied R1 original native prefix differs')
    inputs = {'attempt': args.attempt, 'old_source_sha': OLD, 'current_native_source_sha': MIXED,
              'current_release_source_sha': CURRENT, 'image_sha': IMAGE,
              'old_runtime': str(args.old_runtime), 'current_runtime': str(CURRENT_WORK / 'runtime'),
              'old_runtime_hashes': proof['old_runtime_hashes'], 'current_runtime_hashes': proof['current_runtime_hashes'],
              'related_source_hashes': proof['source_hashes'], 'related_source_files': 51,
              'tools': {name: sha(evidence / name) for name in ('old-validator.py', 'equivalence.py', 'preregistration.json', 'restoration-proof.json', 'runner.py', 'R1-delivery-manifest.json', 'R1-G-backup-receipt.json')},
              'revision': 2, 'reused_pilot_attempt': REUSE, 'reused_pilot_native_sets': 2,
              'reused_pilot_unique_native_encounters': 12,
              'reused_pilot_member_hashes': {name: row['sha256'] for name, row in pilot_files.items()},
              'systemd_unit': 'pr13-cap-' + args.attempt, 'families': [list(f) for f in families()],
              'samples_per_arm': 3, 'block_index': 0, 'seed_start': 420001, 'seed_end': 420003,
              'output_budget_bytes': BUDGET, 'metadata_reserve_bytes': METADATA,
              'native_family_deadline_seconds': 180, 'total_deadline_seconds': 2400,
              'memory_limit_bytes': MEMORY, 'memory_floor_bytes': FLOOR, 'root_free_ratio_floor': .15,
              'old_216000_relabelled': False, 'whole_experiment_complete': False, 'main_acceptance_granted': False}
    write(evidence / 'inputs.json', inputs)
    write(evidence / 'prepare-result.json', {'ok': True, 'attempt': args.attempt, 'inputs_sha256': sha(evidence / 'inputs.json'),
                                           'related_source_files': 51, 'native_dispatched': False})
    return {'ok': True, 'attempt': args.attempt, 'inputs_sha256': sha(evidence / 'inputs.json'), 'native_dispatched': False}


def frozen(attempt):
    evidence, work = paths(attempt)
    inputs = read(evidence / 'inputs.json')
    require(inputs['old_source_sha'] == OLD and inputs['current_native_source_sha'] == MIXED
            and inputs['current_release_source_sha'] == CURRENT and inputs['families'] == [list(f) for f in families()], 'Frozen input scope differs')
    require(all(sha(evidence / name) == expected for name, expected in inputs['tools'].items()), 'Frozen gate tools changed')
    require(runtime_hashes(Path(inputs['old_runtime'])) == inputs['old_runtime_hashes']
            and runtime_hashes(Path(inputs['current_runtime'])) == inputs['current_runtime_hashes'], 'Frozen actual runtime bytes changed')
    require(all(sha(CURRENT_WORK / 'source' / name) == value for name, value in inputs['related_source_hashes'].items()),
            'Frozen related source bytes changed')
    if (work / 'outputs').exists():
        require(all(sha(work / 'outputs' / family_name(PILOT) / name) == value
                    for name, value in inputs['reused_pilot_member_hashes'].items()),
                'Preserved R1 native bytes/failed comparison logs changed')
    return evidence, work, inputs


INNER = '''import json,os,subprocess,sys
from pathlib import Path
commands=json.loads(sys.argv[1]);out=Path('/output')
for name,args in commands:
 with (out/(name+'.log')).open('x') as f:
  done=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=180)
 if done.returncode:sys.exit(done.returncode)
'''


def run(args):
    host()
    evidence, work, inputs = frozen(args.attempt)
    owner = inputs['systemd_unit']
    exclusive(owner)
    hold = read(BASE / 'evidence/pool-render-segments-r3/scheduling-hold.json')
    require(hold['active'] is True and hold['owner'] == owner, 'Exact root-owned pool scheduling hold required')
    # The live systemd lease stops future cap dispatches, while this shared lock
    # proves no earlier prepared/ended cap unit is awaiting G delivery/cleanup.
    import fcntl
    with (BASE / 'evidence/shared-resource-coordination.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        exclusive(owner)
        for path in (BASE / 'evidence/cap-experiment-full-r3/units').glob('*/resource-reservation.json'):
            marker = read(path)
            require(marker.get('status') == 'Ended' and marker.get('G_backup_verified') is True
                    and marker.get('output_cleaned') is True, 'Earlier cap original awaits terminal G delivery/cleanup')
    require(not (evidence / 'run-started.json').exists() and not (evidence / 'run-result.json').exists(),
            'Uncertain or ended native attempt cannot restart')
    require({p.name for p in (work / 'outputs').iterdir()} == {family_name(PILOT)},
            'Only exact separately adopted R1 pilot prefix may preexist')
    guard(work, start=True)
    write(evidence / 'run-started.json', {'owner': owner, 'at': time.time(), 'inputs_sha256': sha(evidence / 'inputs.json'),
                                       'runner_pid': os.getpid(), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
    result = {'ok': False, 'attempt': args.attempt, 'old_source_sha': OLD, 'current_native_source_sha': MIXED,
              'current_release_source_sha': CURRENT, 'families_completed': 0, 'comparisons': [],
              'total_unique_native_encounters': 0, 'old_216000_relabelled': False, 'main_acceptance_granted': False}
    result.update(revision=2, reused_R1_native_encounters=12, new_native_encounters=0,
                  original_R1_failed_comparison_preserved=True)
    active_cid = None
    deadline = time.monotonic() + inputs['total_deadline_seconds']
    try:
        for index, family in enumerate(families()):
            require(time.monotonic() < deadline, 'Total explicit gate deadline exceeded; original prefix retained')
            family_id = family_name(family)
            output = work / 'outputs' / family_id
            require(output.is_dir() if index == 0 else not output.exists(),
                    'Only first exact adopted pilot output may preexist; no native restart')
            guard(work)
            if index:
                output.mkdir()
            dimensions = ['--hero', family[0], '--group', family[1], '--replacement', family[2],
                          '--block-index', '0', '--samples', '3']
            commands = []
            if index:
                for name, source in (('old', OLD), ('current', MIXED)):
                    commands.append((name + '-native', ['dotnet', '/' + name + '/FantasyCard.Numerics.dll',
                        '--tuning-recovery-experiment', '--source-sha', source, '--output', '/output/' + name, *dimensions]))
                    commands.append((name + '-validation', ['python3', '/gate/old-validator.py', '--input', '/output/' + name,
                        '--source-sha', source, '--output', '/output/' + name + '-validation.json', '--controls']))
            commands.append(('r2-equivalence', ['python3', '/gate/equivalence.py', '--original', '/output/old', '--current', '/output/current',
                '--hero', family[0], '--group', family[1], '--replacement', family[2], '--controls', '--output', '/output/equivalence.json']))
            container_owner = owner + '-' + str(index)
            require(container_owner not in docker('ps', '-a', '--format', '{{.Names}}').stdout.decode().splitlines(),
                    'Existing native container may not restart')
            active_cid = docker('create', '--name', container_owner, '--label', 'codex.owner=' + container_owner,
                '--memory', '950m', '--cpus', '1', '--network', 'none', '--user', '1000:1000', '--read-only',
                '--tmpfs', '/tmp:rw,nosuid,size=64m', '-e', 'PR13_TUNING_EQ_CONTAINER=1',
                '-e', 'DOTNET_CLI_HOME=/tmp', '-e', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1',
                '-e', 'DOTNET_EnableDiagnostics=0',
                '-v', inputs['old_runtime'] + ':/old:ro', '-v', inputs['current_runtime'] + ':/current:ro',
                '-v', str(evidence) + ':/gate:ro', '-v', str(output) + ':/output',
                IMAGE, 'python3', '-c', INNER, json.dumps(commands)).stdout.decode().strip()
            require(re.fullmatch('[0-9a-f]{64}', active_cid), 'Full native container ID missing')
            write(evidence / (family_id + '-started.json'), {'family': list(family), 'container_id': active_cid,
                 'container_owner': container_owner, 'systemd_unit': owner, 'at': time.time(), 'pilot': index == 0})
            docker('start', active_cid)
            family_deadline = time.monotonic() + 6 * 180
            while True:
                state = owned_container(active_cid, container_owner)
                if not state['State']['Running']:
                    break
                guard(work)
                require(time.monotonic() < min(deadline, family_deadline), 'Declared family/total deadline reached; prefix retained')
                time.sleep(1)
            require(state['State']['ExitCode'] == 0 and state['State']['OOMKilled'] is False, 'Native/independent exact gate failed')
            comparison = read(output / 'equivalence.json')
            validations = {name: read(output / (name + '-validation.json')) for name in ('old', 'current')}
            require(comparison['ok'] is True and comparison['family'] == list(family)
                    and comparison['encounters_per_source'] == 6 and comparison['unique_native_encounters'] == 12
                    and len(comparison['negative_controls']) == 13 and all(v['rejected'] is True for v in comparison['negative_controls'])
                    and comparison['opaque_identity_paths'] == ['Actual.BattleId', 'Actual.AttackerId']
                    and comparison['opaque_ID_global_noalias_verified'] is True,
                    'Exact reconciliation or meaningful identity/business corruption controls failed')
            require(all(v['ok'] is True and v['encounters'] == 6 and v['pairs'] == 3
                        and len(v['negative_controls']) == 4 and all(c['rejected'] is True for c in v['negative_controls'])
                        for v in validations.values()), 'Original four business oracle controls failed')
            guard(work)
            logs = docker('logs', active_cid)
            content = logs.stdout + logs.stderr
            require(len(content) <= 1024**2, 'Native family log budget exceeded')
            (output / 'r2-container.log').write_bytes(content)
            docker('rm', '-v', active_cid)
            active_cid = None
            family_result = {'ok': True, 'family': list(family), 'pilot': index == 0,
                'comparison': comparison, 'validations': validations, 'owned_container_removed': True,
                'native_reused_from_R1': index == 0, 'new_unique_native_encounters': 0 if index == 0 else 12,
                'original_output_directory': str(output), 'equivalence_sha256': sha(output / 'equivalence.json')}
            write(evidence / (family_id + '-result.json'), family_result)
            result['comparisons'].append(comparison)
            result['families_completed'] += 1
            result['total_unique_native_encounters'] += 12
            result['new_native_encounters'] += 0 if index == 0 else 12
            if index == 0:
                write(evidence / 'pilot-gate.json', {'ok': True, 'family': list(family), 'originals_reused_in_matrix': True,
                                                  'equivalence_sha256': sha(output / 'equivalence.json')})
        frozen(args.attempt)
        require(result['families_completed'] == 36 and result['total_unique_native_encounters'] == 432, 'Complete limited matrix denominator differs')
        owners, semantic = {}, set()
        for comparison in result['comparisons']:
            for row in comparison['opaque_ID_bijection_rows']:
                key = tuple(row['semantic_encounter']) + (row['field'],)
                require(key not in semantic and row['field'] in ('BattleId', 'AttackerId'),
                        'Duplicate or undeclared opaque semantic encounter identity')
                semantic.add(key)
                for side in ('old_UUID', 'current_UUID'):
                    owner_key = (side, row['field'], row[side])
                    require(owner_key not in owners, 'Opaque UUID alias across complete 36-family matrix')
                    owners[owner_key] = key
        require(len(semantic) == 432 and len(owners) == 864,
                'Complete two-namespace opaque encounter bijection denominator differs')
        result.update(ok=True, old_encounters=216, current_encounters=216, initial_pilot_reused_in_matrix=True,
                      source_and_runtime_unchanged=True, numeric_tolerance_used=False, whole_experiment_complete=False,
                      global_36_family_opaque_noalias_verified=True, opaque_semantic_ID_pairs_verified=len(semantic))
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error), failed_prefix_retained=True)
    finally:
        if active_cid:
            try:
                state = json.loads(docker('inspect', active_cid).stdout)[0]
                require(state['Id'] == active_cid and state['Config']['Labels'].get('codex.owner', '').startswith(owner + '-'),
                        'Cleanup exact failed container ownership differs')
                if state['State']['Running']:
                    docker('stop', '--time', '5', active_cid)
                logs = docker('logs', active_cid)
                require(len(logs.stdout) + len(logs.stderr) <= 1024**2, 'Failed native log budget exceeded')
                (evidence / 'failed-container.log').write_bytes(logs.stdout + logs.stderr)
                docker('rm', '-v', active_cid)
                result['failed_owned_container_removed'] = True
            except Exception as error:
                result.update(ok=False, finalization_error=type(error).__name__, finalization_detail=str(error))
        write(evidence / 'run-result.json', result)
    return result


def terminal(attempt):
    evidence, work, inputs = frozen(attempt)
    state = unit_state(inputs['systemd_unit'])
    require(state['MainPID'] == 0 and state['ExecMainStatus'] == 0
            and state['ActiveState'] not in ('active', 'activating', 'deactivating', 'reloading'),
            'Exact native driver must be successfully terminal before delivery/cleanup')
    return evidence, work, inputs


def delivery(args):
    host()
    evidence, work, inputs = terminal(args.attempt)
    result = read(evidence / 'run-result.json')
    require(result['ok'] is True and result['families_completed'] == 36
            and result['total_unique_native_encounters'] == 432, 'Successful complete limited gate required')
    active_bind_guard((work, evidence))
    files = []
    for root, prefix in ((evidence, 'metadata'), (work, 'persistent')):
        for path in sorted(root.rglob('*')):
            require(not path.is_symlink(), 'Linked delivery member')
            if not path.is_file() or (root == evidence and path.name in MUTABLE):
                continue
            require(path.resolve() == path and path.stat().st_nlink == 1, 'Nonordinary delivery member')
            files.append({'source': str(path), 'path': prefix + '/' + path.relative_to(root).as_posix(),
                          'bytes': path.stat().st_size, 'sha256': sha(path)})
    manifest = {'schema_version': 1, 'kind': 'tuning-current-equivalence', 'attempt': args.attempt,
                'old_source_sha': OLD, 'current_native_source_sha': MIXED, 'current_release_source_sha': CURRENT,
                'inputs_sha256': sha(evidence / 'inputs.json'), 'families': 36, 'old_encounters': 216,
                'current_encounters': 216, 'total_unique_native_encounters': 432, 'files': files,
                'old_216000_relabelled': False, 'main_acceptance_granted': False}
    target = evidence / 'delivery-manifest.json'
    if target.exists():
        require(read(target) == manifest, 'Existing original delivery manifest differs')
    else:
        write(target, manifest)
    return {'ok': True, 'manifest': str(target), 'manifest_sha256': sha(target), 'members': len(files),
            'bytes': sum(f['bytes'] for f in files), 'cloud_archive_created': False}


def cleanup(args):
    host()
    evidence, work, inputs = terminal(args.attempt)
    require(read(evidence / 'run-result.json')['ok'] is True, 'Failed originals cannot be cleaned')
    manifest = read(evidence / 'delivery-manifest.json')
    receipt = read(args.backup_receipt)
    require(receipt['ok'] is True and receipt['kind'] == manifest['kind'] and receipt['attempt'] == args.attempt
            and receipt['manifest_sha256'] == sha(evidence / 'delivery-manifest.json')
            and receipt['old_source_sha'] == OLD and receipt['current_native_source_sha'] == MIXED
            and receipt['current_release_source_sha'] == CURRENT
            and receipt['members_verified'] == len(manifest['files'])
            and all(receipt[field] is True for field in ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
                'inner_gzip_CRC_raw_SHA_counts_verified', 'no_native_business_executed_locally'))
            and receipt['families_verified'] == 36 and receipt['unique_encounters_verified'] == 432
            and re.match(r'^[Gg]:[\\/]', receipt['local_archive']) and receipt['bytes'] > 0
            and re.fullmatch('[0-9a-f]{64}', receipt['sha256']), 'Complete G original-byte proof required')
    output = work / 'outputs'
    require(output.resolve(strict=True) == output and output.is_relative_to(BASE / 'work') and not output.is_symlink(),
            'Cleanup target is not exact owned output directory')
    active_bind_guard((output,))
    expected = {f['source']: f for f in manifest['files'] if f['path'].startswith('persistent/outputs/')}
    actual = {}
    allocated = 0
    for path in output.rglob('*'):
        require(not path.is_symlink() and path.resolve() == path, 'Linked cleanup member')
        if not path.is_file():
            continue
        row = expected.get(str(path))
        require(row and path.stat().st_nlink == 1 and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Passed original changed after G backup')
        actual[str(path)] = row
        allocated += path.stat().st_blocks * 512
    require(actual and set(actual) == set(expected), 'Unlisted/absent passed output original')
    saved = evidence / 'local-backup-receipt.json'
    if saved.exists():
        require(read(saved) == receipt, 'Existing G receipt differs')
    else:
        shutil.copyfile(args.backup_receipt, saved)
    health()
    before = os.statvfs(BASE)
    shutil.rmtree(output)
    after = os.statvfs(BASE)
    health()
    result = {'ok': True, 'attempt': args.attempt, 'output_removed': str(output), 'allocated_bytes_removed': allocated,
              'root_disk_bytes_reclaimed': (after.f_bavail - before.f_bavail) * after.f_frsize,
              'local_G_archive_sha256': receipt['sha256'], 'local_G_archive_bytes': receipt['bytes'],
              'runtime_and_retained_metadata_preserved': True, 'failed_originals_retained': True,
              'pool_hold_release_owned_by_root_dispatcher': True, 'main_acceptance_granted': False}
    write(evidence / 'local-storage-cleanup.json', result)
    return result


def status(args):
    host()
    evidence, work = paths(args.attempt)
    result = {'ok': True, 'attempt': args.attempt, 'native_never_restarted': True, 'main_acceptance_granted': False}
    for name in ('prepare-result.json', 'run-started.json', 'pilot-gate.json', 'run-result.json', 'local-storage-cleanup.json'):
        result[name] = read(evidence / name) if (evidence / name).exists() else None
    result['native_systemd_unit'] = unit_state('pr13-cap-' + args.attempt) if (evidence / 'run-started.json').exists() else {'not_dispatched': True}
    result['completed_family_results'] = len(list(evidence.glob('*-B0-result.json')))
    result['original_output_bytes'] = sum(p.stat().st_size for p in (work / 'outputs').rglob('*') if p.is_file())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('prepare', 'run', 'status', 'prepare-delivery', 'cleanup-passed'))
    p.add_argument('--attempt', required=True)
    p.add_argument('--old-runtime', type=Path)
    p.add_argument('--restoration-proof', type=Path)
    p.add_argument('--plan', type=Path)
    p.add_argument('--comparator', type=Path)
    p.add_argument('--backup-receipt', type=Path)
    p.add_argument('--pilot-delivery-manifest', type=Path)
    p.add_argument('--pilot-backup-receipt', type=Path)
    a = p.parse_args()
    # Short metadata mutations share the queue lock. Native run releases the lock
    # before starting and holds its exact live systemd lease throughout execution.
    if a.phase == 'run':
        result = run(a)
    elif a.phase == 'status':
        result = status(a)
    else:
        host()
        import fcntl
        with (BASE / 'evidence/shared-resource-coordination.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = {'prepare': prepare, 'prepare-delivery': delivery, 'cleanup-passed': cleanup}[a.phase](a)
    print(json.dumps(result))
    if result.get('ok') is not True:
        sys.exit(1)


if __name__ == '__main__':
    main()
