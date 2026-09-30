"""Strict SSH transport and external acceptance, using only trusted runner code."""
import json
import os
import pathlib
import re
import selectors
import shlex
import signal
import subprocess
import tempfile
import time
from deployment import extract_health, file_hash, positive_integer, sha, validate_manifest, validate_image_proof

HOST = 'ubuntu@43.172.70.182'
PUBLIC_ORIGIN = 'https://www.relicbound.cn'
STATUSES = frozenset(('preflight', 'activating', 'awaiting_external', 'accepted',
                      'rolling_back', 'rolled_back', 'rollback_failed'))


def external_health():
    """Bound responses; report booleans/status only, never remote response text."""
    results = []
    for path, expected in (('/health/ready', 200), ('/admin', 404), ('/api/admin/client-settings', 404)):
        response = subprocess.run(['curl', '--disable', '--silent', '--show-error',
            '--proto', '=https', '--max-time', '20', '--max-filesize', '256',
            '--write-out', '\n%{http_code}', PUBLIC_ORIGIN + path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25)
        body, _, code = response.stdout.rpartition(b'\n')
        passed = response.returncode == 0 and code == str(expected).encode()
        if path == '/health/ready':
            passed = passed and body.strip() == b'Healthy'
        results.append({'path': path, 'expected_status': expected, 'passed': passed})
    return all(row['passed'] for row in results), results


def supervise(command, probe=external_health, deadline_seconds=1950):
    """One remote session retains the shared flock until accept/rollback completes."""
    external = None
    deadline = time.monotonic() + deadline_seconds
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, bufsize=0) as process:
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffered = b''
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Remote controller deadline')
                if not selector.select(timeout=min(1, max(0, deadline-time.monotonic()))):
                    continue
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    break
                buffered += chunk
                if len(buffered) > 8192:
                    raise ValueError('Unexpected remote output size')
                while b'\n' in buffered:
                    line, buffered = buffered.split(b'\n', 1)
                    text = line.decode('ascii', errors='strict')
                    if text.startswith('Deployment stopped: '):
                        continue
                    status = text.removeprefix('deployment_status=')
                    if status not in STATUSES or text != 'deployment_status=' + status:
                        raise ValueError('Unexpected remote protocol')
                    print(text, flush=True)
                    if status == 'awaiting_external':
                        if external is not None:
                            raise ValueError('Repeated acceptance request')
                        external = probe()
                        process.stdin.write(b'accept\n' if external[0] else b'rollback\n')
                        process.stdin.flush()
            code = process.wait(timeout=max(1, deadline-time.monotonic()))
        except BaseException:
            # EOF requests rollback without killing the server-side compensation.
            process.stdin.close()
            try:
                process.wait(timeout=480)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise
        finally:
            selector.close()
        if code or external is None or not external[0]:
            raise RuntimeError('Remote or external acceptance failed')
    return external[1]


def safe_result(data, manifest):
    """Only a strict, typed evidence schema is allowed into uploaded artifacts."""
    extra = {'baseline_revision', 'baseline_image_id', 'checkout_sha', 'events', 'status', 'backup'}
    if not isinstance(data, dict) or set(data) != set(manifest) | extra:
        raise ValueError('Unexpected evidence fields')
    if any(data[key] != value for key, value in manifest.items()):
        raise ValueError('Remote evidence differs from tested build')
    for field in ('baseline_revision', 'checkout_sha'):
        sha(data[field])
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', data['baseline_image_id']):
        raise ValueError('Invalid baseline evidence')
    if data['status'] not in STATUSES or not isinstance(data['events'], list) or not 1 <= len(data['events']) <= 20:
        raise ValueError('Invalid transaction evidence')
    for event in data['events']:
        if set(event) != {'status', 'utc_epoch'} or event['status'] not in STATUSES or type(event['utc_epoch']) is not int or event['utc_epoch'] <= 0:
            raise ValueError('Invalid status event')
    if data['events'][-1]['status'] != data['status']:
        raise ValueError('Inconsistent final status')
    backup = data['backup']
    expected_name = f"actions-{manifest['run_id']}-{manifest['run_attempt']}-before-{manifest['source_sha']}.dump"
    if set(backup) != {'name', 'sha256', 'bytes'} or backup['name'] != expected_name or not re.fullmatch(r'[0-9a-f]{64}', backup['sha256']) or type(backup['bytes']) is not int or backup['bytes'] <= 0:
        raise ValueError('Invalid backup evidence')
    return data


def ssh_options(private, hosts):
    return ['-F', '/dev/null', '-i', str(private), '-o', 'BatchMode=yes',
        '-o', 'IdentitiesOnly=yes', '-o', 'PasswordAuthentication=no', '-o', 'ForwardAgent=no',
        '-o', 'ClearAllForwardings=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'UserKnownHostsFile=' + str(hosts),
        '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4']


