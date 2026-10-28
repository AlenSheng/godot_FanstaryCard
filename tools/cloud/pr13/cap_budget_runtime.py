"""Cloud-only compilation and original/default/16 GiB collector pilot gate.

The 372-file mixed source has exactly two overrides of B042: collector and
validator. Domain code is unchanged. A real mixed Git commit must exist.
No full experiment dispatch is implemented. prepare/build/pilot are separate
explicit actions; uncertain or ended attempts never automatically restart.
Source/runtime/pilot originals persist until their complete verified G backup.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

if '_container-build' in sys.argv:
    _helper_path = Path('/ram/recovery.py')
else:
    _helper_path = Path(os.environ.get('PR13_CAP_RECOVERY_HELPER', str(Path(__file__).with_name('recovery-helper.py'))))
    if not _helper_path.is_file():
        _helper_path = Path(__file__).with_name('cap_runtime_recovery.py')
if not _helper_path.is_file():
    raise RuntimeError('Fixed recovery helper missing; deploy it adjacent as recovery-helper.py')
_spec = importlib.util.spec_from_file_location('pr13_fixed_recovery_helper', _helper_path)
recovery = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recovery)


BASE = recovery.BASE
GIT = recovery.GIT
BUSINESS = recovery.SOURCE_SHA
IMAGE = recovery.IMAGE
REVISION = 'cap-effective-raw-budget-v2'
OVERRIDES = ('server/tools/FantasyCard.Numerics/CapEffectiveExperiment.cs',
             'tools/pr13_cap_effective_experiment.py')
EQUIVALENCE = 'tools/pr13_cap_collector_equivalence.py'
RAW_DEFAULT = 2 * 1024**3
RAW_RAISED = 16 * 1024**3
DOMAIN_HASHES = {k: v for k, v in recovery.RUNTIME_HASHES.items() if k.startswith('FantasyCard.Domain.')}
METADATA_RESERVE = 16 * 1024**2
PILOT_BUDGET = 64 * 1024**2
MONITOR = '2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return recovery.digest(path)


def write(path, value):
    require(not path.exists(), 'Existing attempt evidence cannot be overwritten: ' + str(path))
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def read(path):
    require(path.is_file() and not path.is_symlink(), 'Missing/linked frozen metadata')
    return json.loads(path.read_text(encoding='utf-8'))


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, check=True, timeout=timeout)


def docker(*args):
    return command(['sudo', '-n', 'docker', *args])


def paths(attempt):
    require(re.fullmatch(r'cap-budget-runtime-r[1-9][0-9]*-[0-9]{8}', attempt), 'Fresh named budget runtime attempt required')
    return BASE / 'evidence' / attempt, BASE / 'work' / attempt, Path('/dev/shm') / ('pr13-' + attempt)


def host(root):
    require(root == BASE and os.name != 'nt' and sys.platform.startswith('linux')
            and BASE.is_dir() and GIT.is_dir(), 'Fixed Tencent Linux acceptance host only')


def guard(root_bytes=METADATA_RESERVE, memory_bytes=0, scratch_bytes=0):
    recovery.guard(root_bytes=root_bytes, memory_bytes=memory_bytes, scratch_bytes=scratch_bytes)
    recovery.health()


def no_jobs(owner):
    own = os.environ.get('PR13_BUDGET_SYSTEMD_UNIT', '')
    require(not own or own == owner, 'Own systemd identity differs from explicit native phase')
    rows = command(['systemctl', 'list-units', '--state=running', '--no-legend', '--plain',
                    'pr13-cap-*', 'pr13-pool-segment-*']).stdout.decode().splitlines()
    require(not any(row.split()[0].removesuffix('.service') != own for row in rows if row.split()),
            'An exact cloud cap/render job is live; no new native phase is dispatched')
    names = docker('ps', '--format', '{{.Names}}').stdout.decode().splitlines()
    require(not any(name.startswith(('pr13-cap-', 'pr13-pool-segment-')) for name in names),
            'A cloud cap/render container is live')
    require(owner not in docker('ps', '-a', '--format', '{{.Names}}').stdout.decode().splitlines(),
            'Existing native phase container must not restart')


def unit_state(unit):
    completed = subprocess.run(['systemctl', 'show', unit,
        '--property=MainPID,ActiveState,SubState,LoadState,ExecMainStatus'],
        capture_output=True, text=True, timeout=15)
    values = dict(line.split('=', 1) for line in completed.stdout.splitlines() if '=' in line)
    require(completed.returncode == 0 and all(key in values for key in (
        'MainPID', 'ActiveState', 'SubState', 'LoadState', 'ExecMainStatus'))
        and values['MainPID'].isdigit() and values['ExecMainStatus'].isdigit(),
        'Exact native systemd observation incomplete; preserve uncertainty and never restart')
    return {'unit': unit, **{key: int(values[key]) for key in ('MainPID', 'ExecMainStatus')},
            **{key: values[key] for key in ('ActiveState', 'SubState', 'LoadState')}}


def terminal_phases(attempt):
    for phase in ('build', 'pilot'):
        state = unit_state('pr13-' + attempt + '-' + phase)
        require(state['MainPID'] == 0 and state['ExecMainStatus'] == 0
                and state['ActiveState'] not in ('active', 'activating', 'deactivating', 'reloading'),
                'Exact native build/pilot driver must be successful and terminal')


def no_active_bind(targets):
    running = docker('ps', '-q', '--no-trunc').stdout.decode().splitlines()
    for cid in running:
        require(re.fullmatch('[0-9a-f]{64}', cid), 'Full active container identity required')
        state = json.loads(docker('inspect', cid).stdout)[0]
        require(state['Id'] == cid, 'Active container inspection identity changed')
        for mount in state.get('Mounts', []):
            require(mount.get('Type') in ('bind', 'volume', 'tmpfs'), 'Unknown active mount type')
            if mount['Type'] != 'bind':
                continue
            if cid == MONITOR and mount.get('Source') == '/' and mount.get('RW') is False:
                continue
            source = Path(mount['Source']).resolve()
            require(not any(source == target or source.is_relative_to(target) or target.is_relative_to(source)
                            for target in targets), 'An active container bind intersects frozen delivery/cleanup originals')


def source_blob(revision, path):
    return command(['git', '-C', str(GIT), 'show', revision + ':' + path]).stdout


def prepare(args):
    host(args.root)
    evidence, work, scratch = paths(args.attempt)
    require(not evidence.exists() and not work.exists() and not scratch.exists(), 'Existing attempt cannot be replaced')
    for value in (args.mixed_source_sha, args.instrumentation_source_sha):
        require(re.fullmatch('[0-9a-f]{40}', value or ''), 'Real exact Git provenance SHA required')
    require(args.mixed_source_sha != BUSINESS, 'Collector instrumentation must have a distinct mixed source')
    original_raw, original_hashes = recovery.source_contract()
    changes = command(['git', '-C', str(GIT), 'diff', '--name-only', '--no-renames', BUSINESS, args.mixed_source_sha]).stdout.decode().splitlines()
    require(set(changes) == set(OVERRIDES) and len(changes) == 2, 'Mixed Git tree must change exactly collector and validator')
    parents = [line.split()[1] for line in command(['git', '-C', str(GIT), 'cat-file', '-p', args.mixed_source_sha]).stdout.decode().split('\n\n', 1)[0].splitlines() if line.startswith('parent ')]
    require(parents == [BUSINESS], 'Mixed source must have B042 as its sole parent')
    blobs = {}
    for name, original_sha in original_hashes.items():
        content = source_blob(args.mixed_source_sha, name)
        digest = hashlib.sha256(content).hexdigest()
        if name in OVERRIDES:
            require(content == source_blob(args.instrumentation_source_sha, name) and digest != original_sha,
                    'Mixed override must match exact instrumentation Git bytes')
        else:
            require(digest == original_sha, 'One of the original 370 business/source files changed')
        blobs[name] = content
    extra = source_blob(args.instrumentation_source_sha, EQUIVALENCE)
    needed = sum(map(len, blobs.values())) + sum(len(source_blob(BUSINESS, name)) for name in OVERRIDES)
    guard(root_bytes=needed + 64 * 1024**2)
    no_jobs('pr13-' + args.attempt + '-prepare')
    evidence.mkdir()
    work.mkdir()
    (work / 'source').mkdir()
    for name, content in blobs.items():
        path = work / 'source' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for name in OVERRIDES:
        path = work / 'original-overrides' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source_blob(BUSINESS, name))
    (evidence / 'equivalence.py').write_bytes(extra)
    shutil.copyfile(Path(__file__), evidence / 'runner.py')
    shutil.copyfile(Path(recovery.__file__), evidence / 'recovery-helper.py')
    overrides = {name: {'original_sha256': original_hashes[name],
                        'mixed_sha256': hashlib.sha256(blobs[name]).hexdigest(),
                        'instrumentation_source_sha': args.instrumentation_source_sha} for name in OVERRIDES}
    inputs = {'schema_version': 2, 'attempt': args.attempt, 'source_sha': args.mixed_source_sha,
        'business_source_sha': BUSINESS, 'instrumentation_source_sha': args.instrumentation_source_sha,
        'source_publication_state_at_preparation': args.source_publication_state,
        'source_files': 372, 'source_hashes': {name: hashlib.sha256(data).hexdigest() for name, data in blobs.items()},
        'original_source_hashes': original_hashes, 'original370_inputs_unchanged': True,
        'exact_two_overrides_match_instrumentation_Git_bytes': True, 'override_paths': list(OVERRIDES),
        'override_hashes': overrides, 'original_input_manifest_sha256': hashlib.sha256(original_raw).hexdigest(),
        'original_2068_directory_restored': False, 'Domain_business_sources_unchanged': True,
        'source_path': str(work / 'source'), 'runtime_path': str(work / 'runtime'),
        'extra_tools_not_counted_in_372': {'equivalence.py': sha(evidence / 'equivalence.py'),
            'runner.py': sha(evidence / 'runner.py'), 'recovery-helper.py': sha(evidence / 'recovery-helper.py')},
        'image_sha': IMAGE, 'SDK': recovery.SDK, 'original_runtime_hashes': recovery.RUNTIME_HASHES,
        'required_Domain_hashes': DOMAIN_HASHES, 'collector_revision': REVISION,
        'memory_floor_bytes': 500000000, 'root_free_ratio_floor': .15,
        'native_default_raw_bytes': RAW_DEFAULT, 'declared_pilot_raised_raw_bytes': RAW_RAISED,
        'full_unit_dispatch_permitted': False, 'whole_task_accepted': False}
    write(evidence / 'inputs.json', inputs)
    result = {'ok': True, 'attempt': args.attempt, 'source_sha': args.mixed_source_sha,
              'mixed_input_manifest_sha256': sha(evidence / 'inputs.json'), 'source_files': 372,
              'native_compilation_dispatched': False, 'large_experiment_dispatched': False,
              'whole_task_accepted': False}
    write(evidence / 'prepare-result.json', result)
    return result


def frozen(attempt):
    evidence, work, scratch = paths(attempt)
    inputs = read(evidence / 'inputs.json')
    require(inputs['source_files'] == len(inputs['source_hashes']) == 372
            and inputs['business_source_sha'] == BUSINESS and inputs['override_paths'] == list(OVERRIDES), 'Frozen mixed inputs differ')
    require(all(sha(work / 'source' / path) == expected for path, expected in inputs['source_hashes'].items()), 'Mixed source bytes changed')
    require(all(sha(evidence / name) == expected for name, expected in inputs['extra_tools_not_counted_in_372'].items()), 'Frozen runner/equivalence tools changed')
    require(all(sha(work / 'original-overrides' / path) == inputs['original_source_hashes'][path] for path in OVERRIDES), 'Original B042 overrides changed')
    return evidence, work, scratch, inputs


def owned(cid, owner):
    state = json.loads(docker('inspect', cid).stdout)[0]
    require(state['Id'] == cid and state['Config']['Labels'].get('codex.owner') == owner, 'Exact native container ownership differs')
    return state


def wait_container(cid, owner, seconds):
    deadline = time.monotonic() + seconds
    while True:
        state = owned(cid, owner)
        if not state['State']['Running']:
            return state
        guard()
        require(time.monotonic() < deadline, 'Native phase deadline reached; partial evidence retained')
        time.sleep(5)


def build(args):
    host(args.root)
    evidence, work, scratch, inputs = frozen(args.attempt)
    owner = 'pr13-' + args.attempt + '-build'
    require(not scratch.exists() and not (evidence / 'build-started.json').exists()
            and not (evidence / 'build-result.json').exists() and not (work / 'runtime').exists(), 'Native build cannot restart')
    no_jobs(owner)
    guard(root_bytes=64 * 1024**2, memory_bytes=(950 + 512) * 1024**2, scratch_bytes=256 * 1024**2)
    write(evidence / 'build-started.json', {'owner': owner, 'at': time.time(), 'source_sha': inputs['source_sha']})
    scratch.mkdir()
    shutil.copytree(work / 'source', scratch / 'source')
    shutil.copyfile(evidence / 'runner.py', scratch / 'runner.py')
    shutil.copyfile(evidence / 'recovery-helper.py', scratch / 'recovery.py')
    cid = None
    result = {'ok': False, 'attempt': args.attempt, 'source_sha': inputs['source_sha'],
              'business_source_sha': BUSINESS, 'instrumentation_source_sha': inputs['instrumentation_source_sha'],
              'mixed_input_manifest_sha256': sha(evidence / 'inputs.json'), 'whole_task_accepted': False,
              'full_unit_dispatch_permitted': False, 'domain_original_hashes': DOMAIN_HASHES,
              'container_build_path': '/work', 'container_runtime_output': '/ram/runtime',
              'path_matches_successful_original_recovery': True, 'new_global_PathMap_override': False}
    try:
        cid = docker('create', '--name', owner, '--label', 'codex.owner=' + owner,
            '--memory', '950m', '--cpus', '1', '--network', 'none', '--user', '1000:1000',
            '-e', 'PR13_RECOVERY_CONTAINER=1', '-v', str(scratch / 'source') + ':/work',
            '-v', str(scratch) + ':/ram', '-v', str(BASE / 'cache') + ':/cache:ro',
            IMAGE, 'python3', '/ram/runner.py', '_container-build').stdout.decode().strip()
        require(re.fullmatch('[0-9a-f]{64}', cid), 'Exact created build container ID missing')
        docker('start', cid)
        state = wait_container(cid, owner, 700)
        result.update(exit_code=state['State']['ExitCode'], oom_killed=state['State']['OOMKilled'])
        require(result['exit_code'] == 0 and not result['oom_killed'], 'Native compilation or 56 regressions failed')
        hashes = {path.name: sha(path) for path in (scratch / 'runtime').iterdir() if path.is_file()}
        require(set(hashes) == set(recovery.RUNTIME_HASHES), 'Native runtime file set differs')
        result['runtime_hashes'] = hashes
        result['domain_hashes_identical_to_original'] = all(hashes[name] == value for name, value in DOMAIN_HASHES.items())
        require(result['domain_hashes_identical_to_original'], 'Actual Domain DLL/PDB/deps hashes must equal originals')
        result['numerics_hashes_actual'] = {name: value for name, value in hashes.items() if name not in DOMAIN_HASHES}
        result['runtime_identical_to_original'] = hashes == recovery.RUNTIME_HASHES
        require(not result['runtime_identical_to_original'], 'Instrumented Numerics runtime must be a declared new build')
        counters = ET.parse(scratch / 'test-results/cap-runtime-recovery.trx').find('.//{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters')
        require(counters is not None, 'Native regression TRX missing')
        counts = {key: int(value) for key, value in counters.attrib.items()}
        result['domain_regression_counters'] = counts
        result['domain_regression_exact_56_passed'] = counts.get('total') == counts.get('passed') == 56 and counts.get('failed') == 0
        require(result['domain_regression_exact_56_passed'], 'Exactly 56 original regressions must pass')
        frozen(args.attempt)
        result['source_inputs_unchanged'] = True
        guard(root_bytes=16 * 1024**2)
        shutil.copytree(scratch / 'runtime', work / 'runtime')
        require({path.name: sha(path) for path in (work / 'runtime').iterdir()} == hashes, 'Persisted new runtime differs')
        result.update(ok=True, runtime_path=str(work / 'runtime'), source_path=str(work / 'source'))
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
    finally:
        try:
            content = b''
            if cid:
                if owned(cid, owner)['State']['Running']:
                    docker('stop', '--time', '5', cid)
                require(not owned(cid, owner)['State']['Running'], 'Owned failed build did not stop')
                logs = docker('logs', cid)
                content = logs.stdout + logs.stderr
                require(len(content) <= 4 * 1024**2, 'Build log exceeds persistent budget')
            diagnostics = []
            for name in ('compile.log', 'help.log', 'domain.log', 'sdk.json', 'test-results/cap-runtime-recovery.trx'):
                source = scratch / name
                if source.exists():
                    require(source.stat().st_size <= 4 * 1024**2, 'Build diagnostic budget exceeded')
                    diagnostics.append(source)
            aggregate = len(content) + sum(path.stat().st_size for path in diagnostics)
            require(aggregate <= 24 * 1024**2, 'Aggregate build diagnostics exceed 24 MiB; originals retained')
            require(not (evidence / 'build-container.log').exists()
                    and not any((evidence / path.name).exists() for path in diagnostics), 'Original build diagnostic would be overwritten')
            guard(root_bytes=aggregate + (len(diagnostics) + 1) * 4096 + 128 * 1024 + METADATA_RESERVE)
            if cid:
                (evidence / 'build-container.log').write_bytes(content)
            for source in diagnostics:
                shutil.copyfile(source, evidence / source.name)
            if cid:
                docker('rm', '-v', cid)
                result['owned_container_removed'] = True
            result['diagnostic_aggregate_bytes'] = aggregate
            result['ok'] = result['ok'] and result.get('owned_container_removed') is True
            result['passed_or_failed_build_scratch_retained_for_G'] = str(scratch)
            guard()
            write(evidence / 'build-result.json', result)
        except Exception as error:
            result.update(ok=False, finalization_error=type(error).__name__, finalization_detail=str(error))
    return result


PILOT_INNER = '''import json,subprocess,sys
from pathlib import Path
commands=json.loads(sys.argv[1]);out=Path('/pilot')
for name,args in commands:
 with (out/(name+'.log')).open('x') as f:
  completed=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=180)
 if completed.returncode:sys.exit(completed.returncode)
'''


def pilot(args):
    host(args.root)
    evidence, work, scratch, inputs = frozen(args.attempt)
    compiled = read(evidence / 'build-result.json')
    require(compiled['ok'] is True and compiled['domain_hashes_identical_to_original'] is True
            and compiled['domain_regression_exact_56_passed'] is True, 'Actual new build gate missing')
    owner = 'pr13-' + args.attempt + '-pilot'
    output = work / 'pilots'
    require(not output.exists() and not (evidence / 'pilot-started.json').exists()
            and not (evidence / 'pilot-result.json').exists(), 'Native pilot cannot restart')
    no_jobs(owner)
    guard(root_bytes=PILOT_BUDGET + METADATA_RESERVE, memory_bytes=950 * 1024**2)
    original = BASE / 'work/cap-runtime-recovery-r1-20261011/runtime'
    require({path.name: sha(path) for path in original.iterdir()} == recovery.RUNTIME_HASHES, 'Original runtime source gate changed')
    require({path.name: sha(path) for path in (work / 'runtime').iterdir()} == compiled['runtime_hashes'], 'New runtime bytes changed')
    output.mkdir()
    write(evidence / 'pilot-started.json', {'owner': owner, 'at': time.time(), 'source_sha': inputs['source_sha']})
    dimensions = ['--hero', 'Mage', '--group', 'E1', '--element', 'Water', '--equipment-level', '5',
                  '--block-index', '0', '--samples', '3']
    provenance = ['--business-source-sha', BUSINESS, '--instrumentation-source-sha', inputs['instrumentation_source_sha'],
                  '--mixed-input-manifest-sha256', sha(evidence / 'inputs.json')]
    commands = []
    for name, new, budget in (('original', False, RAW_DEFAULT), ('new-default', True, RAW_DEFAULT), ('new-16g', True, RAW_RAISED)):
        native = ['dotnet', ('/new/' if new else '/original/') + 'FantasyCard.Numerics.dll', '--cap-effective-experiment',
                  '--source-sha', inputs['source_sha'] if new else BUSINESS, '--output', '/pilot/' + name, *dimensions]
        if new:
            native += provenance
            if name == 'new-16g':
                native += ['--cap-raw-unit-limit-bytes', str(budget)]
        commands.append((name + '-native', native))
        validator = ['python3', '/source/tools/pr13_cap_effective_experiment.py' if new else '/original-tools/tools/pr13_cap_effective_experiment.py',
                     '--input', '/pilot/' + name, '--source-sha', inputs['source_sha'] if new else BUSINESS,
                     '--output', '/pilot/' + name + '-validation.json', '--controls']
        if new:
            validator += provenance + ['--cap-raw-unit-limit-bytes', str(budget), '--collector-revision', REVISION]
        commands.append((name + '-validation', validator))
    commands.append(('equivalence', ['python3', '/extra/equivalence.py', '--original', '/pilot/original',
        '--candidate-default', '/pilot/new-default', '--candidate-16g', '/pilot/new-16g',
        '--mixed-source-sha', inputs['source_sha'], '--instrumentation-source-sha', inputs['instrumentation_source_sha'],
        '--mixed-input-manifest-sha256', sha(evidence / 'inputs.json'), '--controls', '--output', '/pilot/equivalence.json']))
    cid = None
    result = {'ok': False, 'attempt': args.attempt, 'source_sha': inputs['source_sha'], 'business_source_sha': BUSINESS,
              'instrumentation_source_sha': inputs['instrumentation_source_sha'], 'mixed_input_manifest_sha256': sha(evidence / 'inputs.json'),
              'same_three_seed_paired_pilots': True, 'original_raw_bytes': RAW_DEFAULT, 'new_default_raw_bytes': RAW_DEFAULT,
              'new_explicit_raised_raw_bytes': RAW_RAISED, 'whole_task_accepted': False, 'full_unit_dispatch_permitted': False}
    try:
        cid = docker('create', '--name', owner, '--label', 'codex.owner=' + owner, '--memory', '950m', '--cpus', '1',
            '--network', 'none', '--user', '1000:1000', '-v', str(original) + ':/original:ro',
            '-v', str(work / 'runtime') + ':/new:ro', '-v', str(work / 'source') + ':/source:ro',
            '-v', str(work / 'original-overrides') + ':/original-tools:ro', '-v', str(evidence) + ':/extra:ro',
            '-v', str(output) + ':/pilot', IMAGE, 'python3', '-c', PILOT_INNER, json.dumps(commands)).stdout.decode().strip()
        require(re.fullmatch('[0-9a-f]{64}', cid), 'Exact created pilot container ID missing')
        docker('start', cid)
        state = wait_container(cid, owner, 900)
        result.update(exit_code=state['State']['ExitCode'], oom_killed=state['State']['OOMKilled'])
        require(result['exit_code'] == 0 and not result['oom_killed'], 'Native or independent pilot validation/equivalence failed')
        validations = {name: read(output / (name + '-validation.json')) for name in ('original', 'new-default', 'new-16g')}
        require(all(v['ok'] is True and v['encounters'] == 6 and v['pairs'] == 3
                    and len(v['negative_controls']) == 4 and all(c['rejected'] is True for c in v['negative_controls']) for v in validations.values()),
                'Original four independent negative controls did not reject corrupt events')
        require(all(len(validations[name]['collector_negative_controls']) == 3
                    and all(control['rejected'] is True for control in validations[name]['collector_negative_controls'])
                    for name in ('new-default', 'new-16g')), 'New collector metadata negative controls did not reject corruption')
        equivalence = read(output / 'equivalence.json')
        require(equivalence['ok'] is True and len(equivalence['comparisons']) == 2
                and all(c['ok'] is True for c in equivalence['comparisons'])
                and len(equivalence['negative_controls']) == 4
                and all(c['rejected'] is True for c in equivalence['negative_controls']), 'Exact collector pilot equality not proven')
        result['validations'] = validations
        result['equivalence_ok'] = True
        result['equivalence_json_sha256'] = sha(output / 'equivalence.json')
        shutil.copyfile(output / 'equivalence.json', evidence / 'equivalence.json')
        frozen(args.attempt)
        require({path.name: sha(path) for path in (work / 'runtime').iterdir()} == compiled['runtime_hashes'], 'Pilot mutated new runtime')
        result['source_and_runtime_inputs_unchanged'] = True
        result['pilot_output_bytes'] = sum(path.stat().st_size for path in output.rglob('*') if path.is_file())
        require(result['pilot_output_bytes'] <= PILOT_BUDGET, 'Persistent pilot output budget exceeded')
        result['ok'] = True
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
    finally:
        try:
            if cid:
                if owned(cid, owner)['State']['Running']:
                    docker('stop', '--time', '5', cid)
                require(not owned(cid, owner)['State']['Running'], 'Owned pilot did not stop')
                logs = docker('logs', cid)
                content = logs.stdout + logs.stderr
                require(len(content) <= 4 * 1024**2, 'Pilot log exceeds diagnostic budget')
                guard(root_bytes=len(content) + 128 * 1024 + METADATA_RESERVE)
                (evidence / 'pilot-container.log').write_bytes(content)
                docker('rm', '-v', cid)
                result['owned_container_removed'] = True
            result['ok'] = result['ok'] and result.get('owned_container_removed') is True
            guard()
            write(evidence / 'pilot-result.json', result)
        except Exception as error:
            result.update(ok=False, finalization_error=type(error).__name__, finalization_detail=str(error))
    return result


def delivery(args):
    host(args.root)
    evidence, work, scratch, inputs = frozen(args.attempt)
    compiled = read(evidence / 'build-result.json')
    tested = read(evidence / 'pilot-result.json')
    require(compiled['ok'] is True and tested['ok'] is True and tested['equivalence_ok'] is True,
            'Successful native build and exact full pilot equality required before passed delivery')
    terminal_phases(args.attempt)
    no_active_bind((work, scratch))
    rows = []
    for directory, prefix in ((evidence, 'metadata'), (work, 'persistent'), (scratch, 'passed-build-scratch')):
        for path in sorted(directory.rglob('*')):
            if not path.is_file():
                continue
            require(not path.is_symlink() and path.resolve().is_relative_to(directory), 'Linked original delivery member')
            name = path.relative_to(directory).as_posix()
            if prefix == 'metadata' and name in ('delivery-manifest.json', 'local-backup-receipt.json', 'passed-scratch-cleanup.json'):
                continue
            rows.append({'source': str(path), 'path': prefix + '/' + name, 'bytes': path.stat().st_size, 'sha256': sha(path)})
    result = {'schema_version': 1, 'kind': 'cap-budget-runtime-and-equivalence', 'attempt': args.attempt,
              'source_sha': inputs['source_sha'], 'business_source_sha': BUSINESS,
              'instrumentation_source_sha': inputs['instrumentation_source_sha'], 'mixed_input_manifest_sha256': sha(evidence / 'inputs.json'),
              'source_files': 372, 'runtime_files': 8, 'pilot_sets': 3, 'files': rows,
              'whole_task_accepted': False, 'full_unit_dispatch_permitted': False}
    path = evidence / 'delivery-manifest.json'
    if path.exists():
        require(read(path) == result, 'Existing original delivery manifest differs')
    else:
        write(path, result)
    return {'ok': True, 'attempt': args.attempt, 'manifest': str(path), 'manifest_sha256': sha(path),
            'members': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows, 'cloud_archive_created': False}


def status(args):
    host(args.root)
    evidence, work, scratch = paths(args.attempt)
    result = {'ok': True, 'attempt': args.attempt, 'evidence_directory': str(evidence), 'work_directory': str(work),
              'scratch_directory': str(scratch), 'whole_task_accepted': False, 'full_unit_dispatch_permitted': False}
    for name in ('prepare-result.json', 'build-started.json', 'build-result.json', 'pilot-started.json', 'pilot-result.json'):
        result[name] = read(evidence / name) if (evidence / name).exists() else None
    result['native_systemd_units'] = {}
    for phase in ('build', 'pilot'):
        unit = 'pr13-' + args.attempt + '-' + phase
        if (evidence / (phase + '-started.json')).exists():
            result['native_systemd_units'][phase] = unit_state(unit)
        else:
            result['native_systemd_units'][phase] = {'unit': unit, 'phase_not_dispatched': True,
                                                    'no_terminal_claim_without_native_unit': True}
    return result


def cleanup_scratch(args):
    host(args.root)
    evidence, work, scratch, inputs = frozen(args.attempt)
    require(read(evidence / 'build-result.json')['ok'] is True
            and read(evidence / 'pilot-result.json')['ok'] is True,
            'Failed originals cannot be cleaned by the passed-scratch action')
    receipt = read(args.backup_receipt or (evidence / 'local-backup-receipt.json'))
    manifest_path = evidence / 'delivery-manifest.json'
    manifest = read(manifest_path)
    require(receipt['ok'] is True and receipt['source_sha'] == inputs['source_sha']
            and receipt['business_source_sha'] == BUSINESS
            and receipt['instrumentation_source_sha'] == inputs['instrumentation_source_sha']
            and receipt['manifest_sha256'] == sha(manifest_path)
            and receipt['members'] == receipt['members_verified'] == len(manifest['files'])
            and receipt['source_files_verified'] == 372 and receipt['runtime_files_verified'] == 8
            and receipt['pilot_equivalence_verified'] is True
            and receipt['domain_hashes_identical_to_original'] is True
            and receipt['runtime_identical_to_original'] is False
            and all(receipt[field] is True for field in ('archive_gzip_CRC_verified',
                'all_original_members_sha256_verified', 'inner_gzip_CRC_raw_SHA_counts_verified'))
            and re.match(r'^[Gg]:[\\/]', receipt['local_archive'])
            and receipt['bytes'] > 0 and re.fullmatch('[0-9a-f]{64}', receipt['sha256']),
            'Complete original new-runtime/pilot G proof required before cache cleanup')
    saved = evidence / 'local-backup-receipt.json'
    if saved.exists():
        require(read(saved) == receipt, 'Existing new-runtime G proof differs')
    else:
        shutil.copyfile(args.backup_receipt, saved)
    require(scratch.parent == Path('/dev/shm') and scratch.is_dir() and not scratch.is_symlink()
            and scratch.resolve(strict=True) == scratch and scratch.name == 'pr13-' + args.attempt,
            'Cleanup target is not the exact owned passed build scratch')
    terminal_phases(args.attempt)
    no_active_bind((scratch,))
    expected = {row['source']: row for row in manifest['files'] if row['path'].startswith('passed-build-scratch/')}
    actual = set()
    allocated = 0
    for path in scratch.rglob('*'):
        require(not path.is_symlink() and path.resolve().is_relative_to(scratch), 'Linked passed scratch member')
        if path.is_file():
            name = str(path)
            require(name in expected and path.stat().st_size == expected[name]['bytes']
                    and sha(path) == expected[name]['sha256'], 'Passed scratch member differs from complete G manifest')
            actual.add(name)
            allocated += path.stat().st_blocks * 512
    require(actual == set(expected) and actual, 'Unlisted or absent passed scratch original')
    before = os.statvfs(scratch.parent)
    shutil.rmtree(scratch)
    after = os.statvfs(scratch.parent)
    result = {'ok': True, 'attempt': args.attempt, 'source_sha': inputs['source_sha'],
        'business_source_sha': BUSINESS, 'instrumentation_source_sha': inputs['instrumentation_source_sha'],
        'manifest_sha256': sha(manifest_path), 'local_G_archive_sha256': receipt['sha256'],
        'local_G_archive_bytes': receipt['bytes'], 'passed_scratch_removed': str(scratch),
        'allocated_bytes_removed': allocated, 'tmpfs_bytes_reclaimed': (after.f_bavail - before.f_bavail) * after.f_frsize,
        'persistent_source_runtime_and_three_pilot_sets_retained': True, 'failed_originals_retained': True,
        'whole_task_accepted': False, 'full_unit_dispatch_permitted': False}
    write(evidence / 'passed-scratch-cleanup.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'build', 'pilot', 'status', 'prepare-delivery', 'cleanup-passed-scratch', '_container-build'))
    parser.add_argument('--root', type=Path, default=BASE)
    parser.add_argument('--attempt')
    parser.add_argument('--mixed-source-sha')
    parser.add_argument('--instrumentation-source-sha')
    parser.add_argument('--source-publication-state', choices=('private-test-source', 'remote-reachable'), default='private-test-source')
    parser.add_argument('--backup-receipt', type=Path)
    args = parser.parse_args()
    if args.phase == '_container-build':
        require(os.environ.get('PR13_RECOVERY_CONTAINER') == '1', 'Native compilation container only')
        return recovery.container_build()
    require(args.attempt is not None, 'Explicit attempt required')
    actions = {'prepare': prepare, 'build': build, 'pilot': pilot, 'status': status, 'prepare-delivery': delivery,
               'cleanup-passed-scratch': cleanup_scratch}
    result = actions[args.phase](args)
    print(json.dumps(result), flush=True)
    return 0 if result.get('ok') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
