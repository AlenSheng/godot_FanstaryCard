"""Run isolated session/authentication tests without contacting a game server."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
VERSION = json.loads((ROOT / "client/data/catalog.json").read_text(encoding="utf-8"))["version"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        prefix, path = self.normalized_path()
        if path == "/":
            self.respond(200, {"configVersion": "outdated" if prefix == "mismatch" else VERSION, "capabilities": ["identity.local"]})
        elif path == "/health/ready":
            self.respond(200, {"status": "Healthy"})
        elif path == "/api/v1/bootstrap":
            self.respond(200, {
                "configVersion": "outdated" if prefix == "bootstrap-mismatch" else VERSION,
                "player": {"userId": "fixture-player", "displayName": "Fixture", "selectedClass": "Mage"},
                "wallet": {"gold": 0}, "decks": [], "equippedLoadouts": [],
                "unfinishedMatch": None, "unfinishedSettlement": None,
            })
        elif path == "/late-unauthorized":
            time.sleep(0.4)
            self.respond(401, {"detail": "Expired old token"})
        elif path == "/unauthorized":
            self.respond(401, {"detail": "Expired token"})
        else:
            self.respond(404, {})

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size:
            self.rfile.read(size)
        prefix, path = self.normalized_path()
        if path == "/api/v1/auth/local":
            self.server.sign_ins[prefix] = self.server.sign_ins.get(prefix, 0) + 1
            self.respond(200, {"accessToken": "isolated-fixture-token", "expiresAt": "2030-01-01T00:00:00Z", "player": {"userId": "fixture-player"}})
        else:
            self.respond(404, {})

    def normalized_path(self):
        for prefix in ["bootstrap-mismatch", "mismatch"]:
            if self.path.startswith("/" + prefix + "/"):
                return prefix, self.path[len(prefix) + 1:]
        return "matching", self.path

    def respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def main():
    executable = os.environ.get("A3GAME_GODOT_EXECUTABLE")
    if not executable:
        executable = json.loads((ROOT / "tools/engine-local/godot-4.7.2-stable-windows-x86_64.json").read_text())["executable"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.sign_ins = {}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    environment = dict(os.environ, FANTASYCARD_SESSION_TEST_URL=f"http://127.0.0.1:{server.server_port}")
    try:
        run = subprocess.run([executable, "--headless", "--path", str(ROOT / "client"), "--script", "res://tests/session_integration.gd"], env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        print(run.stdout)
        if run.stderr:
            print(run.stderr)
        no_early_sign_in = server.sign_ins.get("mismatch", 0) == 0
        print(json.dumps({"config_mismatch_prevented_sign_in": no_early_sign_in, "isolated_http_sign_ins": server.sign_ins}))
        return 0 if run.returncode == 0 and "SCRIPT ERROR" not in run.stderr and no_early_sign_in else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
