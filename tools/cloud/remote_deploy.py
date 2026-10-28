"""One test-server transaction holds the legacy lock through external acceptance.

Only status words are printed. No database contents, env values or command output
leave the server. EOF/timeout/cancellation rolls back the application, never data.
"""
import argparse
import contextlib
import json
import os
import pathlib
import re
import select
import signal
import subprocess
import sys
import threading
import time
from deployment import file_hash, positive_integer, sha, validate_manifest

REPO = pathlib.Path('/opt/fantasycard-github')
APP = pathlib.Path('/opt/fantasycard-app')
COMPOSE = REPO / 'server/compose.cloud.yaml'
ENV_FILE = REPO / 'server/.env'
LOCK = pathlib.Path('/tmp/fantasycard-update.lock')
HEALTH_TIMEOUT = 180
BLOCKED_PATHS = (
    'server/src/FantasyCard.Server/Persistence', 'server/compose.cloud.yaml',
    'server/Caddyfile', 'server/site', 'server/monitoring', 'server/deploy',
    'server/src/FantasyCard.Server/appsettings*', 'server/Directory.Build.props',
    'server/Directory.Packages.props', 'server/global.json', 'server/NuGet.Config',
    'server/src/FantasyCard.Server/FantasyCard.Server.csproj',
    'server/src/FantasyCard.Server/Rooms', 'server/src/FantasyCard.Server/Realtime',
    'server/src/FantasyCard.Domain', 'server/src/FantasyCard.Contracts',
    'server/src/FantasyCard.Server/Program.cs', 'server/src/FantasyCard.Server/Dockerfile',
)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, content):
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fsync_directory(path.parent)


def remove(path):
    path.unlink(missing_ok=True)
    fsync_directory(path.parent)


def run(*arguments, **kwargs):
    kwargs.setdefault('stdout', subprocess.DEVNULL)
    kwargs.setdefault('stderr', subprocess.DEVNULL)
    return subprocess.run(list(map(str, arguments)), check=True,
                          timeout=kwargs.pop('timeout', 120), **kwargs)


def capture(*arguments):
    return run(*arguments, stdout=subprocess.PIPE, text=True, timeout=15).stdout.strip()


@contextlib.contextmanager
def deployment_lock():
    import fcntl
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def external_decision(stream=sys.stdin, timeout=180):
    ready, _, _ = select.select([stream], [], [], timeout)
    return bool(ready) and os.read(stream.fileno(), 32) == b'accept\n'


def rollout(new_image, old_image, apply, healthy, record, finalize,
            external, commit, rollback_state, finish_rollback):
    """Compensate even when evidence writing fails; never let it skip rollback."""
    try:
        record('activating')
        apply(new_image)
        if not healthy():
            raise RuntimeError('Candidate health failed')
        record('awaiting_external')
        if not external():
            raise RuntimeError('External acceptance failed')
        finalize(new_image)
        record('accepted')
        commit()
    except BaseException:
        handlers = {}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM):
                handlers[sig] = signal.signal(sig, signal.SIG_IGN)
        try:
            try:
                record('rolling_back')
            except BaseException:
                pass
            restored = False
            try:
                apply(old_image)
                if not healthy():
                    raise RuntimeError('Baseline health failed')
                finalize(old_image)
                rollback_state()
                restored = True
            except BaseException:
                pass
            try:
                record('rolled_back' if restored else 'rollback_failed')
                if restored:
                    finish_rollback()
            except BaseException:
                pass  # Keep durable pending state to block the next deployment.
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        raise


