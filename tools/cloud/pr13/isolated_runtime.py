"""Operate only task-owned Tencent test services; preserve the live deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

BASE = Path('/home/ubuntu/pr13-acceptance-20261009')
LABEL = 'pr13-tencent-20261009'
NAMES = {'postgres': 'pr13-tencent-live-pg', 'otel': 'pr13-tencent-live-otel',
         'prometheus': 'pr13-tencent-live-prometheus', 'server': 'pr13-tencent-live-server'}
PG_IMAGE = 'postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
IMAGE = 'sha256:330e33567955abb730b953217e1afe1f9963ff770d8d40ca24255b9db217f6ce'


def command(*args, check=True, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Owned cloud operation failed: ' + args[0])
    return result


def docker(*args, **kwargs):
    return command('sudo', '-n', 'docker', *args, **kwargs)


def inspect(name):
    return json.loads(docker('inspect', name).stdout)[0]


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


def owned(record, role):
    info = inspect(NAMES[role])
    if info['Id'] != record['containers'][role] or info['Config']['Labels'].get('codex.session') != LABEL:
        raise ValueError('Exact test-container identity or owner differs')
    return info


def start(owned_test_bypass=False, image_id=None, database_max_connections=None, unrestricted_cpu=False):
    if unrestricted_cpu and not owned_test_bypass:
        raise ValueError('CPU quota removal requires the owned test bypass')
    if database_max_connections is not None and (not owned_test_bypass or isinstance(database_max_connections, bool) or not isinstance(database_max_connections, int) or not 100 <= database_max_connections <= 512):
        raise ValueError('Database concurrency override requires the owned test bypass and an explicit 100-512 connection budget')
    selected_image = image_id or IMAGE
    state = BASE / 'evidence/live-runtime.json'
    if state.exists():
        raise ValueError('An immutable live-test runtime record already exists')
    source = command('git', '-C', str(BASE / 'source'), 'rev-parse', 'HEAD').stdout.strip()
    record = {'source_sha': source, 'execution_host': 'Tencent cloud', 'started_at_unix': time.time(),
              'containers': {}, 'ok': False, 'image_id': selected_image,
              'client_connection': 'Local real Godot clients through strict SSH forwarding; HTTP/ticket WS over SSH is distinct from already verified public HTTPS/WSS.',
              'mode': 'Development on a private loopback test listener; local diagnostics explicitly enabled',
              'default_request_limits': {'auth_per_minute': 10, 'economy_per_minute': 30, 'market_read_per_minute': 120},
              'owned_test_bypass': owned_test_bypass,
              'unrestricted_application_database_cpu': unrestricted_cpu,
              'effective_admission': {'ip_policy_limits_enabled': not owned_test_bypass,
                                      'realtime_command_quota_enabled': not owned_test_bypass,
                                      'application_database_pool_enabled': not owned_test_bypass},
              'controller_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'candidate_activation': False, 'live_database_used': False}
    config = BASE / 'cache/live-monitoring'
    config.mkdir(mode=0o700, exist_ok=True)
    private = BASE / 'secrets'
    private.mkdir(mode=0o700, exist_ok=True)
    evidence = BASE / 'live-evidence'
    evidence.mkdir(mode=0o700, exist_ok=False)
    try:
        for name in NAMES.values():
            if docker('inspect', name, check=False).returncode == 0:
                raise ValueError('A declared test-container name is already occupied')
        live = inspect('fantasycard-cloud-server-1')
        if live['Image'] != selected_image:
            raise ValueError('Production image changed since verified source freeze')
        for role, name in [('otel', 'fantasycard-cloud-otel-collector-1'),
                           ('prometheus', 'fantasycard-cloud-prometheus-1')]:
            record[role + '_image_id'] = inspect(name)['Image']
        node = inspect('fantasycard-cloud-node-exporter-1')
        node_ip = node['NetworkSettings']['Networks']['fantasycard-cloud_default']['IPAddress']
        record['host_metric_source'] = {'container_id': node['Id'], 'address': node_ip + ':9100', 'scope': 'actual shared Tencent host'}
        otel = config / 'otel.yaml'
        otel.write_text('''receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:24317
      http:
        endpoint: 127.0.0.1:24318
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 96
    spike_limit_mib: 24
  batch:
    timeout: 1s
exporters:
  prometheus:
    endpoint: 127.0.0.1:29464
    resource_to_telemetry_conversion:
      enabled: true
service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
''')
        prom = config / 'prometheus.yml'
        prom.write_text('''global:
  scrape_interval: 10s
  evaluation_interval: 10s
scrape_configs:
  - job_name: fantasycard
    static_configs:
      - targets: [127.0.0.1:29464]
        labels:
          instance: otel-collector:9464
  - job_name: node
    static_configs:
      - targets: [''' + node_ip + ''':9100]
        labels:
          instance: node-exporter:9100
''')
        for path in [otel, prom]:
            path.chmod(0o644)
        database = 'pr13_tencent_live_' + secrets.token_hex(8)
        password = secrets.token_hex(24)
        pg_env = private / 'live-pg.env'
        pg_env.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB=' + database + '\nPOSTGRES_PASSWORD=' + password + '\n')
        pg_env.chmod(0o600)
        app_env = private / 'live-server.env'
        app_env.write_text('ASPNETCORE_ENVIRONMENT=Development\nASPNETCORE_URLS=http://127.0.0.1:28081\n'
                          'AllowedHosts=localhost;127.0.0.1\nIdentity__EnableLocalAuth=true\n'
                          'ConnectionStrings__Postgres=Host=127.0.0.1;Port=25434;Database=' + database + ';Username=fantasycard;Password=' + password + ';Timeout=10;Command Timeout=30\n'
                          'ProtobufHttp__AllowLegacyJson=false\nRealtime__AllowLegacyAccessTokenQuery=false\n'
                          'Matchmaking__BotFillDelaySeconds=30\nDiagnostics__LocalMetricsFile=/evidence/server-metrics.private.jsonl\n'
                          'OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:24317\nOTEL_METRIC_EXPORT_INTERVAL=1000\n')
        if owned_test_bypass:
            with app_env.open('a') as stream:
                stream.write('RequestLimits__OwnedTestBypass=true\nRequestLimits__OwnedTestSession=' + LABEL + '\n')
        app_env.chmod(0o600)

        def launch(role, args, image, tail=()):
            record['containers'][role] = docker('run', '-d', '--name', NAMES[role], '--label', 'codex.session=' + LABEL,
                                                '--label', 'codex.scope=disposable-cloud', *args, image, *tail).stdout.strip()
            save(state, record)

        pg_memory = '384m' if database_max_connections is not None else '192m'
        pg_tail = ['postgres', '-c', 'max_connections=' + str(database_max_connections)] if database_max_connections is not None else ()
        pg_cpu = [] if unrestricted_cpu else ['--cpus', '0.3']
        app_cpu = [] if unrestricted_cpu else ['--cpus', '0.8']
        launch('postgres', ['--memory', pg_memory, *pg_cpu, '-p', '127.0.0.1:25434:5432', '--env-file', str(pg_env)], PG_IMAGE, pg_tail)
        record['database_memory_budget'] = pg_memory
        deadline = time.monotonic() + 60
        # The entrypoint's temporary initialization server accepts Unix sockets
        # before restarting. TCP readiness proves the final database is serving.
        while docker('exec', NAMES['postgres'], 'pg_isready', '-h', '127.0.0.1', '-U', 'fantasycard', '-d', database, check=False).returncode:
            if time.monotonic() >= deadline:
                raise TimeoutError('Owned live-test PostgreSQL readiness')
            time.sleep(1)
        launch('otel', ['--network', 'host', '--memory', '128m', '--cpus', '0.2', '-v', str(otel) + ':/etc/pr13.yaml:ro'], record['otel_image_id'], ['--config=/etc/pr13.yaml'])
        launch('prometheus', ['--network', 'host', '--memory', '192m', '--cpus', '0.2', '-v', str(prom) + ':/etc/pr13.yml:ro'], record['prometheus_image_id'],
               ['--config.file=/etc/pr13.yml', '--web.listen-address=127.0.0.1:19190', '--storage.tsdb.path=/prometheus', '--storage.tsdb.retention.time=6h'])
        launch('server', ['--network', 'host', '--memory', '512m', *app_cpu, '--user', '1000:1000', '--env-file', str(app_env), '-v', str(evidence) + ':/evidence'], selected_image)
        deadline = time.monotonic() + 120
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:28081/health/ready', timeout=3) as response:
                    if response.status == 200:
                        break
            except OSError:
                if not owned(record, 'server')['State']['Running']:
                    raise RuntimeError('Owned live-test server exited')
            if time.monotonic() >= deadline:
                raise TimeoutError('Owned live-test application readiness')
            time.sleep(1)
        record.update(ok=True, database_name=database, runtime_revision=owned(record, 'server')['Config']['Labels'].get('org.opencontainers.image.revision'),
                      host_server_pid=owned(record, 'server')['State']['Pid'], prometheus_url='http://127.0.0.1:19190', server_url='http://127.0.0.1:28081',
                      config_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [otel, prom]})
        actual_env = dict(value.split('=', 1) for value in owned(record, 'server')['Config']['Env'])
        if (actual_env.get('RequestLimits__OwnedTestBypass', 'false').lower() == 'true') != owned_test_bypass:
            raise ValueError('Effective owned-test bypass environment differs')
        record['database_max_connections'] = int(docker(
            'exec', NAMES['postgres'], 'psql', '-X', '-U', 'fantasycard', '-d', database,
            '-At', '-c', 'SHOW max_connections').stdout.strip())
        if database_max_connections is not None and record['database_max_connections'] != database_max_connections:
            raise ValueError('Effective database concurrency differs from the registered override')
        record['effective_cpu_quotas'] = {role: owned(record,role)['HostConfig']['NanoCpus'] for role in ['server','postgres']}
        if unrestricted_cpu and any(record['effective_cpu_quotas'].values()):
            raise ValueError('Owned application/database CPU quotas were not removed')
        save(state, record)
        return record
    except Exception as error:
        record['error'] = type(error).__name__
        save(state, record)
        stop(record)
        raise


def audit(record):
    owned(record, 'postgres')
    query = "BEGIN READ ONLY; SET LOCAL statement_timeout='10s'; SELECT json_build_object('pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'active_match_players',(SELECT count(*) FROM match_players WHERE state='Active'),'settlements',(SELECT count(*) FROM match_settlements),'ledger_rows',(SELECT count(*) FROM economy_ledger)); ROLLBACK;"
    raw = docker('exec', NAMES['postgres'], 'psql', '-X', '-U', 'fantasycard', '-d', record['database_name'], '-At', '-v', 'ON_ERROR_STOP=1', '-c', query).stdout
    values = [json.loads(line) for line in raw.splitlines() if line.startswith('{')]
    if len(values) != 1:
        raise ValueError('Unique owned database audit result required')
    return {'actual': values[0], 'read_only': True, 'execution_host': 'Tencent cloud'}


def stop(record):
    cleanup = {}
    for role in reversed(list(record['containers'])):
        try:
            owned(record, role)
            if role == 'server':
                logs = docker('logs', NAMES[role], check=False)
                (BASE / 'live-evidence/server.private.log').write_text(logs.stdout + logs.stderr)
            docker('rm', '-f', NAMES[role])
            cleanup[role] = True
        except Exception as error:
            cleanup[role] = type(error).__name__
    save(BASE / 'evidence/live-runtime-cleanup.json', {'cleanup': cleanup, 'all_removed': all(v is True for v in cleanup.values())})
    return cleanup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['start', 'audit', 'stop'])
    parser.add_argument('--owned-test-bypass', action='store_true', help='Disable IP/realtime quotas and the application connection pool on this owned test instance')
    parser.add_argument('--image-id', help='Exact verified current production image ID to reuse')
    parser.add_argument('--database-max-connections', type=int, help='Owned bypass only: temporary physical PostgreSQL connection budget, 100-512')
    parser.add_argument('--unrestricted-cpu', action='store_true', help='Owned bypass only: application and database share the real host CPU without artificial per-container quotas')
    args = parser.parse_args()
    if args.operation == 'start':
        value = start(args.owned_test_bypass, args.image_id, args.database_max_connections, args.unrestricted_cpu)
    else:
        record = json.loads((BASE / 'evidence/live-runtime.json').read_text())
        value = audit(record) if args.operation == 'audit' else stop(record)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
