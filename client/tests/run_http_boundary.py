"""Real loopback HTTP framing faults; no production network or credentials."""
import argparse
import json
import re
import gzip
import zlib
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from fixture_runtime import isolated_environment


def evaluate_output(output, exit_code, tls_fault):
    rows = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict): rows.append(value)
        except json.JSONDecodeError:
            pass
    summaries = [row for row in rows if row.get('suite') == 'http-boundary']
    tls_rows = [row for row in rows if row.get('path') == 'invalid-tls']
    tls_rejected = len(tls_rows) == 1 and tls_rows[0].get('passed') is True and tls_rows[0].get('bytes') == 0
    errors = [line.strip() for line in output.splitlines()
              if re.search(r'ERROR:|Parse Error|Failed to load script', line)]
    expected = [line for line in errors if tls_fault and tls_rejected and
                re.fullmatch(r'ERROR: TLS handshake error: -[0-9]+', line)]
    unexpected = [line for line in errors if line not in expected]
    # Prove the certificate caused the negative case, rather than a timeout.
    tls_valid = tls_rejected and len(expected) == 1 if tls_fault else not tls_rows
    return {'ok': exit_code == 0 and len(summaries) == 1 and summaries[0].get('ok') is True and
                  summaries[0].get('failures') == [] and tls_valid and not unexpected,
            'expected_tls_errors': expected, 'unexpected_errors': unexpected,
            'tls_rejection_verified': tls_rejected and len(expected) == 1}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args): pass
    def do_HEAD(self): self.respond()
    def do_GET(self): self.respond()
    def respond(self):
        encoded = (gzip.compress(b'abcdef') if self.path == '/gzip' else
                   zlib.compress(b'abcdef') if self.path == '/deflate' else
                   gzip.compress(b'x' * (2 * 1024 * 1024 + 1)) if self.path == '/gzip-limit' else None)
        self.send_response(204 if self.path == "/empty" else 200)
        if self.path in ("/chunked", "/truncated-chunk"):
            self.send_header("Transfer-Encoding", "chunked")
        elif self.path != "/close-body":
            size = len(encoded) if encoded else 2 * 1024 * 1024 + 1 if self.path == "/production-limit" else 6000 if self.path == "/limit" else 9 if self.path == "/truncated" else 0 if self.path == "/empty" else 6
            self.send_header("Content-Length", str(size))
        if self.path == "/bad-gzip": self.send_header("Content-Encoding", "gzip")
        if encoded: self.send_header('Content-Encoding', 'deflate' if self.path == '/deflate' else 'gzip')
        if self.path in ("/close-body", "/close-length", "/truncated", "/truncated-chunk"):
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if self.command == "HEAD" or self.path == "/empty": return
        if self.path == "/slow": time.sleep(.6)
        body = (encoded if encoded else b"3\r\nabc\r\n3\r\ndef\r\n0\r\nX-Trace: fixture\r\n\r\n" if self.path == "/chunked" else
                b"3\r\nabc\r\n" if self.path == "/truncated-chunk" else
                b"abc" if self.path == "/truncated" else
                b"x" * (2 * 1024 * 1024 + 1) if self.path == "/production-limit" else
                b"x" * 6000 if self.path == "/limit" else b"abcdef")
        try:
            self.wfile.write(body)
            self.wfile.flush()
            if self.path == "/idle-close":
                time.sleep(.05)
                self.close_connection = True
        except (BrokenPipeError, ConnectionResetError, OSError): pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs/pr13-http-boundary"))
    parser.add_argument("--tls-fault", action="store_true", help="Generate an owned untrusted loopback TLS certificate with openssl")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = args.output.resolve()
    (work/"network").mkdir(parents=True, exist_ok=True)
    (work/"tests").mkdir(exist_ok=True)
    shutil.copyfile(root/"client/network/reusable_http_client.gd", work/"network/reusable_http_client.gd")
    shutil.copyfile(root/"client/tests/run_http_boundary.gd", work/"tests/run_http_boundary.gd")
    (work/"project.godot").write_text('[application]\nconfig/name="HTTP boundaries"\n', encoding="utf8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    env = isolated_environment(work, FANTASYCARD_SERVER_URL=f"http://127.0.0.1:{server.server_port}")
    tls_server = None
    tls_worker = None
    if args.tls_fault:
        cert = work/'untrusted-fixture-cert.pem'
        key = work/'untrusted-fixture-key.pem'
        config = work/'openssl-fixture.cnf'
        config.write_bytes(b'[req]\ndistinguished_name=dn\n[dn]\n')
        try:
            generated = subprocess.run(['openssl','req','-config',str(config),'-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],
                                       capture_output=True, timeout=30, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (work/'certificate-generation.log').write_bytes(generated.stderr)
            generated.check_returncode()
        except BaseException:
            server.shutdown(); server.server_close(); worker.join(timeout=5)
            raise
        tls_server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert,key)
        tls_server.socket = context.wrap_socket(tls_server.socket,server_side=True)
        tls_worker = threading.Thread(target=tls_server.serve_forever,daemon=True)
        tls_worker.start()
        env['PR13_INVALID_TLS_ORIGIN'] = f'https://localhost:{tls_server.server_port}'
    command = [args.godot, "--headless", "--path", str(work), "--script", "res://tests/run_http_boundary.gd"]
    try:
        run = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf8",
                             errors="replace", timeout=60, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        output = run.stdout + run.stderr
        (work/"boundary.log").write_text(output, encoding="utf8")
        print(output)
        result = evaluate_output(output, run.returncode, args.tls_fault)
        (work/"result.json").write_text(json.dumps({**result, "command": command, "exit_code": run.returncode}), encoding="utf8")
        return 0 if result['ok'] else 1
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"") + (exc.stderr or b"")
        if isinstance(output, bytes): output = output.decode("utf8", errors="replace")
        (work/"boundary.log").write_text(output + "\nFIXTURE TIMEOUT", encoding="utf8")
        (work/"result.json").write_text(json.dumps({"ok": False, "command": command,
                                                   "exit_code": None, "timeout": True}), encoding="utf8")
        return 1
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)
        if tls_server:
            tls_server.shutdown(); tls_server.server_close(); tls_worker.join(timeout=5)


if __name__ == "__main__": raise SystemExit(main())
