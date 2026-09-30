"""Real loopback HTTP framing faults; no production network or credentials."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from fixture_runtime import isolated_environment


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args): pass
    def do_HEAD(self): self.respond()
    def do_GET(self): self.respond()
    def respond(self):
        self.send_response(204 if self.path == "/empty" else 200)
        if self.path in ("/chunked", "/truncated-chunk"):
            self.send_header("Transfer-Encoding", "chunked")
        elif self.path != "/close-body":
            size = 6000 if self.path == "/limit" else 9 if self.path == "/truncated" else 0 if self.path == "/empty" else 6
            self.send_header("Content-Length", str(size))
        if self.path in ("/close-body", "/close-length", "/truncated", "/truncated-chunk"):
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if self.command == "HEAD" or self.path == "/empty": return
        if self.path == "/slow": time.sleep(.6)
        body = (b"3\r\nabc\r\n3\r\ndef\r\n0\r\nX-Trace: fixture\r\n\r\n" if self.path == "/chunked" else
                b"3\r\nabc\r\n" if self.path == "/truncated-chunk" else
                b"abc" if self.path == "/truncated" else
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
    command = [args.godot, "--headless", "--path", str(work), "--script", "res://tests/run_http_boundary.gd"]
    try:
        run = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf8",
                             errors="replace", timeout=60, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        output = run.stdout + run.stderr
        (work/"boundary.log").write_text(output, encoding="utf8")
        print(output)
        passed = run.returncode == 0 and "ERROR:" not in output and '"ok":true' in output
        (work/"result.json").write_text(json.dumps({"ok": passed, "command": command, "exit_code": run.returncode}), encoding="utf8")
        return 0 if passed else 1
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"") + (exc.stderr or b"")
        if isinstance(output, bytes): output = output.decode("utf8", errors="replace")
        (work/"boundary.log").write_text(output + "\nFIXTURE TIMEOUT", encoding="utf8")
        (work/"result.json").write_text(json.dumps({"ok": False, "command": command,
                                                   "exit_code": None, "timeout": True}), encoding="utf8")
        return 1
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)


if __name__ == "__main__": raise SystemExit(main())
