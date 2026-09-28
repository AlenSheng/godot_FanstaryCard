"""Verify the repository Caddy boundary over real local TLS and WSS.

Uses a private, one-day certificate (no system trust changes), an existing server
assembly, and a newly owned PostgreSQL schema. Never contacts the production host.
"""
import argparse
import base64
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def string_field(number, value):
    value = value.encode()
    return varint(number * 8 + 2) + varint(len(value)) + value


def fields(data):
    offset = 0
    result = {}
    def integer():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('Invalid probe response varint')
    while offset < len(data):
        tag = integer()
        if tag & 7 == 0:
            value = integer()
        elif tag & 7 == 2:
            size = integer()
            value = data[offset:offset + size]
            if len(value) != size:
                raise ValueError('Truncated probe response')
            offset += size
        else:
            raise ValueError('Unexpected probe response field')
        result[tag >> 3] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dotnet', 'server-dll', 'psql', 'connection-file', 'caddy'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--work-dir', default='work/local-tls-validation')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = (repo / args.work_dir).resolve()
    if output.exists():
        raise ValueError('Choose a new output directory to preserve prior TLS evidence')
    output.mkdir(parents=True)
    connection = Path(args.connection_file).read_text(encoding='utf-8-sig').strip()
    settings = dict((k.strip().lower(), v.strip()) for k, v in
                    (item.split('=', 1) for item in connection.split(';') if '=' in item))
    if settings.get('host') not in ('127.0.0.1', 'localhost', '::1') or settings.get('database') != 'fc_migration_tests':
        raise ValueError('Use the dedicated loopback migration database')
    schema = 'fc_tls_' + uuid.uuid4().hex
    env = dict(os.environ, PGHOST=settings['host'], PGPORT=settings.get('port', '5432'),
               PGDATABASE=settings['database'], PGUSER=settings.get('username', ''), PGPASSWORD=settings.get('password', ''))
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    def sql(query):
        run = subprocess.run([args.psql, '-X', '-v', 'ON_ERROR_STOP=1', '-c', query],
                             env=env, capture_output=True, timeout=30, creationflags=flags)
        if run.returncode:
            raise RuntimeError('Isolated test schema operation failed; database output withheld')
    results, secrets, processes, logs = [], [], [], []
    owned = False
    completed = False
    def check(name, condition):
        results.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)
    def launch(command, log_name, child_env):
        log = (output / log_name).open('wb')
        logs.append(log)
        process = subprocess.Popen(command, cwd=repo / 'server/src/FantasyCard.Server',
                                   env=child_env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        processes.append(process)
        return process
    listeners = [socket.socket() for _ in range(4)]
    for listener in listeners:
        listener.bind(('127.0.0.1', 0))
    api, public, origin, admin = [s.getsockname()[1] for s in listeners]
    for listener in listeners:
        listener.close()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated-loopback-test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
                   .sign(key, hashes.SHA256()))
    cert_path, key_path = output / 'local.pem', output / 'local.key'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.create_default_context(cafile=str(cert_path))
    tls = 'tls "' + cert_path.as_posix() + '" "' + key_path.as_posix() + '"'
    config = (repo / 'server/Caddyfile').read_text(encoding='utf-8-sig')
    config = config.replace('{\n', '{\n\tadmin off\n\tdefault_bind 127.0.0.1\n\tauto_https off\n', 1)
    config = config.replace('relicbound.cn, www.relicbound.cn {', f'https://127.0.0.1:{public} {{\n\t{tls}')
    config = config.replace('43.172.70.182 {', f'https://127.0.0.1:{origin} {{')
    config = config.replace('tls /etc/caddy/certs/ip2.crt /etc/caddy/certs/ip2.key', tls)
    config = config.replace('www.relicbound.cn:20000 {', f'https://127.0.0.1:{admin} {{\n\t{tls}')
    config = config.replace('server:8080', f'127.0.0.1:{api}').replace('/srv/site', (repo / 'server/site').as_posix())
    config_path = output / 'Caddyfile.local'
    config_path.write_text(config, encoding='utf-8')
    def request(port, path, body=None, headers=None):
        req = urllib.request.Request(f'https://127.0.0.1:{port}' + path, data=body, headers=headers or {})
        try:
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
    try:
        sql('CREATE SCHEMA ' + schema)
        owned = True
        admin_key = uuid.uuid4().hex + uuid.uuid4().hex
        secrets.append(admin_key)
        child = dict(os.environ, DOTNET_ROOT=str(Path(args.dotnet).resolve().parent),
                     ASPNETCORE_ENVIRONMENT='Development', ASPNETCORE_URLS=f'http://127.0.0.1:{api}',
                     ConnectionStrings__Postgres=connection.rstrip(';') + ';Search Path=' + schema,
                     Identity__EnableLocalAuth='true', Admin__ApiKey=admin_key,
                     ProtobufHttp__AllowLegacyJson='false', Realtime__AllowLegacyAccessTokenQuery='false',
                     Logging__LogLevel__Default='Warning')
        for name in list(child):
            if name.startswith('OTEL_EXPORTER_'):
                child.pop(name)
        server = launch([args.dotnet, str(Path(args.server_dll).resolve())], 'server.log', child)
        for _ in range(150):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{api}/health/ready', timeout=.5) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(.2)
        else:
            raise RuntimeError('Local server readiness timeout')
        proxy_env = dict(os.environ, APPDATA=str(output / 'appdata'), XDG_DATA_HOME=str(output / 'caddy-data'))
        launch([args.caddy, 'run', '--config', str(config_path), '--adapter', 'caddyfile'], 'caddy.log', proxy_env)
        for _ in range(80):
            try:
                if request(public, '/health/ready')[0] == 200:
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(.1)
        else:
            raise RuntimeError('Local TLS readiness timeout')
        check('HTTPS validates private CA and IP SAN', True)
        check('JSON announcement remains available over TLS', request(public, '/api/v1/client-info')[1].get_content_type() == 'application/json')
        headers = {'Content-Type': 'application/protobuf', 'Accept': 'application/protobuf'}
        status, response_headers, body = request(public, '/api/v1/auth/local',
                                                string_field(1, uuid.uuid4().hex) + string_field(2, 'TLS QA'), headers)
        check('actual PB login through TLS proxy', status == 200 and response_headers.get_content_type() == 'application/protobuf')
        token = fields(body)[1].decode()
        secrets.append(token)
        headers['Authorization'] = 'Bearer ' + token
        status, response_headers, body = request(public, '/api/v1/bootstrap', headers=headers)
        check('actual PB Bootstrap through TLS proxy', status == 200 and len(body) > 8192 and bool(fields(body).get(3)))
        check('private response cannot be cached or MIME-sniffed', 'no-store' in response_headers.get('Cache-Control', '') and response_headers.get('X-Content-Type-Options') == 'nosniff')
        status, _, body = request(public, '/api/v1/realtime/ticket', b'', headers)
        check('PB ticket through TLS proxy', status == 200)
        ticket = fields(body)[1].decode()
        secrets.append(ticket)
        with context.wrap_socket(socket.create_connection(('127.0.0.1', public), timeout=10), server_hostname='127.0.0.1') as ws:
            nonce = base64.b64encode(os.urandom(16)).decode()
            ws.sendall((f'GET /ws/v1/session?ticket={ticket} HTTP/1.1\r\nHost: 127.0.0.1:{public}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            stream = ws.makefile('rb')
            check('real WSS upgrade', b' 101 ' in stream.readline())
            upgrade = {}
            while True:
                line = stream.readline()
                if line == b'\r\n':
                    break
                name, value = line.decode().split(':', 1)
                upgrade[name.lower()] = value.strip()
            expected = base64.b64encode(hashlib.sha1((nonce + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            check('WSS accept hash verified', upgrade.get('sec-websocket-accept') == expected)
            def receive():
                first, second = stream.read(2)
                check('server sends complete binary frame', first == 0x82 and second < 128)
                size = second
                if size == 126:
                    size = int.from_bytes(stream.read(2), 'big')
                elif size == 127:
                    size = int.from_bytes(stream.read(8), 'big')
                data = stream.read(size)
                if len(data) != size:
                    raise RuntimeError('Truncated WebSocket frame')
                return fields(data)
            check('real WSS session.connected', receive()[2] == b'session.connected')
            payload = b'\x08\x01' + string_field(2, 'ping') + string_field(3, uuid.uuid4().hex)
            mask = os.urandom(4)
            ws.sendall(bytes([0x82, 0x80 | len(payload)]) + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))
            check('real binary pong over WSS', receive()[2] == b'pong')
            stream.close()
        check('public administration denied', request(public, '/api/admin/client-settings')[0] == 404)
        check('management endpoint requires key', request(admin, '/api/admin/client-settings')[0] in (401, 403))
        check('management JSON with valid key', request(admin, '/api/admin/client-settings', headers={'X-Admin-Key': admin_key})[0] == 200)
        check('management blocks gameplay', request(admin, '/api/v1/bootstrap', headers=headers)[0] == 404)
        check('origin listener denies public API', request(origin, '/api/v1/client-info')[0] == 404)
        server.terminate()
        server.wait(timeout=15)
        marker = 'tls-probe-' + uuid.uuid4().hex
        secrets.append(marker)
        check('TLS proxy returns 502 with unavailable upstream', request(public, '/ws/v1/session?ticket=' + marker, headers={'X-Admin-Key': admin_key})[0] == 502)
        completed = True
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()
        if owned:
            sql('DROP SCHEMA ' + schema + ' CASCADE')
        combined = '\n'.join(path.read_text(encoding='utf-8', errors='replace') for path in output.glob('*.log'))
        results.append(dict(name='all planned TLS checks completed', passed=completed))
        results.append(dict(name='runtime logs contain no session or admin credentials', passed=not any(secret in combined for secret in secrets)))
        (output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    if not all(item['passed'] for item in results):
        raise RuntimeError('Local TLS validation failed')
    print(json.dumps({'passed': len(results), 'failed': 0, 'scope': 'private loopback TLS/WSS; not production TLS or cloud ACL'}))


if __name__ == '__main__':
    main()
