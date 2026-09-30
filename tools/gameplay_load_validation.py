"""Pure gameplay-load accounting. No network calls and no server-side writes."""
from __future__ import annotations

import hashlib
import math
import platform
import statistics
import subprocess
from collections import Counter
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


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def aggregate_window(statuses: list[dict]) -> dict:
    """Aggregate already-deduplicated samples, retaining errors in each denominator.

    No implicit compatibility-404 exclusions. A received 404 remains an error.
    'steady' excludes auth/bootstrap/explicit initial labels, not all cold traffic.
    """
    if not isinstance(statuses, list):
        statuses = [None]
    http, steady, realtime, rtt, attempts = [], [], [], [], []
    phase_rows: dict[str, list[dict]] = {}
    invalid = invalid_schema = 0
    for status in statuses:
        if not isinstance(status, dict):
            invalid_schema += 1
            continue
        for field, rows in (("operations", status.get("operations", [])),
                            ("telemetry", status.get("telemetry", []))):
            if not isinstance(rows, list):
                invalid_schema += 1
                continue
            for row in rows:
                if not isinstance(row, dict):
                    invalid_schema += 1
                    continue
                kind = "http" if field == "operations" else row.get("type")
                if kind not in {"http", "http_attempt", "realtime", "rtt"} or (field == "telemetry" and kind == "http"):
                    continue
                duration = row.get("duration_ms")
                if not _number(duration) or duration < 0:
                    invalid += 1
                status_code = row.get("status")
                if kind in {"http", "http_attempt"} and status_code is not None and (not isinstance(status_code, int)
                        or isinstance(status_code, bool) or status_code < 0 or status_code > 599):
                    invalid_schema += 1
                if kind == "http":
                    http.append(row)
                    if _steady(row):
                        steady.append(row)
                    phase = row.get("phase")
                    if not isinstance(phase, str) or phase not in {"login", "initial", "matchmaking", "playing", "settlement", "cleanup"}:
                        phase = "unknown/legacy"
                    phase_rows.setdefault(phase, []).append(row)
                elif kind == "http_attempt":
                    attempts.append(row)
                elif kind == "realtime":
                    realtime.append(row)
                else:
                    rtt.append(row)
    def failed(row: dict) -> bool:
        code = row.get("status")
        return row.get("ok") is not True or not isinstance(code, int) or isinstance(code, bool) or not 200 <= code < 300
    def latency(rows: list[dict]) -> dict:
        return summarize([row["duration_ms"] for row in rows if _number(row.get("duration_ms")) and row["duration_ms"] >= 0])
    # A client-initiated cancellation is recorded, but is not an HTTP service
    # error or a completed request in the error-rate denominator.
    completed_http = [row for row in http if row.get("result") != "cancelled"]
    completed_steady = [row for row in steady if row.get("result") != "cancelled"]
    errors = sum(failed(row) for row in completed_http)
    steady_errors = sum(failed(row) for row in completed_steady)
    return {
        "http": latency(completed_http),
        "steady_http": latency(completed_steady),
        "cancelled_http": latency([row for row in http if row.get("result") == "cancelled"]),
        "realtime": latency(realtime),
        "rtt": latency(rtt),
        "phase_http": {phase: latency([row for row in rows if row.get("result") != "cancelled"])
                       for phase, rows in phase_rows.items()},
        "error_count": errors, "sample_count": len(completed_http),
        "logical_request_count": len(http),
        "cancelled_count": len(http) - len(completed_http),
        "all_attempt_count": len(attempts) if attempts else None,
        "attempt_coverage": "measured" if attempts else "unavailable",
        "attempt_result_counts": dict(Counter(str(row.get("result", "unknown")) for row in attempts)),
        "valid_attempt_latency_count": latency(attempts)["count"],
        "valid_latency_count": latency(completed_http)["count"],
        "latency_sample_quality": {
            "http": "unavailable" if not completed_http else "insufficient" if latency(completed_http)["count"]<20 else "sufficient_for_diagnostic_rule",
            "realtime": "unavailable" if not realtime else "insufficient" if latency(realtime)["count"]<10 else "sufficient_for_diagnostic_rule"},
        "error_rate": errors / len(completed_http) if completed_http else 0.0,
        "steady_error_count": steady_errors, "steady_sample_count": len(completed_steady),
        "steady_error_rate": steady_errors / len(completed_steady) if completed_steady else 0.0,
        "invalid_metric_count": invalid + invalid_schema,
        "invalid_duration_count": invalid, "invalid_schema_count": invalid_schema,
        "steady_definition": "exclude auth/bootstrap paths and login/bootstrap/initial labels",
    }


