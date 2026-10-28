"""One isolated PG control on Tencent at the existing native part boundary."""
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
E = B / 'evidence/A042-old-started-PG-r1-20261014'
W = B / 'work/A042-old-started-PG-r1-20261014'
OWNER = 'pr13-cap-a042-old-started-pg-r1'
PG = OWNER + '-pg'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    require(not path.exists(), 'Preserve immutable observation: ' + str(path))
    path.write_bytes((json.dumps(value, indent=2) + '\n').encode())
    path.chmod(0o600)


def run(args, check=True, timeout=45):
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    if check:
        r.check_returncode()
    return r


def docker(*args, **options):
    return run(['docker', *map(str, args)], **options)


def state():
    return dict(line.split('=', 1) for line in run(['systemctl', 'show', OWNER,
        '--property=MainPID,ActiveState,ExecMainStatus,InvocationID']).stdout.decode().splitlines())


def guard(start=False):
    memory = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                      if line.startswith('MemAvailable:'))) * 1024
    disk = os.statvfs('/')
    require(memory >= 500000000 + (1400 + 512 + 64) * 1024 ** 2 * int(start), 'Frozen memory floor/reserve')
    require(disk.f_bavail * disk.f_frsize >= int(disk.f_blocks * disk.f_frsize * .15) + 256 * 1024 ** 2 * int(start),
            'Frozen disk floor/reserve')
    with urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10) as response:
        require(response.status == 200, 'Production health failed')
    return {'memory_available_bytes': memory, 'root_free_bytes': disk.f_bavail * disk.f_frsize, 'health_status': 200}


