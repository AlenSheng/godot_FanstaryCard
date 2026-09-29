"""Pure gameplay-load accounting. No network calls and no server-side writes."""
from __future__ import annotations

import hashlib
import math
import platform
import statistics
import subprocess
from pathlib import Path


def summarize(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    result = {"count": len(values), "min_ms": min(values),
              "mean_ms": statistics.fmean(values), "max_ms": max(values)}
    for name, fraction in (("p50_ms", .50), ("p95_ms", .95), ("p99_ms", .99)):
        result[name] = ordered[max(0, math.ceil(len(values) * fraction) - 1)]
    return {key: value if key == "count" else round(value, 2) for key, value in result.items()}


def _steady(operation: dict) -> bool:
    # Older clients do not emit lifecycle labels. Do not misclassify their
    # authentication/bootstrap calls as steady-state just because label is absent.
    label = str(operation.get("label", ""))
    path = str(operation.get("path", "")).split("?", 1)[0].rstrip("/")
    return (label not in {"login", "bootstrap"} and not label.startswith("initial:")
            and not path.startswith("/api/v1/auth/") and path != "/api/v1/bootstrap")


def aggregate_window(statuses: list[dict]) -> dict:
    """Aggregate already-deduplicated samples, retaining errors in each denominator.

    No implicit compatibility-404 exclusions. A received 404 remains an error.
    'steady' excludes auth/bootstrap/explicit initial labels, not all cold traffic.
    """
    http, steady, realtime, rtt = [], [], [], []
    invalid = 0
    for status in statuses:
        for field, rows in (("operations", status.get("operations", [])),
                            ("telemetry", status.get("telemetry", []))):
            for row in rows:
                kind = "http" if field == "operations" else row.get("type")
                if kind not in {"http", "realtime", "rtt"} or (field == "telemetry" and kind == "http"):
                    continue
                duration = row.get("duration_ms")
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                    invalid += 1
                    continue
                if kind == "http":
                    http.append(row)
                    if _steady(row):
                        steady.append(row)
                elif kind == "realtime":
                    realtime.append(row)
                else:
                    rtt.append(row)
    def failed(row: dict) -> bool:
        return row.get("ok") is not True or not 200 <= int(row.get("status", 0)) < 300
    errors = sum(failed(row) for row in http)
    steady_errors = sum(failed(row) for row in steady)
    return {
        "http": summarize([row["duration_ms"] for row in http]),
        "steady_http": summarize([row["duration_ms"] for row in steady]),
        "realtime": summarize([row["duration_ms"] for row in realtime]),
        "rtt": summarize([row["duration_ms"] for row in rtt]),
        "error_count": errors, "sample_count": len(http),
        "error_rate": errors / len(http) if http else 0.0,
        "steady_error_count": steady_errors, "steady_sample_count": len(steady),
        "steady_error_rate": steady_errors / len(steady) if steady else 0.0,
        "invalid_metric_count": invalid,
        "steady_definition": "exclude auth/bootstrap paths and login/bootstrap/initial labels",
    }


def workload_snapshot(processes: list[dict], statuses: list[dict], now_ms: int,
                      stale_ms: int = 30000, stalled_ms: int = 90000) -> dict:
    """Only fresh reports from an owned, running PID count as current activity."""
    by_id = {}
    for status in statuses:
        cid = status.get("client_id")
        if cid and status.get("now_unix_ms", 0) >= by_id.get(cid, {}).get("now_unix_ms", 0):
            by_id[cid] = status
    live, fresh, failed, stale, stalled, missing, invalid = [], [], [], [], [], [], []
    for entry in processes:
        process, cid = entry["process"], entry["client_id"]
        code = process.poll()
        if code is not None:
            if code != 0:
                failed.append(cid)
            continue
        live.append(cid)
        status = by_id.get(cid)
        if status is None:
            if now_ms - entry["started_at_ms"] > stale_ms:
                missing.append(cid)
            continue
        timestamp = status.get("now_unix_ms", 0)
        if status.get("pid") != process.pid or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp > now_ms:
            invalid.append(cid)
            continue
        if now_ms - timestamp > stale_ms:
            stale.append(cid)
            continue
        if status.get("last_progress_age_ms", 0) > stalled_ms:
            stalled.append(cid)
        fresh.append(status)
    return {
        "alive_processes": len(live), "fresh_status_clients": len(fresh),
        "online": sum(status.get("online") is True for status in fresh),
        "in_room": sum(status.get("room") is True for status in fresh),
        "failed_processes": failed, "stale_clients": stale,
        "stalled_clients": stalled, "missing_clients": missing, "invalid_clients": invalid,
        "workload_failure": bool(failed or stale or stalled or missing or invalid),
    }


def classify_stop(reason: str, *, smoke_verified: bool = False, workload_failed: bool = False) -> dict:
    """An orderly stop is not synonymous with passing an acceptance test."""
    if workload_failed or reason.startswith("coordinator_error:") or "workload_or_generator_failure" in reason or "monitoring_unavailable" in reason or "invalid_telemetry" in reason:
        classification, code = "invalid_workload_or_evidence", 3
    elif reason == "smoke_passed" and smoke_verified:
        classification, code = "smoke_passed", 0
    elif reason.startswith("redline:"):
        classification, code = "performance_redline", 2
    elif reason.startswith("operator_"):
        classification, code = "operator_stopped", 130
    else:
        classification, code = "incomplete_or_failed", 1
    return {"classification": classification, "passed": code == 0, "exit_code": code}


def provenance(root: Path, paths: tuple[str, ...]) -> dict:
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "git_commit": None, "git_dirty": None, "sha256": {}}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, capture_output=True, text=True, timeout=5, check=True)
        result.update(git_commit=commit.stdout.strip(), git_dirty=bool(dirty.stdout.strip()))
    except (OSError, subprocess.SubprocessError):
        pass
    for path in paths:
        try:
            result["sha256"][path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
        except OSError:
            result["sha256"][path] = None
    return result
