import fcntl
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

B = Path('/home/ubuntu/pr13-acceptance-20261009')
E = B / 'evidence/A08-history-state-PG-r1-20261014'
W = B / 'work/A08-history-state-PG-r1-20261014'
OWNER = 'pr13-cap-a08-history-state-pg-r1'
PG = OWNER + '-pg'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    require(not path.exists(), 'Preserve original: ' + str(path))
    path.write_bytes((json.dumps(value, indent=2) + '\n').encode())


def run(args, check=True, timeout=45):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if check:
        result.check_returncode()
    return result


def docker(*args, **options):
    return run(['docker', *map(str, args)], **options)


def state():
    return dict(line.split('=', 1) for line in run(['systemctl', 'show', OWNER,
        '--property=MainPID,ActiveState,ExecMainStatus,InvocationID']).stdout.decode().splitlines())


def guard(start=False):
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    disk = os.statvfs('/')
    require(available >= 500000000 + (1024 + 256 + 64) * 1024 ** 2 * int(start), 'Memory floor/reserve')
    require(disk.f_bavail * disk.f_frsize >= int(disk.f_blocks * disk.f_frsize * .15) + 256 * 1024 ** 2 * int(start),
            'Disk floor/reserve')
    with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10) as response:
        require(response.status == 200, 'Production health')
    return {'memory_available_bytes': available, 'root_free_bytes': disk.f_bavail * disk.f_frsize, 'health_status': 200}


def frozen():
    plan = read(W / 'control/plan.original.json')
    repo = '/opt/fantasycard-github'
    for row in plan['source_files']:
        path = Path(plan['source_root']) / row['path']
        require(not path.is_symlink() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],
                'Shared original source changed')
        raw = run(['git', '-c', 'safe.directory=' + repo, '-C', repo, 'show', 'HEAD:' + row['path']]).stdout
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Current source differs')
        owned = W / 'source' / row['path']
        expected = plan['modified_test_source_sha256'] if row['path'] == plan['source_override_path'] else row['sha256']
        require(not owned.is_symlink() and sha(owned) == expected, 'Owned controlled source differs')
    for row in plan['package_files']:
        path = Path(plan['package_root']) / row['path']
        require(not path.is_symlink() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Package changed')
    for row in plan['work_files']:
        path = W / 'control' / row['path']
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], 'Frozen control input changed')
    for row in plan['config_files']:
        path = W / 'control/published' / row['path']
        raw = run(['git', '-c', 'safe.directory=' + repo, '-C', repo, 'show', 'HEAD:' + row['path']]).stdout
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'] and
                hashlib.sha256(raw).hexdigest() == row['sha256'], 'Published config input changed')
    original = (Path(plan['source_root']) / plan['source_override_path']).read_bytes()
    addition = (W / 'control/addition.original.cs').read_bytes()
    index = original.rfind(b'}')
    require((W / 'source' / plan['source_override_path']).read_bytes() == original[:index] + addition + original[index:],
            'Only declared new test method insertion allowed')
    return plan