def deploy(bundle, source_sha, run_id, run_attempt, controller_sha, recover=False):
    import pwd
    if pwd.getpwuid(os.geteuid()).pw_name != 'ubuntu':
        raise ValueError('Run as ubuntu without elevating the controller')
    sha(source_sha)
    sha(controller_sha)
    positive_integer(run_id)
    positive_integer(run_attempt)
    expected = APP / f'test-deploy/incoming/{run_id}-{run_attempt}'
    if bundle != expected or bundle.resolve(strict=True) != expected:
        raise ValueError('Expected exact run directory without symlinks')
    for name in ('manifest.json', 'image.tar.gz', 'image-validation.json', 'health.sh', 'remote_deploy.py', 'deployment.py'):
        path = bundle / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Invalid bundle file')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    validate_manifest(manifest, source_sha, run_id, run_attempt, controller_sha)
    for name, field in (('image.tar.gz', 'archive_sha256'), ('health.sh', 'health_sha256'),
                        ('remote_deploy.py', 'remote_sha256'), ('deployment.py', 'deployment_sha256')):
        if file_hash(bundle / name) != manifest[field]:
            raise ValueError('Bundle bytes differ from tested build')
    if file_hash(bundle / 'image-validation.json') != manifest['image_validation_sha256']:
        raise ValueError('Runtime-image validation evidence differs from build')
    if not COMPOSE.is_file() or not ENV_FILE.is_file():
        raise ValueError('Existing server is not provisioned')
    state = APP / 'test-deploy'
    override, pending, accepted = (state / name for name in ('active-image.yaml', 'pending.json', 'last-accepted.json'))
    marker, result = APP / 'deployed-runtime-commit', bundle / 'result.json'
    command = ['sudo', '-n', 'docker', 'compose', '-f', str(COMPOSE), '--env-file', str(ENV_FILE)]

    def compose(*arguments, **kwargs):
        files = ['-f', str(override)] if override.exists() else []
        return run(*command, *files, *arguments, **kwargs)

    def identity():
        container = compose('ps', '-q', 'server', stdout=subprocess.PIPE, text=True, timeout=15).stdout.strip()
        if not re.fullmatch(r'[0-9a-f]{12,64}', container):
            raise ValueError('Expected one application container')
        image = capture('sudo', '-n', 'docker', 'inspect', '--format', '{{.Image}}', container)
        revision = capture('sudo', '-n', 'docker', 'inspect', '--format',
                           '{{index .Config.Labels "org.opencontainers.image.revision"}}', container)
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('Invalid baseline image identity')
        sha(revision)
        return image, revision

    def health():
        deadline = time.monotonic() + HEALTH_TIMEOUT
        while True:
            try:
                if subprocess.run(['bash', str(bundle / 'health.sh')], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=35).returncode == 0:
                    return True
            except subprocess.TimeoutExpired:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(5)

    if pending.exists():
        if not recover:
            raise ValueError('Unfinished transaction requires explicit recovery')
        evidence = json.loads(pending.read_text())
        if any(evidence.get(key) != value for key, value in manifest.items()):
            raise ValueError('Recovery bundle differs from pending transaction')
        old_image, old_revision = evidence['baseline_image_id'], sha(evidence['baseline_revision'])
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', old_image):
            raise ValueError('Invalid recovery baseline')
    else:
        if recover:
            raise ValueError('No transaction to recover')
        remote = capture('git', '-C', REPO, 'remote', 'get-url', 'origin')
        if remote not in ('https://github.com/AlenSheng/godot_FanstaryCard.git',
                          'git@github.com:AlenSheng/godot_FanstaryCard.git'):
            raise ValueError('Unexpected server repository')
        run('git', '-C', REPO, 'diff', '--quiet')
        run('git', '-C', REPO, 'diff', '--cached', '--quiet')
        run('git', '-C', REPO, 'fetch', '--no-tags', '--filter=blob:none', 'origin', source_sha, timeout=300)
        if capture('git', '-C', REPO, 'rev-parse', 'FETCH_HEAD') != source_sha:
            raise ValueError('Fetched source differs from approved commit')
        old_image, old_revision = identity()
        if old_revision != manifest['rollback_baseline_sha']:
            raise ValueError('Baseline moved since rollback review')
        checkout = sha(capture('git', '-C', REPO, 'rev-parse', 'HEAD'))
        if marker.read_text().strip() != old_revision:
            raise ValueError('Runtime marker differs from running image')
        if (APP / 'deployed-git-commit').read_text().strip() != checkout:
            raise ValueError('Checkout marker differs from checkout')
        run('git', '-C', REPO, 'diff', '--quiet', old_revision, source_sha, '--', *BLOCKED_PATHS)
        run('git', '-C', REPO, 'diff', '--quiet', 'HEAD', old_revision, '--', *BLOCKED_PATHS)
        previous_override = override.read_text() if override.exists() else None
        if previous_override is not None and previous_override != f'services:\n  server:\n    image: {old_image}\n':
            raise ValueError('Unexpected active override')
        previous_accepted = accepted.read_text() if accepted.exists() else None
        evidence = {**manifest, 'baseline_revision': old_revision, 'baseline_image_id': old_image,
                    'checkout_sha': checkout, 'previous_override': previous_override,
                    'previous_accepted': previous_accepted, 'events': [], 'status': 'preflight'}

    def record(status):
        evidence['status'] = status
        evidence['events'].append({'status': status, 'utc_epoch': int(time.time())})
        if status in ('rolling_back', 'rollback_failed'):
            atomic_write(pending, json.dumps(evidence, indent=2) + '\n')
        public = {key: value for key, value in evidence.items()
                  if key not in ('previous_override', 'previous_accepted')}
        atomic_write(result, json.dumps(public, indent=2) + '\n')
        print('deployment_status=' + status, flush=True)

    new_image = manifest['image_id']
    def apply(image):
        atomic_write(override, f'services:\n  server:\n    image: {image}\n')
        compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'server', timeout=180)
        wanted_revision = source_sha if image == new_image else old_revision
        if identity() != (image, wanted_revision):
            raise ValueError('Running image/source differs from selected identity')

    def finalize(image):
        atomic_write(marker, (source_sha if image == new_image else old_revision) + '\n')

    def rollback_state():
        for path, value in ((override, evidence['previous_override']), (accepted, evidence['previous_accepted'])):
            if value is None:
                remove(path)
            else:
                atomic_write(path, value)

    def commit():
        atomic_write(accepted, result.read_text())
        try:
            remove(pending)  # Commit point, after all application/marker/evidence writes.
        except BaseException:
            atomic_write(pending, json.dumps(evidence, indent=2) + '\n')
            raise

    if recover:
        # Recovery never activates the candidate. Successful recovery is still a
        # failed deployment; operators must inspect rolled_back and retry explicitly.
        def reject(image):
            if image == old_image:
                apply(image)
            else:
                raise RuntimeError('Explicit recovery')
        rollout(new_image, old_image, reject, health, record, finalize,
                lambda: False, commit, rollback_state, lambda: remove(pending))
        return

    record('preflight')
    if not health():
        raise ValueError('Baseline unhealthy; stopped before application mutation')
    backup_dir = APP / 'backups'
    backup_dir.mkdir(exist_ok=True, mode=0o700)
    backup = backup_dir / f'actions-{run_id}-{run_attempt}-before-{source_sha}.dump'
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        compose('exec', '-T', 'postgres', 'pg_dump', '-U', 'fantasycard', '-d', 'fantasycard',
                '--format=custom', '--no-owner', '--no-privileges', stdout=output, timeout=300)
        output.flush()
        os.fsync(output.fileno())
    if not backup.stat().st_size:
        raise ValueError('Empty database backup')
    with backup.open('rb') as stream:
        compose('exec', '-T', 'postgres', 'pg_restore', '--list', stdin=stream)
    evidence['backup'] = {'name': backup.name, 'sha256': file_hash(backup), 'bytes': backup.stat().st_size}
    run('sudo', '-n', 'docker', 'image', 'load', '-i', bundle / 'image.tar.gz', timeout=300)
    if capture('sudo', '-n', 'docker', 'image', 'inspect', '--format', '{{.Id}}', new_image) != new_image:
        raise ValueError('Loaded image differs from tested image')
    if capture('sudo', '-n', 'docker', 'image', 'inspect', '--format',
               '{{index .Config.Labels "org.opencontainers.image.revision"}}', new_image) != source_sha:
        raise ValueError('Loaded source label differs from approved source')
    atomic_write(pending, json.dumps(evidence, indent=2) + '\n')
    rollout(new_image, old_image, apply, health, record, finalize, external_decision,
            commit, rollback_state, lambda: remove(pending))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=pathlib.Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--run-attempt', type=int, required=True)
    parser.add_argument('--controller-sha', required=True)
    parser.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise RuntimeError('Controller interrupted')
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM):
        signal.signal(sig, interrupted)
    # Global normal-operation budget. Compensation ignores this alarm and has a
    # separate <=450s reserve in the runner's 1950s controller deadline.
    signal.alarm(1500)
    try:
        with deployment_lock():
            deploy(args.bundle, args.source_sha, args.run_id, args.run_attempt, args.controller_sha, args.recover)
    except BaseException as error:
        print('Deployment stopped: ' + type(error).__name__, flush=True)
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