def workload_snapshot(processes: list[dict], statuses: list[dict], now_ms: int,
                      stale_ms: int = 30000, stalled_ms: int = 90000,
                      now_monotonic_ms: float | None = None) -> dict:
    """Only fresh reports from an owned, running PID count as current activity."""
    if not isinstance(processes, list):
        processes = [None]
    if not isinstance(statuses, list):
        statuses = [None]
    if not _number(now_ms) or not _number(stale_ms) or not _number(stalled_ms) or stale_ms < 0 or stalled_ms < 0:
        return {"alive_processes": 0, "fresh_status_clients": 0, "online": 0,
                "in_room": 0, "room_state_clients": 0, "active_in_room": 0,
                "server_confirmed_in_room": None, "invalid_schema_count": 1,
                "failed_processes": [], "stale_clients": [], "stalled_clients": [],
                "missing_clients": [], "invalid_clients": [], "workload_failure": True}
    by_id = {}
    invalid_schema = 0
    for status in statuses:
        if not isinstance(status, dict):
            invalid_schema += 1
            continue
        cid = status.get("client_id")
        timestamp = status.get("now_unix_ms")
        if not isinstance(cid, str) or not cid or not _number(timestamp) or timestamp < 0:
            invalid_schema += 1
            continue
        if cid and timestamp >= by_id.get(cid, {}).get("now_unix_ms", 0):
            by_id[cid] = status
    live, fresh, failed, stale, stalled, missing, invalid = [], [], [], [], [], [], []
    for entry in processes:
        if (not isinstance(entry, dict) or not isinstance(entry.get("client_id"), str)
                or not entry["client_id"] or not _number(entry.get("started_at_ms"))
                or not hasattr(entry.get("process"), "poll") or not hasattr(entry.get("process"), "pid")):
            invalid_schema += 1
            continue
        process, cid = entry["process"], entry["client_id"]
        code = process.poll()
        if code is not None:
            if code != 0:
                failed.append(cid)
            continue
        live.append(cid)
        status = by_id.get(cid)
        if status is None:
            elapsed = (now_monotonic_ms-entry["started_at_monotonic_ms"]
                       if _number(now_monotonic_ms) and _number(entry.get("started_at_monotonic_ms"))
                       else now_ms-entry["started_at_ms"])
            if elapsed > stale_ms:
                missing.append(cid)
            continue
        timestamp = status.get("now_unix_ms", 0)
        monotonic_age = (now_monotonic_ms-status["_received_at_monotonic_ms"]
                         if _number(now_monotonic_ms) and _number(status.get("_received_at_monotonic_ms")) else None)
        if (not isinstance(status.get("pid"), int) or isinstance(status.get("pid"), bool)
                or status.get("pid") != process.pid or (timestamp > now_ms if monotonic_age is None else monotonic_age < 0)
                or any(status.get(key) != entry.get(key) for key in ("run_id", "process_epoch") if entry.get(key) is not None)):
            invalid.append(cid)
            continue
        age = status.get("last_progress_age_ms", 0)
        if (not _number(age) or age < 0 or
                not isinstance(status.get("online", False), bool) or
                not isinstance(status.get("room", False), bool)):
            invalid_schema += 1
            invalid.append(cid)
            continue
        if (now_ms-timestamp if monotonic_age is None else monotonic_age) > stale_ms:
            stale.append(cid)
            continue
        if age > stalled_ms:
            stalled.append(cid)
        fresh.append(status)
    return {
        "alive_processes": len(live), "fresh_status_clients": len(fresh),
        "online": sum(status.get("online") is True for status in fresh),
        "in_room": sum(status.get("online") is True and status.get("room") is True for status in fresh),
        "room_state_clients": sum(status.get("room") is True for status in fresh),
        "active_in_room": sum(status.get("online") is True and status.get("room") is True for status in fresh),
        "server_confirmed_in_room": None,
        "invalid_schema_count": invalid_schema,
        "failed_processes": failed, "stale_clients": stale,
        "stalled_clients": stalled, "missing_clients": missing, "invalid_clients": invalid,
        "workload_failure": bool(failed or stale or stalled or missing or invalid or invalid_schema),
    }


