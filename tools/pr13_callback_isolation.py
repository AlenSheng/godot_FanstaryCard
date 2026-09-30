"""Bounded OFFLINE Godot callback cases with an owned loopback protobuf service."""
from __future__ import annotations

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "client/tests"))
from fixture_runtime import isolated_environment
from http_protobuf_fixture import encode

VERSION = json.loads((ROOT / "client/data/catalog.json").read_text())["version"]
REQUEST_GATE_SECONDS = 5
CASE_SECONDS = 6
RUN_SECONDS = 55


def bootstrap(receipt=None, account="callback-A"):
    return {"config_version": VERSION, "player": {"user_id": account, "selected_class": "Mage"},
            "wallet": {"gold": 17}, "materials": {}, "inventory": {}, "shop": {}, "market": [],
            "mail": {}, "unfinished_settlement": receipt}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def respond(self, code, body, media):
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        with self.server.lock:
            op = data["op"]
            if op == "reset":
                self.server.plans.clear()
                self.server.counts.clear()
                self.server.case_id = data["case_id"]
            elif op == "plan":
                gate = threading.Event()
                if not data.get("paused", False):
                    gate.set()
                self.server.plans.append({**data, "gate": gate, "started": False, "done": False})
            elif op == "release":
                self.server.plans[data["index"]]["gate"].set()
            result = {"counts": dict(self.server.counts), "plans": [
                {"path": p["path"], "started": p["started"], "done": p["done"]} for p in self.server.plans]}
        self.respond(200, json.dumps(result).encode(), "application/json")

    def do_GET(self):
        if self.path == "/api/v1/client-info":
            self.respond(200, json.dumps({"configVersion": VERSION}).encode(), "application/json")
            return
        with self.server.lock:
            self.server.counts[self.path] += 1
            plan = next((p for p in self.server.plans if p["path"] == self.path and not p["started"]), None)
            if plan is not None:
                plan["started"] = True
            record = {"case_id": self.server.case_id, "path": self.path, "started_ns": time.monotonic_ns(),
                      "paused": bool(plan and plan.get("paused")), "authorization": self.headers.get("Authorization"),
                      "trace_id": self.headers.get("X-Trace-Id"), "request_media": self.headers.get("Accept")}
            self.server.records.append(record)
        if plan is None:
            self.respond(404, encode("HttpError", {"status": 404, "detail": "No registered callback response"}), "application/protobuf")
            record.update(status=404, completed_ns=time.monotonic_ns())
            return
        released = plan["gate"].wait(REQUEST_GATE_SECONDS)
        receipt = {"settlement_id": plan.get("receipt_id", ""), "match_id": plan.get("match_id", ""),
                   "player_id": plan.get("account", "callback-A"), "result": "Dead", "details": {}}
        data = bootstrap(receipt if plan.get("receipt_id") else None, plan.get("account", "callback-A")) if self.path == "/api/v1/bootstrap" else receipt
        self.respond(200, encode("BootstrapResponse" if self.path == "/api/v1/bootstrap" else "SettlementResponse", data), "application/protobuf")
        with self.server.lock:
            plan["done"] = True
            record.update(status=200, gate_released=released, completed_ns=time.monotonic_ns())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    executable = os.environ["A3GAME_GODOT_EXECUTABLE"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.lock = threading.Lock()
    server.plans, server.records, server.counts, server.case_id = [], [], Counter(), "initialization"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = isolated_environment(output, FANTASYCARD_SERVER_URL=f"http://127.0.0.1:{server.server_port}",
                               FANTASYCARD_LOAD_RUN_ID="pr13-callback-offline", PR13_CALLBACK_CASE_SECONDS=str(CASE_SECONDS))
    command = [executable, "--headless", "--path", str(ROOT / "client"), "--script", "res://tests/pr13_callback_isolation.gd"]
    started = time.monotonic()
    try:
        run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=RUN_SECONDS)
        (output / "godot.stdout.log").write_text(run.stdout)
        (output / "godot.stderr.log").write_text(run.stderr)
        lines = [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{") and '"callback_case":' in line]
        (output / "cases.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in lines))
        (output / "service_requests.jsonl").write_text("".join(json.dumps(row) + "\n" for row in server.records))
        cases_ok = len(lines) == 6 and all(row["status"] == "Passed" for row in lines)
        requests_ok = all(row.get("request_media") == "application/protobuf" and row.get("gate_released", True) for row in server.records)
        ok = run.returncode == 0 and cases_ok and requests_ok and "SCRIPT ERROR" not in run.stderr
        tracked = subprocess.check_output(["git", "ls-files", "client"], cwd=ROOT, text=True).splitlines()
        sources = sorted(set([p for p in tracked if not p.startswith("client/evidence/")
                              and Path(p).suffix in {".gd", ".tscn", ".tres", ".godot", ".json"}]
                             + ["client/tests/pr13_callback_isolation.gd", "tools/pr13_callback_isolation.py",
                                "client/tests/http_protobuf_fixture.py", "client/tests/fixture_runtime.py",
                                "docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json"]))
        manifest = [{"path": p, "bytes": (ROOT / p).stat().st_size, "sha256": sha(ROOT / p)} for p in sources]
        (output / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (output / "commands.json").write_text(json.dumps({"command": command, "cwd": str(ROOT), "exit_code": run.returncode,
            "elapsed_seconds": time.monotonic() - started, "deadlines": {"request_gate_seconds": REQUEST_GATE_SECONDS, "case_seconds": CASE_SECONDS, "run_seconds": RUN_SECONDS},
            "godot": subprocess.check_output([executable, "--version"], text=True).strip(), "python": sys.version,
            "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "working_tree_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
            "tracked_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)).hexdigest(),
            "skipped": [], "profile": "OFFLINE"}, indent=2) + "\n")
        report = {"ok": ok, "Accepted": False, "status": "Partial" if ok else "Failed", "profile": "OFFLINE",
                  "canonical_cases": lines, "service_requests": len(server.records), "controlled_delayed_requests": sum(row["paused"] for row in server.records),
                  "remaining_profiles": ["POSTGRES", "LIVE"], "support_only": ["PR13-B11.2-T01", "PR13-B11.2-T02"],
                  "support_remaining_profiles": ["POSTGRES", "LIVE", "RENDER"],
                  "qualification": "Real Godot GameStore _on_event/request entries and protobuf loopback HTTP; events are controlled component injections, with no database or live server."}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        evidence_manifest = [{"path": p.name, "bytes": p.stat().st_size, "sha256": sha(p)}
                             for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"]
        (output / "manifest.json").write_text(json.dumps(evidence_manifest, indent=2) + "\n")
        print(json.dumps({"ok": ok, "exit_code": run.returncode, "cases": len(lines), "failed": [r["callback_case"] for r in lines if r["status"] != "Passed"], "output": str(output)}))
        return 0 if ok else 1
    finally:
        for plan in server.plans:
            plan["gate"].set()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