def frozen():
    plan = read(W / 'plan.original.json')
    for key, root in [('source_files', Path(plan['source_root'])), ('runtime_files', Path(plan['runtime_root']))]:
        for row in plan[key]:
            p = root / row['path']
            require(not p.is_symlink() and p.stat().st_size == row['bytes'] and sha(p) == row['sha256'],
                    'Original shared source/runtime bytes differ: ' + row['path'])
    for row in plan['work_files']:
        p = W / row['path']
        require(p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], 'Frozen control input differs')
    require(len(plan['source_files']) == 328 and len(plan['runtime_files']) == 146, 'Complete shared inputs required')
    overrides={'client/tests/run_ready_stop_faults.py':plan['override_runner_sha256'],'client/tests/run_ready_stop_faults.gd':plan['override_gd_sha256']}
    for row in plan['source_files']+plan['client_files']:
        path=W/'source'/row['path']; expected=overrides.get(row['path'],row['sha256'])
        require(not path.is_symlink() and sha(path)==expected,'Actually used source projection differs')
    repo = Path('/opt/fantasycard-github')
    for row in plan['source_files']:
        raw = run(['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo), 'show', 'HEAD:' + row['path']]).stdout
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                'Current release source differs from actually compiled source')
    return plan


def launch():
    with (B / 'evidence/shared-resource-coordination.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        require(not (E / 'dispatch.original.json').exists(), 'Inspect existing dispatch; do not redispatch')
        busy = run(['systemctl', 'list-units', '--state=running', '--no-legend', 'pr13-cap-*', 'pr13-pool-segment-*']).stdout.strip()
        active = docker('ps', '--format', '{{.Names}}').stdout.decode().splitlines()
        busy_lines=[line for line in busy.decode().splitlines() if 'pr13-cap-a042-old-started-scheduler-r1.service' not in line]
        if busy_lines or any(name.startswith(('pr13-cap-', 'pr13-pool-segment-')) for name in active):
            return {'ok': True, 'resource_deferred': True, 'reason': 'Existing B04 original physical part still running'}
        sample = guard(True)
        frozen()
        unit = Path('/etc/systemd/system') / (OWNER + '.service')
        require(not unit.exists(), 'Existing unit requires inspection')
        unit.write_text('[Unit]\nDescription=Actual Godot READY false-send PostgreSQL boundary\n[Service]\nType=exec\nUser=root\n'
                        'ExecStart=/usr/bin/python3 ' + str(E / 'controller.original.py') + ' run\nRuntimeMaxSec=2300\nRestart=no\n')
        write(E / 'dispatch-intent.original.json', {'owner': OWNER, 'guard': sample, 'unit_file_sha256': sha(unit),
                                                    'required_rows_source': 'Actual immutable assembly discovery frozen before execution', 'native_retry_allowed': False})
        run(['systemctl', 'daemon-reload'])
        result = run(['systemctl', 'start', '--no-block', OWNER], check=False)
        write(E / 'dispatch.original.json', {'exit_code': result.returncode, 'owner': OWNER})
        require(result.returncode == 0, 'Unknown dispatch outcome; inspect same native handle')
        return {'ok': True, 'started': True, 'owner': OWNER}


def execute():
    original_state = state()
    require(original_state['MainPID'] == str(os.getpid()) and original_state['ActiveState'] == 'active', 'Wrong native handle')
    plan = frozen()
    write(E / 'started.original.json', {'pid': os.getpid(), 'state': original_state, 'guard': guard(True),
          'actual_cloud_release_sha': run(['git', '-c', 'safe.directory=/opt/fantasycard-github', '-C', '/opt/fantasycard-github', 'rev-parse', 'HEAD']).stdout.decode().strip(),
          'plan_sha256': sha(W / 'plan.original.json')})
    output = E / 'persistent-output'
    require(not output.exists(), 'Original output must stay immutable')
    output.mkdir(mode=0o777)
    output.chmod(0o777)
    secret = B / 'secrets/A042-old-started-PG-r1.private.env'
    require(not secret.exists(), 'Existing private environment requires inspection')
    ids = {}
    result = {'ok': False, 'owner': OWNER, 'case_id': 'A042SecondCycleOldStarted', 'MAIN_accepted': False}

    def owned(name):
        v = json.loads(docker('inspect', ids[name]).stdout)[0]
        require(v['Id'] == ids[name] and v['Name'] == '/' + name and v['Config']['Labels']['codex.owner'] == OWNER,
                'Foreign container identity')
        return v

    def schema_count():
        q = "SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT IN ('public','information_schema') AND schema_name NOT LIKE 'pg_%'"
        return int(docker('exec', ids[PG], 'psql', '-X', '-U', 'fantasycard', '-d', database, '-At', '-c', q).stdout.strip())

    try:
        password = secrets.token_hex(24)
        database = 'coverage_' + secrets.token_hex(12)
        secret.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB=' + database + '\nPOSTGRES_PASSWORD=' + password +
                          '\nFANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database=' + database +
                          ';Username=fantasycard;Password=' + password + ';Timeout=10;Command Timeout=30\n')
        secret.chmod(0o600)
        ids[PG] = docker('run', '-d', '--name', PG, '--label', 'codex.owner=' + OWNER, '--label','codex.scope=disposable-local','--label','codex.task=pr13-stages-20261008','-p','127.0.0.1::5432',
                        '--memory', '512m', '--memory-swap', '512m', '--cpus', '.4',
                        '--tmpfs', '/var/lib/postgresql:rw,nosuid,nodev,size=268435456', '--env-file', str(secret),
                        plan['postgres_image'], 'postgres', '-c', 'shared_buffers=16MB', '-c', 'max_connections=100').stdout.decode().strip()
        owned(PG)
        deadline = time.monotonic() + 60
        while docker('exec', ids[PG], 'pg_isready', '-h', '127.0.0.1', '-U', 'fantasycard', '-d', database, check=False).returncode:
            require(time.monotonic() < deadline, 'Isolated PG startup deadline')
            time.sleep(1)
        before = schema_count()
        require(before == 0, 'Fresh isolated PG required')
        ids[OWNER] = docker('create', '--name', OWNER, '--label', 'codex.owner=' + OWNER,
            '--network','host', '--group-add',str(os.stat('/var/run/docker.sock').st_gid), '--memory', '1400m', '--memory-swap', '1400m', '--cpus', '1',
            '--read-only', '--user', '1000:1000', '--tmpfs', '/tmp:rw,nosuid,nodev,size=134217728',
            '--env-file', str(secret), '-e', 'HOME=/tmp/home', '-e', 'DOTNET_CLI_HOME=/tmp/dotnet',
            '-e','GIT_CONFIG_COUNT=1','-e','GIT_CONFIG_KEY_0=safe.directory','-e','GIT_CONFIG_VALUE_0=/source',
            '-v', str(W/'source') + ':/source:ro', '-v','/var/run/docker.sock:/var/run/docker.sock','-v','/usr/bin/docker:/usr/bin/docker:ro', '-v', plan['runtime_root'] + ':/runtime:ro',
            '-v', str(W) + ':/work:ro', '-v', str(output) + ':/output',
            plan['SDK_image'], 'python3', '/work/inner.original.py').stdout.decode().strip()
        owned(OWNER)
        docker('start', ids[OWNER])
        deadline = time.monotonic() + 2100
        while True:
            native = owned(OWNER)
            if not native['State']['Running']:
                break
            require(time.monotonic() < deadline, 'Frozen native control deadline')
            sample = guard()
            require(sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) <= 256 * 1024 ** 2, 'Original output quota')
            with (E / 'resources.original.jsonl').open('a') as stream:
                stream.write(json.dumps(sample) + '\n')
            time.sleep(2)
        logs = docker('logs', ids[OWNER])
        (E / 'container.stdout.original.log').write_bytes(logs.stdout)
        (E / 'container.stderr.original.log').write_bytes(logs.stderr)
        report = read(output / 'A042-old-started-result.original.json') if (output / 'A042-old-started-result.original.json').exists() else {}
        after = schema_count()
        pg = owned(PG)
        result.update(ok=native['State']['ExitCode'] == 0 and not native['State']['OOMKilled'] and report.get('ok') is True and after == 0,
                      exit_code=native['State']['ExitCode'], oom_killed=native['State']['OOMKilled'],
                      actual_native_job_exit_code=report.get('actual_native_job_exit_code'), actual_native_PG_rows=report.get('actual_native_rows'),
                      isolated_PG_schemas_before=before, isolated_PG_schemas_after=after,
                      actual_PG_image=pg['Image'], actual_SDK_image=native['Image'], owned_container_ids=ids,
                      actual_control_report_sha256=sha(output / 'A042-old-started-result.original.json') if report else None)
        frozen()
        result['original_source_runtime_and_work_inputs_unchanged'] = True
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error), original_failure_retained=True)
    finally:
        cleanup = {}
        for name in reversed(list(ids)):
            try:
                v = owned(name)
                if v['State']['Running']:
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
            require(secret.resolve() == (B / 'secrets/A042-old-started-PG-r1.private.env').resolve(), 'Exact private path required')
            secret.unlink()
        result['private_environment_removed_after_owned_containers_ended'] = not secret.exists()
        result['ok'] = result['ok'] and result['owned_containers_removed'] and result['private_environment_removed_after_owned_containers_ended']
        write(E / 'result.original.json', result)
    require(result['ok'], 'Actual control failed; inspect immutable original output')


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'launch':
        print(json.dumps(launch()))
    elif action == 'run':
        execute()
    elif action == 'status':
        print(json.dumps({'ok': True, 'state': state(), 'result': read(E / 'result.original.json') if (E / 'result.original.json').exists() else None}))
    else:
        raise ValueError('Unknown action')
