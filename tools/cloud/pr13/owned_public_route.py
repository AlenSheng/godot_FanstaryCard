"""Activate and restore one IP-restricted owned-test route in the existing Caddy.

The deployed Caddyfile stays unchanged. The original live configuration and exact
relay process identity are retained before mutation; production admission stays on.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolated_runtime as owned

BASE = owned.BASE
REPOSITORY = Path('/opt/fantasycard-github')
STATE = BASE / 'evidence/owned-public-route-active.private.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def private_save(path, value):
    owned.save(path, value)


def docker(*args, payload=None):
    result = subprocess.run(['sudo', '-n', 'docker', *args], input=payload, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError('Owned proxy operation failed: ' + result.stderr.decode(errors='replace')[-500:])
    return result.stdout


def proxy(record):
    info = json.loads(docker('inspect', record['proxy_id']))[0]
    assert info['Id'] == record['proxy_id'] and info['State']['Running']
    assert info['Config']['Labels']['com.docker.compose.project'] == 'fantasycard-cloud'
    assert any(m['Source'] == str(REPOSITORY / 'server/Caddyfile') and
               m['Destination'] == '/etc/caddy/Caddyfile' and not m['RW'] for m in info['Mounts'])
    assert digest((REPOSITORY / 'server/Caddyfile').read_bytes()) == record['source_caddyfile_sha256']
    return info


def live_config(record):
    proxy(record)
    return json.loads(docker('exec', record['proxy_id'], 'wget', '-qO-', 'http://127.0.0.1:2019/config/'))


def process_identity(pid):
    root = Path('/proc') / str(pid)
    stat = (root / 'stat').read_text().rpartition(')')[2].split()
    assert stat[0] != 'Z'
    return {'start_ticks': stat[19], 'cmdline_sha256': digest((root / 'cmdline').read_bytes())}


def relay_alive(record):
    try:
        return process_identity(record['relay_pid']) == record['relay_identity']
    except (FileNotFoundError, ProcessLookupError, AssertionError, KeyError):
        return False


def reload_config(record, raw, suffix):
    proxy(record)
    target = '/tmp/pr13-owned-' + Path(record['work']).name.removeprefix('owned-public-route-') + '-' + suffix + '.json'
    docker('exec', '-i', record['proxy_id'], 'sh', '-c', 'cat > "$1"', 'sh', target, payload=raw)
    docker('exec', record['proxy_id'], 'caddy', 'validate', '--config', target)
    docker('exec', record['proxy_id'], 'caddy', 'reload', '--config', target)


def start():
    assert not STATE.exists(), 'Inspect the existing activation before starting another route'
    candidate_path = BASE / 'evidence/owned-public-route-candidate.private.json'
    record = json.loads(candidate_path.read_text())
    assert record['phase'] == 'ValidatedNotActivated'
    work = Path(record['work']).resolve()
    assert work.is_relative_to(BASE / 'evidence') and work.name.startswith('owned-public-route-')
    gateway = ipaddress.ip_address(record['bridge_gateway'])
    assert gateway.version == 4 and gateway.is_private and not gateway.is_unspecified
    runtime = json.loads((BASE / 'evidence/live-runtime.json').read_text())
    assert runtime['ok'] and runtime['owned_test_bypass'] and runtime['owned_test_pool_reuse']
    for role in runtime['containers']:
        owned.owned(runtime, role)
    source = subprocess.check_output(['git', '-C', str(REPOSITORY), 'rev-parse', 'HEAD'], text=True).strip()
    assert runtime['release_sha'] == source
    files = ['bridge_relay.py', 'owned_public_route.py', 'isolated_runtime.py']
    hashes = {}
    for name in files:
        path = Path(__file__).resolve().with_name(name)
        raw = path.read_bytes()
        assert raw == subprocess.check_output(['git', '-C', str(REPOSITORY), 'show', source + ':tools/cloud/pr13/' + name])
        hashes[name] = digest(raw)
    original = (work / 'original-runtime.private.json').read_bytes()
    candidate = (work / 'candidate-runtime.private.json').read_bytes()
    assert digest(original) == record['original_raw_sha256'] and digest(candidate) == record['candidate_sha256']
    assert canonical(live_config(record)) == record['original_canonical_sha256'], 'Live proxy changed since preparation'
    for port in (28082, 19191):
        with socket.socket() as probe:
            probe.bind((str(gateway), port))
    record.update(source_sha=source, phase='RelayStarting', activated=False, source_inputs=hashes,
                  owned_runtime_container_ids=runtime['containers'], started_at=time.time())
    private_save(STATE, record)
    command = [sys.executable, str(Path(__file__).resolve().with_name('bridge_relay.py')),
               '--bind', str(gateway), '--state', str(work / 'relay-state.private.json')]
    with (work / 'relay.private.log').open('ab') as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    record.update(relay_pid=child.pid, relay_identity=process_identity(child.pid))
    private_save(STATE, record)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and relay_alive(record):
        path = work / 'relay-state.private.json'
        if path.exists() and json.loads(path.read_text()).get('ready'):
            break
        time.sleep(.2)
    else:
        raise RuntimeError('Owned private bridge relay did not become ready')
    record['phase'] = 'Activating'
    private_save(STATE, record)
    reload_config(record, candidate, 'candidate')
    assert canonical(live_config(record)) == canonical(json.loads(candidate))
    record.update(phase='Active', activated=True, activated_at=time.time(),
                  active_canonical_sha256=canonical(json.loads(candidate)), relay_ready=True,
                  restricted_to_test_source=True, public_binding_added=False,
                  application_auth_and_body_limits_preserved=True)
    private_save(STATE, record)
    runtime['owned_public_route'] = {key: record[key] for key in ['server_url', 'prometheus_url', 'proxy_id', 'source_sha',
                                                               'active_canonical_sha256', 'restricted_to_test_source', 'relay_ready']}
    runtime['owned_public_route']['enabled'] = True
    private_save(BASE / 'evidence/live-runtime.json', runtime)
    return {'phase': record['phase'], 'relay_ready': True, 'relay_pid': child.pid,
            'restricted_to_test_source': True, 'public_binding_added': False, 'source_sha': source}


def audit():
    record = json.loads(STATE.read_text())
    return {'phase': record['phase'], 'relay_alive': relay_alive(record),
            'proxy_matches_owned_route': canonical(live_config(record)) == record.get('active_canonical_sha256'),
            'source_caddyfile_unchanged': digest((REPOSITORY / 'server/Caddyfile').read_bytes()) == record['source_caddyfile_sha256']}


def stop():
    record = json.loads(STATE.read_text())
    work = Path(record['work'])
    original = (work / 'original-runtime.private.json').read_bytes()
    candidate = (work / 'candidate-runtime.private.json').read_bytes()
    assert digest(original) == record['original_raw_sha256'] and digest(candidate) == record['candidate_sha256']
    current = canonical(live_config(record))
    assert current in (record['original_canonical_sha256'], canonical(json.loads(candidate))), 'Unrelated live proxy change: preserve it'
    if current != record['original_canonical_sha256']:
        reload_config(record, original, 'restore')
    assert canonical(live_config(record)) == record['original_canonical_sha256']
    if relay_alive(record):
        os.kill(record['relay_pid'], signal.SIGTERM)
        deadline = time.monotonic() + 5
        while relay_alive(record) and time.monotonic() < deadline:
            time.sleep(.1)
        assert not relay_alive(record), 'Exact owned relay failed bounded shutdown'
    with urllib.request.urlopen('https://www.relicbound.cn/health/ready', timeout=10) as response:
        assert response.status == 200
    record.update(phase='Restored', activated=False, restored_at=time.time(), original_live_config_restored=True,
                  relay_stopped=True, source_caddyfile_unchanged=True, production_health_verified=True)
    private_save(STATE, record)
    return {key: record[key] for key in ['phase', 'original_live_config_restored', 'relay_stopped',
                                       'source_caddyfile_unchanged', 'production_health_verified']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('start', 'audit', 'stop'))
    args = parser.parse_args()
    print(json.dumps({'start': start, 'audit': audit, 'stop': stop}[args.operation]()))


if __name__ == '__main__':
    main()
