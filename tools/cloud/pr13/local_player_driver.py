"""Drive real Windows players against a previously verified owned cloud runtime.

A forwarding failure stops the workload. A replacement forwarding connection is
allowed only after STOP, for the existing clients' bounded business cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'client/tests'))
from fixture_runtime import isolated_environment
from gameplay_load_test import metrics
from pr13_resource_policy import launch_memory_ready, memory_causes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('smoke', 'capacity'), required=True)
    parser.add_argument('--clients', type=int, choices=(10, 50, 100), required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--snapshot-record', type=Path, required=True)
    parser.add_argument('--godot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-route', action='store_true', help='Use the verified IP-restricted HTTPS/WSS owned-test route')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text('utf-8'))
    runtime = json.loads(args.runtime.read_text('utf-8'))
    snapshot_record = json.loads(args.snapshot_record.read_text('utf-8'))
    source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    assert not subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip()
    assert plan['source_sha'] == runtime['release_sha'] == snapshot_record['source_sha'] == source
    policy = plan['resource_and_latency_policy']
    floor = policy['memory_floor_bytes']
    assert floor == 500000000 and policy['per_launch_reserve_bytes'] == 67108864
    assert policy['missing_monitoring_stops_test'] is True
    assert all(policy[k] == v for k, v in [('http_p95_limit_ms', 5000), ('command_p95_limit_ms', 8000),
                                         ('health_limit_ms', 10000), ('monitor_timeout_seconds', 10)])
    assert all(policy[k] == v for k, v in [('cpu_stop_percent', 85), ('disk_available_stop_percent', 15),
                                         ('actor_wait_p95_stop_ms', 100)])
    assert plan['clients'] == args.clients and plan['strategy'] == 'baseline_all_hand'
    assert plan['strategy_seed'] == 20260930 and plan['candidate_activation'] is False
    if args.mode == 'smoke':
        assert args.clients == 10 and plan['overall_seconds'] == 5700 and plan['cycle_seconds'] == 1800
        assert plan['cycles_per_client'] == 3 and plan['load_profile'] == 'cyclic-gameplay'
    else:
        assert args.clients in (50, 100) and plan['overall_seconds'] == 2400 and plan['cycle_seconds'] == 1200
        assert plan['load_profile'] == 'active-hold'
    assert runtime['ok'] and runtime['owned_test_bypass'] and runtime['owned_test_pool_reuse']
    assert runtime['database_max_connections'] == 256 and runtime['effective_cpu_quotas'] == {'server': 0, 'postgres': 0}
    assert runtime['effective_admission']['application_database_pool_max_size'] == 256
    assert not runtime['effective_admission']['ip_policy_limits_enabled']
    assert not runtime['effective_admission']['realtime_command_quota_enabled']
    server_url, prometheus_url = 'http://127.0.0.1:28081', 'http://127.0.0.1:19190'
    if args.public_route:
        route = runtime['owned_public_route']
        assert route['enabled'] and route['relay_ready'] and route['restricted_to_test_source']
        assert route['source_sha'] == source
        server_url, prometheus_url = route['server_url'], route['prometheus_url']
        uri = urllib.parse.urlsplit(server_url)
        assert uri.scheme == 'https' and uri.hostname == 'www.relicbound.cn' and uri.port in (None, 443)
        assert not uri.username and not uri.password and not uri.query and not uri.fragment
        assert re.fullmatch(r'/pr13-owned-[0-9a-f]{24}', uri.path)
        assert prometheus_url == server_url + '/monitor'
    assert snapshot_record['ok'] and snapshot_record['import_exit_code'] == 0
    snapshot = Path(snapshot_record['snapshot'])
    for name, digest in snapshot_record['files'].items():
        assert name.startswith('client/')
        assert hashlib.sha256((snapshot / Path(*Path(name).parts[1:])).read_bytes()).hexdigest() == digest
    assert args.godot.is_file()
    assert launch_memory_ready(psutil.virtual_memory().available, floor, 64)
    output = args.output.resolve()
    assert output.is_relative_to(ROOT / 'outputs')
    output.mkdir(exist_ok=False)
    stop_path = output / 'STOP'
    key = None
    if not args.public_route:
        config = (ROOT / 'server/cloud-env.local.bat').read_text('utf-8-sig')
        key = os.path.expandvars(re.search(r'set "FANTASYCARD_CLOUD_KEY=(.*?)"', config, re.I)[1])
        for port in (28081, 19190):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.3):
                    raise ValueError('Owned forwarding port occupied')
            except (ConnectionRefusedError, socket.timeout):
                pass
    record = {'source_sha': source, 'client_snapshot_source_sha': snapshot_record['source_sha'],
              'driver_pid': os.getpid(), 'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'runtime_revision': runtime['runtime_revision'], 'runtime_image': runtime['image_id'],
              'controller_sha256': runtime['controller_sha256'], 'started_at': time.time(),
              'plan_sha256': hashlib.sha256(args.plan.read_bytes()).hexdigest(), 'frozen_policy': policy,
              'clients': args.clients, 'mode': args.mode, 'candidate_activation': False,
              'owned_test_bypass': True, 'application_max_pool_size': 256, 'database_max_connections': 256,
              'effective_cpu_quotas': runtime['effective_cpu_quotas'], 'accepted': False,
              'execution_split': {'server': 'Tencent cloud owned private instance', 'players': 'Actual local Windows Godot clients'},
              'application_tls_scope': ('Actual HTTPS/WSS on the IP-restricted owned-test path; monitor uses HTTPS'
                                        if args.public_route else 'HTTP/ticket WS inside strict SSH; public HTTPS/WSS remains a separate acceptance scope'),
              'ssh_forwarding_used_for_workload': not args.public_route,
              'public_route_configuration_sha256': runtime.get('owned_public_route', {}).get('active_canonical_sha256') if args.public_route else None,
              'forwarding_policy': {'keepalive_seconds': 5, 'missed_keepalives': 2, 'workload_reconnect': False,
                                    'cleanup_only_reconnect_after_stop': True}, 'forwarding_attempts': []}

    def save():
        temp = output / 'execution.tmp'
        temp.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
        temp.replace(output / 'execution.json')

    def start_forwarding(cleanup_only=False):
        assert not args.public_route
        if cleanup_only:
            assert stop_path.exists(), 'A replacement connection must never resume an interrupted workload'
        command = ['ssh', '-o', 'KexAlgorithms=diffie-hellman-group14-sha256', '-o', 'Ciphers=aes128-ctr',
                   '-o', 'MACs=hmac-sha2-256-etm@openssh.com', '-F', 'none', '-o', 'IdentitiesOnly=yes',
                   '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ExitOnForwardFailure=yes',
                   '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2', '-o', 'TCPKeepAlive=yes',
                   '-o', 'ConnectTimeout=10', '-i', key, '-N', '-L', '127.0.0.1:28081:127.0.0.1:28081',
                   '-L', '127.0.0.1:19190:127.0.0.1:19190', 'ubuntu@43.172.70.182']
        with (output / 'ssh.private.log').open('a', encoding='utf-8') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record['forwarding_attempts'].append({'pid': process.pid, 'at': time.time(), 'cleanup_only': cleanup_only})
        save()
        return process

    def close_forwarding(process):
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def wait_ready(process, seconds=20):
        deadline = time.monotonic() + seconds
        while (process is None or process.poll() is None) and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(server_url + '/health/ready', timeout=2) as response:
                    if response.status == 200:
                        return True
            except OSError:
                pass
            time.sleep(.25)
        return False

    ssh = child = None
    try:
        if not args.public_route:
            ssh = start_forwarding()
        assert wait_ready(ssh), 'Owned endpoint failed readiness'
        baseline = metrics(prometheus_url, 10)
        free = psutil.virtual_memory().available
        record['prelaunch_resource_check'] = {'resources': baseline, 'generator_available_bytes': free, 'at': time.time()}
        save()
        assert all(baseline.get(k) is not None for k in ('cpu', 'disk_available', 'memory_available_bytes'))
        assert not memory_causes(baseline, {'available': True, 'host_memory_available_bytes': free}, floor, floor)
        assert baseline['cpu'] <= 85 and baseline['disk_available'] >= 15
        command = [sys.executable, str(ROOT / 'tools/gameplay_load_test.py'), '--godot', str(args.godot),
                   '--server-url', server_url, '--prometheus', prometheus_url]
        command += (['--smoke', '--smoke-clients', '10', '--smoke-cycles', '3'] if args.mode == 'smoke'
                    else ['--run', '--max-groups', '1', '--group-size', str(args.clients), '--group-interval', '180'])
        command += ['--max-seconds', str(plan['overall_seconds']), '--cycle-limit-seconds', str(plan['cycle_seconds']),
                    '--hero-class', 'mixed', '--strategy', 'baseline_all_hand', '--load-profile', plan['load_profile'],
                    '--strategy-seed', '20260930', '--target-online', str(args.clients), '--target-active', str(args.clients),
                    '--hold-seconds', '600', '--minimum-continuous-seconds', '120', '--minimum-coverage', '0.95',
                    '--maximum-sample-gap', '20', '--launch-interval-seconds', '3',
                    '--minimum-generator-memory-bytes', '500000000', '--minimum-cloud-memory-bytes', '500000000',
                    '--http-p95-limit-ms', '5000', '--command-p95-limit-ms', '8000', '--health-limit-ms', '10000',
                    '--monitor-timeout-seconds', '10', '--client-memory-start-budget-mib', '64', '--client-project', str(snapshot),
                    '--output', str(output / 'load'), '--stop-file', str(stop_path)]
        record['command'] = command
        with (output / 'coordinator.private.log').open('x', encoding='utf-8') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=isolated_environment(output), stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        record.update(coordinator_pid=child.pid, load_started_at=time.time())
        save()
        start = next_sample = time.monotonic()
        with (output / 'cloud-resource-guard.jsonl').open('x', encoding='utf-8') as guard:
            while child.poll() is None:
                reasons = []
                resources = {}
                if ssh is not None and ssh.poll() is not None:
                    record['forwarding_failure_exit_code'] = ssh.returncode
                    reasons.append('ssh_forwarding_exited')
                elif time.monotonic() >= next_sample:
                    resources = metrics(prometheus_url, 10)
                    next_sample = time.monotonic() + 10
                    free = psutil.virtual_memory().available
                    reasons = memory_causes(resources, {'available': True, 'host_memory_available_bytes': free}, floor, floor)
                    if any(resources.get(k) is None for k in ('cpu', 'disk_available')):
                        reasons.append('monitoring_unavailable')
                    # Formal capacity CPU/disk/actor guards retain the coordinator's three-window rule.
                    guard.write(json.dumps({'at': time.time(), 'resources': resources,
                                            'local_generator_available_bytes': free, 'reasons': reasons}) + '\n')
                    guard.flush()
                if reasons:
                    record['guard_stop'] = reasons
                    record['stop_issued_at'] = time.time()
                    stop_path.touch()
                    save()
                    if not args.public_route and ('ssh_forwarding_exited' in reasons or 'monitoring_unavailable' in reasons):
                        close_forwarding(ssh)
                        ssh = start_forwarding(cleanup_only=True)
                        record['cleanup_forwarding_ready'] = wait_ready(ssh)
                        save()
                    break
                if time.monotonic() - start > plan['overall_seconds'] + 120:
                    record['outer_deadline_stop'] = True
                    stop_path.touch()
                    break
                time.sleep(.5)
        try:
            child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            record['forced_coordinator_termination'] = True
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            child.wait(timeout=15)
        record['coordinator_exit_code'] = child.returncode
    except Exception as error:
        record['driver_error'] = type(error).__name__
        stop_path.touch()
        if child is not None and child.poll() is None:
            try:
                child.wait(timeout=120)
            except subprocess.TimeoutExpired:
                record['forced_coordinator_termination'] = True
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                child.wait(timeout=15)
    finally:
        close_forwarding(ssh)
        record.update(ssh_cleanup=ssh is None or ssh.poll() is not None, ended_at=time.time())
        reports = list((output / 'load').glob('*/report.json'))
        if reports:
            assert len(reports) == 1
            report = json.loads(reports[0].read_text('utf-8'))
            record.update(report_path=str(reports[0].relative_to(output)), actual_clients=report['clients'],
                          coordinator_acceptance=report['acceptance_passed'], stop_reason=report['stop_reason'],
                          all_triggers=report['all_triggers'])
        save()
    print(json.dumps({k: record.get(k) for k in ['actual_clients', 'coordinator_exit_code', 'driver_error',
                                               'guard_stop', 'coordinator_acceptance', 'stop_reason', 'ssh_cleanup']}))
    return 0 if record.get('coordinator_acceptance') and not record.get('guard_stop') else 1


if __name__ == '__main__':
    raise SystemExit(main())