def owned_statuses(processes: list[dict], statuses: list[dict]) -> tuple[list[dict], int]:
    """Keep reports from this launch only, including valid exited-process history."""
    entries = {entry["client_id"]: entry for entry in processes}
    owned: dict[str, dict] = {}
    invalid = 0
    for status in statuses:
        if not isinstance(status, dict):
            invalid += 1
            continue
        cid = status.get("client_id")
        if not isinstance(cid, str):
            invalid += 1
            continue
        entry = entries.get(cid)
        if (entry is None or not isinstance(status.get("pid"),int) or isinstance(status.get("pid"),bool)
                or status.get("pid",0)<1 or status.get("pid") != entry["process"].pid
                or status.get("run_id") != entry.get("run_id")
                or status.get("process_epoch") != entry.get("process_epoch")):
            invalid += 1
            continue
        previous = owned.get(entry["client_id"])
        if previous is not None:
            invalid += 1
            if not _number(status.get("now_unix_ms")) or status["now_unix_ms"] <= previous.get("now_unix_ms", 0):
                continue
        owned[entry["client_id"]] = status
    return list(owned.values()), invalid


def new_events(statuses: list[dict], seen: dict[tuple[str, str], int]) -> tuple[list[dict], int]:
    """Consume each owned event once; gaps are evidence loss, never success."""
    window = []
    lost = 0
    for status in statuses:
        key = (status["client_id"], status["process_epoch"])
        prior = seen.get(key, 0)
        raw = status.get("telemetry", [])
        if not isinstance(raw, list):
            lost += 1
            continue
        fresh = []
        for row in raw:
            seq = row.get("event_seq") if isinstance(row, dict) else None
            if (not isinstance(seq, int) or isinstance(seq, bool) or seq < 1
                    or row.get("run_id") != status.get("run_id")
                    or row.get("client_id") != status["client_id"]
                    or row.get("process_epoch") != status["process_epoch"]):
                lost += 1
                continue
            if seq > prior:
                fresh.append(row)
        fresh.sort(key=lambda row: row["event_seq"])
        expected = prior + 1
        accepted = []
        for row in fresh:
            seq = row["event_seq"]
            if seq < expected:
                lost += 1
                continue
            if seq > expected:
                lost += seq - expected
            expected = seq + 1
            accepted.append(row)
        maximum = status.get("event_seq_max")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
            lost += 1
        elif maximum >= expected:
            lost += maximum - expected + 1
        if accepted:
            seen[key] = accepted[-1]["event_seq"]
        copy = dict(status)
        copy["telemetry"] = accepted
        http_events = {row["event_seq"]: row for row in accepted if row.get("type") == "http"}
        operations = status.get("operations", [])
        if not isinstance(operations, list):
            operations = []
            lost += 1
        confirmed_operations = {}
        for row in operations:
            seq = row.get('event_seq') if isinstance(row, dict) else None
            if not isinstance(seq, int) or isinstance(seq, bool):
                lost += 1
                continue
            if seq not in http_events:
                continue  # The bounded operation ring also retains older rows.
            if row != http_events[seq] or seq in confirmed_operations:
                lost += 1
                continue
            confirmed_operations[seq] = row
        lost += len(set(http_events) - set(confirmed_operations))
        copy["operations"] = list(confirmed_operations.values())
        window.append(copy)
    return window, lost


def classify_stop(reason: str, *, smoke_verified: bool = False, load_verified: bool = False,
                  workload_failed: bool = False) -> dict:
    """An orderly stop is not synonymous with passing an acceptance test."""
    if workload_failed or reason.startswith(("coordinator_error:", "invalid_evidence:")) or "workload_or_generator_failure" in reason or "monitoring_unavailable" in reason or "invalid_telemetry" in reason or "generator_memory_low" in reason:
        classification, code = "invalid_workload_or_evidence", 3
    elif reason == "smoke_passed" and smoke_verified:
        classification, code = "smoke_passed", 0
    elif reason == "duration_limit" and load_verified:
        classification, code = "load_window_completed", 0
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
