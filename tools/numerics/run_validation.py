#!/usr/bin/env python3
"""Run real .NET validation without deploying or mutating production resources.

This gate is deliberately narrower than full product acceptance. The simulator
currently measures legal routes, not combat survival or complete cash flow.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET


class ValidationError(RuntimeError):
    """A command or its evidence did not satisfy the requested gate."""


def validate_trx(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise ValidationError(f"Missing test report: {path}")
    root = ET.parse(path).getroot()
    counter = root.find(".//{*}Counters")
    if counter is None:
        raise ValidationError("TRX has no counters; discovery is not execution.")
    counts = {key: int(counter.get(key, "0")) for key in
              ("total", "executed", "passed", "failed", "error", "timeout", "aborted", "notRunnable", "notExecuted")}
    if any(number < 0 for number in counts.values()):
        raise ValidationError("TRX contains negative counters.")
    if counts["executed"] <= 0 or counts["passed"] <= 0:
        raise ValidationError("Zero executed/passed tests is not a passing suite.")
    if any(counts[key] for key in ("failed", "error", "timeout", "aborted", "notRunnable")):
        raise ValidationError(f"TRX reports unsuccessful tests: {counts}")
    if counts["passed"] != counts["executed"] or counts["executed"] > counts["total"]:
        raise ValidationError(f"TRX counters are inconsistent: {counts}")
    return counts


def validate_simulation(data: dict, samples: int, players: int) -> None:
    if data.get("Samples") != samples or data.get("PlayerCount") != players:
        raise ValidationError("Simulation sample/player counts do not match the command.")
    if data.get("MinimumEliteClearsForThreeMiddleCorners") != 4:
        raise ValidationError("The middle-corner geometry regression changed.")
    if not isinstance(data.get("ConfigVersion"), str) or not data["ConfigVersion"]:
        raise ValidationError("Simulation output has no config version.")
    for key in ("ClearedCells", "MiddleEliteCells", "Gold", "WarriorSoul", "ClassSoul", "Fragments"):
        values = data.get(key, {})
        for field in ("P10", "P50", "P90", "Mean"):
            value = values.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValidationError(f"Invalid simulation statistic: {key}.{field}")
        if not values["P10"] <= values["P50"] <= values["P90"]:
            raise ValidationError(f"Unordered quantiles: {key}")


def terminate_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_step(name: str, command: list[str], cwd: Path, output: Path,
             timeout: int, report: dict) -> Path:
    log = output / f"{name}.log"
    entry = {"name": name, "command": command, "log": log.name, "status": "running"}
    report["steps"].append(entry)
    started = time.monotonic()
    environment = os.environ.copy()
    environment.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
                       ASPNETCORE_ENVIRONMENT="Testing", DOTNET_ENVIRONMENT="Testing")
    # Never implicitly reuse a developer shell's production database endpoint.
    for key in list(environment):
        if key.lower().startswith("connectionstrings__") or key.upper() in {"DATABASE_URL", "REDIS_URL", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"}:
            del environment[key]
    kwargs = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    try:
        with log.open("wb") as handle:
            process = subprocess.Popen(command, cwd=cwd, env=environment,
                                       stdout=handle, stderr=subprocess.STDOUT, **kwargs)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                terminate_tree(process)
                entry.update(status="timeout", exit_code=process.returncode)
                raise ValidationError(f"{name} timed out; see {log}") from exc
        entry.update(exit_code=code, status="passed" if code == 0 else "failed")
        if code != 0:
            raise ValidationError(f"{name} failed with exit code {code}; see {log}")
    except OSError as exc:
        entry.update(status="environment_error", error=str(exc))
        raise ValidationError(f"Cannot execute {name}: {exc}") from exc
    finally:
        entry["seconds"] = round(time.monotonic() - started, 3)
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--client-project", type=Path, help="Optional existing project relative to repo root; compilation only.")
    args = parser.parse_args()
    if not 1 <= args.samples <= 1_000_000 or args.timeout < 1:
        parser.error("samples must be 1..1000000 and timeout must be positive")
    root = args.root.resolve()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="fc-numerics-"))
    if args.output:
        output.mkdir(parents=True, exist_ok=False)  # Refuse stale TRX/output reuse.
    report = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "status": "not_run", "steps": [], "tests": {}, "simulations": [],
              "scope": "build + Domain/Server tests + legal-route simulator; not full product acceptance",
              "client_scope": "not_requested"}
    try:
        server = root / "server"
        solution = server / "FantasyCard.Server.slnx"
        if not solution.is_file():
            raise ValidationError(f"Solution not found: {solution}")
        if shutil.which("dotnet") is None:
            raise ValidationError("dotnet is unavailable; no C# test has been run.")
        if shutil.which("git"):
            for label, command in (("source_sha", ["git", "rev-parse", "HEAD"]),
                                   ("worktree", ["git", "status", "--porcelain"])):
                result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
                report[label] = (result.stdout.strip() if label == "source_sha" else bool(result.stdout.strip())) if result.returncode == 0 else "unknown"
        report["sdk_lock"] = json.loads((server / "global.json").read_text(encoding="utf-8-sig"))
        run_step("sdk", ["dotnet", "--info"], server, output, args.timeout, report)
        run_step("restore", ["dotnet", "restore", str(solution)], server, output, args.timeout, report)
        run_step("build", ["dotnet", "build", str(solution), "-c", "Release", "--no-restore"], server, output, args.timeout, report)
        for suite in ("Domain", "Server"):
            name = f"FantasyCard.{suite}.Tests"
            project = server / "tests" / name / f"{name}.csproj"
            result_dir = output / name
            result_dir.mkdir()
            run_step(name, ["dotnet", "test", str(project), "-c", "Release", "--no-build", "--no-restore",
                           "--logger", "trx;LogFileName=results.trx", "--results-directory", str(result_dir)],
                     server, output, args.timeout, report)
            report["tests"][suite] = validate_trx(result_dir / "results.trx")
        for players in (1, 2, 4):
            log = run_step(f"route-{players}", ["dotnet", "run", "--project",
                str(server / "tools/FantasyCard.Numerics/FantasyCard.Numerics.csproj"),
                "-c", "Release", "--no-build", "--no-restore", "--", "--samples", str(args.samples),
                "--players", str(players), "--seed-start", "0"], server, output, args.timeout, report)
            data = json.loads(log.read_text(encoding="utf-8-sig"))
            validate_simulation(data, args.samples, players)
            report["simulations"].append(data)
        if args.client_project:
            project = (root / args.client_project).resolve()
            project.relative_to(root)
            if project.suffix != ".csproj" or not project.is_file():
                raise ValidationError("client-project must name an existing .csproj within the repository")
            run_step("client-build", ["dotnet", "build", str(project), "-c", "Release"], server, output, args.timeout, report)
            report["client_scope"] = "compiled; interactive/runtime client acceptance still required"
        report["status"] = "passed_for_declared_scope"
        return 0
    except (ValidationError, ValueError, OSError, ET.ParseError) as exc:
        report.update(status="failed_or_blocked", error=str(exc))
        return 1
    finally:
        report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        (output / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(output / "validation.json")}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