def main():
    number, attempt = (positive_integer(os.environ[name]) for name in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    source, controller = sha(os.environ['COMMIT_SHA']), sha(os.environ['GITHUB_SHA'])
    artifact, evidence = pathlib.Path('image-artifact'), pathlib.Path('deploy-evidence')
    evidence.mkdir(exist_ok=True)
    if set(path.name for path in artifact.iterdir()) != {'manifest.json', 'image.tar.gz', 'image-validation.json'}:
        raise ValueError('Artifact contains unexpected files')
    for path in artifact.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError('Invalid artifact path')
    manifest = json.loads((artifact / 'manifest.json').read_text())
    validate_manifest(manifest, source, number, attempt, controller)
    if file_hash(artifact / 'image.tar.gz') != manifest['archive_sha256']:
        raise ValueError('Image archive checksum mismatch')
    if file_hash(artifact / 'image-validation.json') != manifest['image_validation_sha256']:
        raise ValueError('Final-image validation checksum mismatch')
    validate_image_proof(json.loads((artifact / 'image-validation.json').read_text()), manifest['image_id'], source)
    extract_health('trusted/server/deploy/fantasycard-update.sh', artifact / 'health.sh')
    for path, field in ((artifact / 'health.sh', 'health_sha256'),
                       (pathlib.Path('trusted/tools/cloud/remote_deploy.py'), 'remote_sha256'),
                       (pathlib.Path('trusted/tools/cloud/deployment.py'), 'deployment_sha256')):
        if file_hash(path) != manifest[field]:
            raise ValueError('Artifact tried to change the trusted controller')
    remote = f'/opt/fantasycard-app/test-deploy/incoming/{number}-{attempt}'
    key, known = os.environ.pop('TEST_SERVER_SSH_KEY', ''), os.environ.pop('TEST_SERVER_KNOWN_HOSTS', '')
    if not key or not known or not re.search(r'(?:^|\n)43\.172\.70\.182\s+(?:ssh-|ecdsa-)', known):
        raise ValueError('Missing private key or exact verified host entry')
    with tempfile.TemporaryDirectory(prefix='fantasycard-ssh-') as directory:
        private, hosts = (pathlib.Path(directory) / name for name in ('key', 'known_hosts'))
        private.write_text(key.rstrip() + '\n')
        hosts.write_text(known.rstrip() + '\n')
        private.chmod(0o600)
        hosts.chmod(0o600)
        del key, known
        options = ssh_options(private, hosts)
        ssh, scp = ['ssh', *options, '-p', '22', HOST], ['scp', *options, '-P', '22']
        def transfer(arguments, timeout):
            return subprocess.run(arguments, check=True, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=timeout)
        transfer([*ssh, 'umask 077 && mkdir -p /opt/fantasycard-app/test-deploy/incoming && mkdir ' + shlex.quote(remote)], 45)
        transfer([*scp, str(artifact / 'image.tar.gz'), str(artifact / 'manifest.json'), str(artifact / 'image-validation.json'), str(artifact / 'health.sh'),
                  'trusted/tools/cloud/remote_deploy.py', 'trusted/tools/cloud/deployment.py', HOST + ':' + remote + '/'], 600)
        command = shlex.join(['python3', remote + '/remote_deploy.py', '--bundle', remote,
            '--source-sha', source, '--run-id', str(number), '--run-attempt', str(attempt), '--controller-sha', controller])
        def interrupted(signum, frame):
            raise RuntimeError('Runner interrupted')
        handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
        runner_status = 'unknown'
        try:
            external = supervise([*ssh, command])
            (evidence / 'external.json').write_text(json.dumps(external, indent=2) + '\n')
            runner_status = 'accepted'
        except BaseException:
            runner_status = 'failed'
            raise
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            # Retrieve into a private temp directory; reject arbitrary fields/text.
            raw = pathlib.Path(directory) / 'result.json'
            try:
                transfer([*scp, HOST + ':' + remote + '/result.json', str(raw)], 45)
                if raw.stat().st_size > 65536:
                    raise ValueError('Evidence too large')
                result = safe_result(json.loads(raw.read_text()), manifest)
                (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            except Exception:
                (evidence / 'retrieval.json').write_text('{"status":"unknown","sanitized_evidence_available":false,"recovery_required":true}\n')
            (evidence / 'runner.json').write_text(json.dumps({'runner_status':runner_status,
                'remote_status':result['status'] if 'result' in locals() else 'unknown',
                'recovery_required': 'result' not in locals() or result['status'] not in ('accepted','rolled_back')}) + '\n')
        result = json.loads((evidence / 'result.json').read_text())
        if result['status'] != 'accepted':
            raise ValueError('Remote transaction did not commit acceptance')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # Exception values/commands/HTTP bodies may contain secret material.
        print('Shipping stopped: ' + type(error).__name__, flush=True)
        raise SystemExit(1) from None
