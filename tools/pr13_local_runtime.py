"""Run bounded PR13 scenarios on an owned loopback host and disposable database."""
import argparse
from contextlib import AbstractContextManager
import hashlib
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, encoding="utf8", timeout=30,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)


def owned_database_info(container):
    result = run(["docker", "inspect", container])
    result.check_returncode()
    info = json.loads(result.stdout)[0]
    labels = info["Config"].get("Labels", {})
    if labels.get("codex.scope") != "disposable-local" or labels.get("codex.task") != "pr13-stages-20261008":
        raise ValueError("Database container is not owned by this task's disposable local scope")
    ports = info["NetworkSettings"]["Ports"].get("5432/tcp") or []
    if len(ports) != 1 or ports[0]["HostIp"] != "127.0.0.1":
        raise ValueError("Database must have one explicit loopback-only published port")
    environment = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    password = environment.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Owned database credentials unavailable")
    return {"container_id": info["Id"], "database_image_id": info["Image"], "port": int(ports[0]["HostPort"]),
            "password": password, "user": environment.get("POSTGRES_USER", "postgres")}


class LocalRuntime(AbstractContextManager):
    def __init__(self, output, container):
        self.output, self.container = output, container
        self.database = "pr13_local_" + uuid.uuid4().hex[:12]
        self.process, self.log = None, None
        self.output_created = self.database_created = False
        self.info = owned_database_info(container)
        self.record = {key: value for key, value in self.info.items() if key not in {"password", "user"}}
        self.record.update(database_owned=True, database=self.database, cleanup=False)

    def sql(self, statement):
        result = run(["docker", "exec", self.container, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", self.info["user"],
                      "-d", self.database, "-t", "-A", "-c", statement])
        result.check_returncode()
        return result.stdout.strip()

    def __enter__(self):
        try:
            return self._enter()
        except BaseException:
            if self.output_created:
                self.__exit__(*sys.exc_info())
            raise

    def _enter(self):
        self.output.mkdir(parents=True, exist_ok=False)
        self.output_created = True
        self.log = (self.output / "server.private.log").open("w", encoding="utf8")
        create = run(["docker", "exec", self.container, "createdb", "-U", self.info["user"], self.database])
        create.check_returncode()
        self.database_created = True
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        source_sha = run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
        # Private outputs avoid shared compiler/reference locks on Windows and
        # cannot accidentally reuse checked-in binaries from another checkout.
        build_workspace = self.output / "build-support"
        build_command = ["dotnet", "build", "src/FantasyCard.Server/FantasyCard.Server.csproj", "-c", "Release", "--nologo",
                         "--artifacts-path", str(build_workspace), "-p:UseSharedCompilation=false"]
        built = run(build_command, cwd=ROOT / "server")
        (self.output / "build.private.log").write_text(built.stdout + built.stderr, encoding="utf8")
        write(self.output / "build.json", {"command": build_command, "source_sha": source_sha, "exit_code": built.returncode})
        built.check_returncode()
        build = build_workspace / "bin/FantasyCard.Server/release"
        frozen = self.output / "server-frozen"
        shutil.copytree(build, frozen, ignore=shutil.ignore_patterns("*.pdb", "artifacts", "process-recovery-evidence"))
        dll = frozen / "FantasyCard.Server.dll"
        write(self.output / "server-artifacts.json", {"files": [
            {"path": file.relative_to(frozen).as_posix(), "bytes": file.stat().st_size,
             "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
            for file in sorted(frozen.rglob("*")) if file.is_file()]})
        self.record.update(server_url=self.url, source_sha=source_sha, build_source_sha=source_sha,
                           server_assembly_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),
                           candidate_defaults=False)
        connection = f"Host=127.0.0.1;Port={self.info['port']};Database={self.database};Username={self.info['user']};Password={self.info['password']};Timeout=10;Command Timeout=30"
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "DOTNET_ROOT", "TEMP", "TMP") if key in os.environ}
        env.update(ASPNETCORE_ENVIRONMENT="Development", ASPNETCORE_URLS=self.url,
                   ConnectionStrings__Postgres=connection, Identity__EnableLocalAuth="true",
                   ProtobufHttp__AllowLegacyJson="false", Realtime__AllowLegacyAccessTokenQuery="false",
                   Matchmaking__BotFillDelaySeconds="30")
        self.process = subprocess.Popen(["dotnet", str(dll)], cwd=dll.parent, env=env,
                                        stdout=self.log, stderr=subprocess.STDOUT,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.record.update(server_pid=self.process.pid, started_at=time.time())
        write(self.output / "runtime.json", self.record)
        deadline = time.monotonic() + 60
        try:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("Owned local server exited before readiness")
                try:
                    with urllib.request.urlopen(self.url + "/health/ready", timeout=3) as response:
                        if response.status == 200:
                            self.record["ready"] = True
                            write(self.output / "runtime.json", self.record)
                            return self
                except OSError:
                    time.sleep(.2)
            raise TimeoutError("Owned local server readiness deadline exceeded")
        except BaseException:
            raise

    def __exit__(self, *args):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.log is not None:
            self.log.close()
        removed = not self.database_created
        try:
            if self.database_created:
                drop = run(["docker", "exec", self.container, "dropdb", "--force", "-U", self.info["user"], self.database])
                removed = drop.returncode == 0
        except (OSError, subprocess.SubprocessError) as error:
            self.record["cleanup_error"] = type(error).__name__
        self.record.update(cleanup=removed and (self.process is None or self.process.poll() is not None),
                           database_removed=removed, ended_at=time.time())
        write(self.output / "runtime.json", self.record)
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--database-container", default="pr13-stages-20261008-s1-pg")
    parser.add_argument("--scenario", choices=("single", "ten", "50", "100", "soak"), required=True)
    parser.add_argument('--functional-cleared-route',action='store_true',help='Separate LIVE functional control: clear then legally extract; never original capacity evidence')
    args = parser.parse_args()
    if args.functional_cleared_route and args.scenario not in ('single','ten'):parser.error('Cleared route control is only a functional single/ten smoke profile')
    profiles = json.loads((ROOT / "docs/plans/PR13_LOCAL_PROFILES_20261008.json").read_text(encoding="utf8"))
    spec = profiles["profiles"]["LIVE" if args.scenario in {"single", "ten"} else "CAPACITY"]
    count = 1 if args.scenario == "single" else 10 if args.scenario == "ten" else 50 if args.scenario == "soak" else int(args.scenario)
    maximum = spec["single_account_limit_seconds"] if args.scenario == "single" else spec["ten_account_limit_seconds"] if args.scenario == "ten" else 2100 if args.scenario == "soak" else spec["deadline_seconds"]
    output = args.output.resolve()
    profile_hash = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with LocalRuntime(output, args.database_container) as runtime:
        command = [args.python, str(ROOT / "tools/gameplay_load_test.py"), "--godot", args.godot,
                   "--server-url", runtime.url, "--output", str(output / "load"), "--max-seconds", str(maximum),
                   "--distinct-local-client-ips", "--hero-class", "mixed", "--strategy", "baseline_all_hand"]
        if args.scenario in {"single", "ten"}:
            command += ["--smoke", "--smoke-clients", str(count), "--smoke-cycles", "3", "--load-profile", "cleared-extraction" if args.functional_cleared_route else "cyclic-gameplay",
                        "--cycle-limit-seconds", "600"]
        else:
            command += ["--run", "--max-groups", "1", "--group-size", str(count), "--target-online", str(count),
                        "--target-active", str(count), "--hold-seconds", str(spec["soak_seconds"] if args.scenario == "soak" else spec["hold_seconds"]),
                        "--local-resource-sampling", "--launch-interval-seconds", "1", "--load-profile", "cyclic-gameplay"]
        record = {"scenario": args.scenario, "command": command, "profile_hash": profile_hash,
                  "source_sha": runtime.record["source_sha"], "maximum_seconds": maximum, "started_at": time.time(),
                  "cycle_limit_seconds": 600 if args.scenario in {"single", "ten"} else 240,
                  "class_scope": "Three classes round-robin; actual distribution comes from client reports", "accepted": False}
        record['functional_route_variant']='clear-then-extract-visible-outer-ring-v1' if args.functional_cleared_route else None
        record['original_capacity_evidence_eligible']=not args.functional_cleared_route
        if args.functional_cleared_route:
            record['frozen_live_budget_hash']=profile_hash
            record['profile_hash']=hashlib.sha256(json.dumps({'frozen_live_budget_hash':profile_hash,'variant':record['functional_route_variant'],'load_profile':'cleared-extraction','requested_cycles':3},sort_keys=True).encode()).hexdigest()
        write(output / "command.json", record)
        with (output / "load.private.log").open("w", encoding="utf8") as log:
            child = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                child.wait(timeout=maximum + 120)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                for stop in (output / "load").glob("*/STOP"):
                    stop.touch()
                for directory in (output / "load").glob("*"):
                    if directory.is_dir(): (directory / "STOP").touch()
                try: child.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    if os.name == "nt": run(["taskkill", "/PID", str(child.pid), "/T", "/F"])
                    else: child.kill()
                    child.wait(timeout=10)
                record["timeout"] = isinstance(error, subprocess.TimeoutExpired)
                record["operator_interrupted"] = isinstance(error, KeyboardInterrupt)
            record.update(exit_code=child.returncode, ended_at=time.time())
            write(output / "command.json", record)
        try:
            state = runtime.sql("BEGIN READ ONLY; SET LOCAL statement_timeout='20s'; SELECT json_build_object('pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),'active_match_players',(SELECT count(*) FROM match_players WHERE state='Active'),'settlements',(SELECT count(*) FROM match_settlements),'ledger_rows',(SELECT count(*) FROM economy_ledger)); ROLLBACK;")
            values = [line for line in state.splitlines() if line.strip().startswith("{")]
            if len(values) != 1: raise ValueError("No unique database postcondition result")
            write(output / "database-postconditions.json", {"actual": json.loads(values[0]), "read_only": True})
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            write(output / "database-postconditions.json", {"actual": None, "missing_reason": type(error).__name__})
    print(json.dumps({"scenario": args.scenario, "exit_code": record["exit_code"], "runtime_cleanup": runtime.record["cleanup"], "output": str(output)}))
    return 0 if record["exit_code"] == 0 and runtime.record["cleanup"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