def launch():
    with (B / 'evidence/shared-resource-coordination.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        require(not (E / 'dispatch.original.json').exists(), 'Inspect existing native handle; no redispatch')
        busy = run(['systemctl', 'list-units', '--state=running', '--no-legend', 'pr13-cap-*', 'pr13-pool-segment-*']).stdout.strip()
        active = docker('ps', '--format', '{{.Names}}').stdout.decode().splitlines()
        busy_lines=[line for line in busy.decode().splitlines() if 'pr13-cap-a08-history-state-scheduler-r1.service' not in line]
        if busy_lines or any(name.startswith(('pr13-cap-', 'pr13-pool-segment-')) for name in active):
            return {'ok': True, 'resource_deferred': True, 'reason': 'Existing B04 physical part'}
        sample = guard(True)
        frozen()
        unit = Path('/etc/systemd/system') / (OWNER + '.service')
        require(not unit.exists(), 'Existing unit must be inspected')
        unit.write_text('[Unit]\nDescription=Owned historical and queued state PostgreSQL control\n'
            '[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 ' + str(E / 'controller.original.py') +
            ' run\nRuntimeMaxSec=1700\nRestart=no\n')
        write(E / 'dispatch-intent.original.json', {'owner': OWNER, 'guard': sample, 'native_expected_rows': 10,
            'new_control_rows': 1, 'unit_file_sha256': sha(unit), 'automatic_retry': False})
        run(['systemctl', 'daemon-reload'])
        result = run(['systemctl', 'start', '--no-block', OWNER], check=False)
        write(E / 'dispatch.original.json', {'exit_code': result.returncode, 'owner': OWNER})
        require(result.returncode == 0, 'Unknown dispatch outcome; inspect original handle')
        return {'ok': True, 'started': True, 'owner': OWNER}


def execute():
    current = state()
    require(current['MainPID'] == str(os.getpid()) and current['ActiveState'] == 'active', 'Wrong native handle')
    plan = frozen()
    write(E / 'started.original.json', {'pid': os.getpid(), 'state': current, 'guard': guard(True),
        'source_base_sha': plan['source_base_sha'], 'plan_sha256': sha(W / 'control/plan.original.json')})
    output = E / 'persistent-output'
    artifacts = W / 'artifacts'
    for path in [output, artifacts]:
        require(not path.exists(), 'Original writable directory exists')
        path.mkdir(mode=0o777)
        path.chmod(0o777)
    # The control root holds immutable inputs plus bounded owned generated copies.
    # Read-only file mounts keep each frozen input immutable in the container.
    control = W / 'control'
    control.chmod(0o777)
    secret = B / 'secrets/A08-history-state-PG-r1.private.env'
    require(not secret.exists(), 'Existing private environment')
    ids = {}
    result = {'ok': False, 'case_id': 'PR13-A08.2-T01', 'owner': OWNER, 'MAIN_accepted': False}

    def owned(name):
        v = json.loads(docker('inspect', ids[name]).stdout)[0]
        require(v['Id'] == ids[name] and v['Name'] == '/' + name and v['Config']['Labels']['codex.owner'] == OWNER,
                'Foreign container')
        return v

    try:
        password = secrets.token_hex(24)
        database = 'config_integrity_' + secrets.token_hex(12)
        secret.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB=' + database + '\nPOSTGRES_PASSWORD=' + password +
            '\nFANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database=' + database +
            ';Username=fantasycard;Password=' + password + ';Timeout=10;Command Timeout=30\n')
        secret.chmod(0o600)
        ids[PG] = docker('run', '-d', '--name', PG, '--label', 'codex.owner=' + OWNER,
            '--network', 'none', '--memory', '256m', '--memory-swap', '256m', '--cpus', '.4',
            '--tmpfs', '/var/lib/postgresql:rw,nosuid,nodev,size=134217728', '--env-file', str(secret),
            plan['postgres_image'], 'postgres', '-c', 'shared_buffers=16MB', '-c', 'max_connections=25').stdout.decode().strip()
        owned(PG)
        until = time.monotonic() + 60
        while docker('exec', ids[PG], 'pg_isready', '-h', '127.0.0.1', '-U', 'fantasycard', '-d', database, check=False).returncode:
            require(time.monotonic() < until, 'PG startup deadline')
            time.sleep(1)
        args = ['create', '--name', OWNER, '--label', 'codex.owner=' + OWNER, '--network', 'container:' + ids[PG],
            '--memory', '1024m', '--memory-swap', '1024m', '--cpus', '1', '--read-only', '--user', '1000:1000',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=134217728', '--env-file', str(secret),
            '-e', 'HOME=/tmp/home', '-e', 'DOTNET_CLI_HOME=/tmp/dotnet', '-e', 'NUGET_PACKAGES=/packages',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'FANTASYCARD_PR13_NUMERICAL_EVIDENCE=/output/native-receipts',
            '-v', str(W / 'source') + ':/work:ro', '-v', plan['package_root'] + ':/packages:ro',
            '-v', str(control) + ':/control', '-v', str(artifacts) + ':/artifacts', '-v', str(output) + ':/output']
        for name in ['plan.original.json'] + [row['path'] for row in plan['work_files']]:
            args.extend(['-v', str(control / name) + ':/control/' + name + ':ro'])
        args.extend(['-v', str(control / 'published') + ':/control/published:ro',
                     plan['SDK_image'], 'python3', '/control/inner.original.py'])
        ids[OWNER] = docker(*args).stdout.decode().strip()
        owned(OWNER)
        docker('start', ids[OWNER])
        until = time.monotonic() + 1500
        while True:
            info = owned(OWNER)
            if not info['State']['Running']:
                break
            require(time.monotonic() < until, 'Frozen native deadline')
            sample = guard()
            require(sum(p.stat().st_size for p in artifacts.rglob('*') if p.is_file()) <= plan['artifact_quota_bytes'], 'Artifact quota')
            require(sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) <= plan['original_output_quota_bytes'], 'Output quota')
            with (E / 'resources.original.jsonl').open('a') as stream:
                stream.write(json.dumps(sample) + '\n')
            time.sleep(5)
        logs = docker('logs', ids[OWNER])
        (E / 'container.stdout.original.log').write_bytes(logs.stdout)
        (E / 'container.stderr.original.log').write_bytes(logs.stderr)
        inner = read(output / 'inner-result.original.json') if (output / 'inner-result.original.json').exists() else {}
        query = "SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT IN ('public','information_schema') AND schema_name NOT LIKE 'pg_%'"
        remaining = int(docker('exec', ids[PG], 'psql', '-X', '-U', 'fantasycard', '-d', database, '-At', '-c', query).stdout.strip())
        result.update(ok=info['State']['ExitCode'] == 0 and not info['State']['OOMKilled'] and inner.get('ok') is True and remaining == 0,
            exit_code=info['State']['ExitCode'], oom_killed=info['State']['OOMKilled'], inner=inner,
            remaining_owned_fixture_schemas=remaining, actual_SDK_image=info['Image'], actual_PG_image=owned(PG)['Image'])
        frozen()
        result['original_shared_and_controlled_inputs_unchanged'] = True
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error), original_failure_retained=True)
    finally:
        cleanup = {}
        for name in reversed(list(ids)):
            try:
                info = owned(name)
                if info['State']['Running']:
                    docker('stop', '--time', '10', ids[name])
                if name == PG:
                    logs = docker('logs', ids[name])
                    (E / 'postgres.stdout.original.log').write_bytes(logs.stdout)
                    (E / 'postgres.stderr.original.log').write_bytes(logs.stderr)
                owned(name)
                docker('rm', ids[name])
                cleanup[name] = True
            except Exception as error:
                cleanup[name] = type(error).__name__
        result['owned_containers_removed'] = len(cleanup) == 2 and all(v is True for v in cleanup.values())
        result['cleanup'] = cleanup
        if result['owned_containers_removed'] and secret.exists():
            secret.unlink()
        result['private_environment_removed_after_owned_containers_ended'] = not secret.exists()
        result['ok'] = result['ok'] and result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
        write(E / 'result.original.json', result)
    require(result['ok'], 'Native original failure preserved')


if __name__ == '__main__':
    if sys.argv[1] == 'launch':
        print(json.dumps(launch()))
    elif sys.argv[1] == 'run':
        execute()
    elif sys.argv[1] == 'status':
        print(json.dumps({'ok': True, 'state': state(), 'result': read(E / 'result.original.json') if (E / 'result.original.json').exists() else None}))
    else:
        raise ValueError('Unknown action')
