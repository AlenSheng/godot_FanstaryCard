"""Ramp isolated Godot clients against the configured cloud server.

The runner owns every spawned process and a stop-file based graceful shutdown.
It records synthetic health latency and client-side REST/WebSocket telemetry;
server host CPU/DB metrics are intentionally reported as unavailable unless the
cloud deployment exports them separately.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
GODOT_MANIFEST = ROOT / "tools/engine-local/godot-4.7.2-stable-windows-x86_64.json"
CLIENT_DLL = ROOT / "tools/cloud_load_client/bin/Release/net10.0/CloudLoadClient.dll"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((p / 100.0) * len(ordered)) - 1))
    return round(float(ordered[index]), 2)


def summarize(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min_ms": round(min(values), 2),
        "mean_ms": round(statistics.fmean(values), 2),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "p99_ms": percentile(values, 99),
        "max_ms": round(max(values), 2),
    }


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def health_probe(url: str, timeout_seconds: float = 15) -> dict:
    probe_url = url.rstrip("/") + "/health/ready"
    started = time.perf_counter()
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Health probe timeout must be finite and positive")
    # Use the Windows curl trust store when available; the bundled Python
    # runtime may not share the host certificate store used by Godot/curl.
    try:
        result = subprocess.run(
            ["curl.exe", "-sS", "-o", "NUL", "-w", "%{http_code} %{time_total}", "--connect-timeout", str(min(10,timeout_seconds)), "--max-time", str(timeout_seconds), probe_url],
            capture_output=True,
            text=True,
            timeout=timeout_seconds+.5,
            check=False,
        )
        fields = result.stdout.strip().split()
        if len(fields) >= 2 and fields[0].isdigit():
            return {"at_unix_ms": int(time.time() * 1000), "duration_ms": round(float(fields[1]) * 1000, 2), "status": int(fields[0]), "ok": int(fields[0]) == 200}
        # A completed or timed-out probe is one observation. Retrying through
        # another transport would exceed its budget and conceal that failure.
        return {"at_unix_ms":int(time.time()*1000),"duration_ms":round((time.perf_counter()-started)*1000,2),"status":0,"ok":False,"error":"invalid_probe_output"}
    except FileNotFoundError:
        pass
    except (subprocess.SubprocessError, ValueError) as error:
        return {"at_unix_ms":int(time.time()*1000),"duration_ms":round((time.perf_counter()-started)*1000,2),"status":0,"ok":False,"error":type(error).__name__}
    remaining = max(.001,timeout_seconds-(time.perf_counter()-started))
    request = urllib.request.Request(probe_url, headers={"User-Agent": "FantasyCard-CloudLoad/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=remaining) as response:
            response.read()
            return {"at_unix_ms": int(time.time() * 1000), "duration_ms": round((time.perf_counter() - started) * 1000, 2), "status": response.status, "ok": response.status == 200}
    except urllib.error.HTTPError as error:
        return {"at_unix_ms": int(time.time() * 1000), "duration_ms": round((time.perf_counter() - started) * 1000, 2), "status": error.code, "ok": False}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {"at_unix_ms": int(time.time() * 1000), "duration_ms": round((time.perf_counter() - started) * 1000, 2), "status": 0, "ok": False, "error": str(error)[:200]}


def load_client_status(report_dir: Path) -> list[dict]:
    statuses: list[dict] = []
    for path in report_dir.glob("*.status.json"):
        value = read_json(path)
        if value:
            statuses.append(value)
    return statuses


def aggregate_recent(statuses: list[dict], window_ms: int, *, now_ms: int | None = None) -> dict:
    # Optional frozen observation time enables exact historical replay while
    # preserving the default legacy filters and error denominator.
    cutoff = (int(time.time() * 1000) if now_ms is None else now_ms) - window_ms
    http: list[dict] = []
    steady_http: list[dict] = []
    realtime: list[dict] = []
    rtt: list[float] = []
    errors = 0
    total = 0
    for status in statuses:
        for operation in status.get("operations", []):
            if int(operation.get("at_unix_ms", 0)) >= cutoff:
                expected_compatibility_404 = int(operation.get("status", 0)) == 404 and "/context" in str(operation.get("path", ""))
                if expected_compatibility_404:
                    continue
                total += 1
                if not bool(operation.get("ok", False)) or int(operation.get("status", 0)) >= 500:
                    errors += 1
                http.append(operation)
                label = str(operation.get("label", ""))
                if label not in {"login", "bootstrap"} and not label.startswith("initial:"):
                    steady_http.append(operation)
        for sample in status.get("telemetry", []):
            if int(sample.get("at_unix_ms", 0)) < cutoff:
                continue
            if sample.get("type") == "realtime":
                realtime.append(sample)
            elif sample.get("type") == "rtt":
                rtt.append(float(sample.get("duration_ms", 0)))
    return {
        "http": summarize([float(x.get("duration_ms", 0)) for x in http]),
        "steady_http": summarize([float(x.get("duration_ms", 0)) for x in steady_http]),
        "realtime": summarize([float(x.get("duration_ms", 0)) for x in realtime]),
        "rtt": summarize(rtt),
        "error_count": errors,
        "sample_count": total,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "steady_sample_count": len(steady_http),
        "steady_error_rate": round(errors / len(steady_http), 4) if steady_http else 0.0,
    }


def start_client(args: argparse.Namespace, report_dir: Path, stop_file: Path, group: int, index: int, processes: list[dict]) -> None:
    client_id = f"g{group:02d}c{index:02d}_{uuid.uuid4().hex[:8]}"
    report_path = report_dir / f"{client_id}.json"
    log_path = report_dir / f"{client_id}.log"
    godot = args.godot
    env = dict(os.environ)
    env.update({
        "FANTASYCARD_SERVER_URL": args.server_url,
        "FANTASYCARD_LOAD_CLIENT_ID": client_id,
        "FANTASYCARD_LOAD_GROUP": str(group),
        "FANTASYCARD_LOAD_REPORT": str(report_path),
        "FANTASYCARD_LOAD_STOP_FILE": str(stop_file),
    })
    log = log_path.open("w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        ["dotnet", str(CLIENT_DLL)],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    processes.append({"process": process, "log": log, "client_id": client_id, "group": group, "report": report_path})


def stop_all(processes: list[dict], stop_file: Path, grace_seconds: float = 35) -> list[int]:
    stop_file.write_text("stop", encoding="utf-8")
    deadline = time.monotonic() + max(0, grace_seconds)
    while time.monotonic() < deadline:
        alive = [entry for entry in processes if entry["process"].poll() is None]
        if not alive:
            return []
        time.sleep(1)
    forced: list[int] = []
    for entry in processes:
        process = entry["process"]
        if process.poll() is None:
            forced.append(process.pid)
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                process.kill()
    for entry in processes:
        entry["process"].wait(timeout=10)
    return forced


def write_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = path.with_suffix(".md")
    markdown.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict) -> str:
    stop = report.get("stop_reason", "unknown")
    groups = report.get("groups_started", 0)
    clients = report.get("clients_started", 0)
    final = report.get("final_window", {})
    lines = [
        "# FantasyCard 云端单机压测报告",
        "",
        f"- 目标：`{report.get('server_url')}`",
        f"- 开始时间：`{report.get('started_at')}`",
        f"- 结束时间：`{report.get('ended_at')}`",
        f"- 启动分组：{groups} 组；客户端：{clients} 个",
        f"- 停止原因：{stop}",
        "",
        "## 性能结论",
        "",
        f"最终 60 秒 HTTP（含登录/Bootstrap）：{json.dumps(final.get('http', {}), ensure_ascii=False)}",
        f"最终 60 秒稳定态 HTTP（排除登录/Bootstrap/首屏读取）：{json.dumps(final.get('steady_http', {}), ensure_ascii=False)}",
        f"最终 60 秒实时命令：{json.dumps(final.get('realtime', {}), ensure_ascii=False)}",
        f"最终 60 秒 WebSocket RTT：{json.dumps(final.get('rtt', {}), ensure_ascii=False)}",
        f"最终 60 秒错误率：{final.get('error_rate', 0) * 100:.2f}%",
        "",
        "## 口径与限制",
        "",
        "本报告是从外部云端客户端观测到的单机承压结果；服务器 CPU、内存、GC、PostgreSQL 和 RoomActor 队列需要云端 OTLP/主机监控才能给出资源瓶颈归因。",
        "项目当前没有拍卖竞价接口，本次市场场景覆盖上架、购买和下架。",
        "",
        "## 分组摘要",
        "",
    ]
    for row in report.get("group_summaries", []):
        lines.append(f"- 第 {row.get('group')} 组：{row.get('clients')} 客户端；稳定态 HTTP p95 {row.get('steady_http_p95_ms')} ms；错误率 {row.get('error_rate', 0) * 100:.2f}%；健康检查 p95 {row.get('health_p95_ms')} ms")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="https://www.relicbound.cn")
    parser.add_argument("--groups", type=int, default=10)
    parser.add_argument("--clients-per-group", type=int, default=10)
    parser.add_argument("--interval-seconds", type=int, default=600)
    parser.add_argument("--max-runtime-seconds", type=int, default=6600)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "cloud-load")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--health-p95-stop-ms", type=float, default=5000)
    parser.add_argument("--http-p95-stop-ms", type=float, default=1500)
    parser.add_argument("--realtime-p95-stop-ms", type=float, default=2000)
    args = parser.parse_args()
    if args.groups <= 0 or args.clients_per_group <= 0:
        raise SystemExit("groups and clients-per-group must be positive")
    if args.godot is None:
        manifest = json.loads(GODOT_MANIFEST.read_text(encoding="utf-8"))
        args.godot = manifest["executable"]
    args.output = args.output if args.output.is_absolute() else ROOT / args.output
    args.output = args.output.resolve()
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    report_dir = args.output / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    stop_file = report_dir / "STOP"
    health: list[dict] = []
    processes: list[dict] = []
    group_summaries: list[dict] = []
    started_at = time.time()
    next_group_at = started_at
    next_health_at = started_at
    next_summary_at = started_at + max(30, args.interval_seconds)
    consecutive_degraded = 0
    stop_reason = "max_groups_reached"
    groups_started = 0
    try:
        while time.time() - started_at < args.max_runtime_seconds:
            now = time.time()
            if groups_started < args.groups and now >= next_group_at:
                groups_started += 1
                for index in range(1, args.clients_per_group + 1):
                    start_client(args, report_dir, stop_file, groups_started, index, processes)
                next_group_at = started_at + groups_started * args.interval_seconds
                print(f"STARTED group={groups_started} clients={args.clients_per_group} total={groups_started * args.clients_per_group}", flush=True)
            if now >= next_health_at:
                sample = health_probe(args.server_url)
                health.append(sample)
                next_health_at = now + 10
                statuses = load_client_status(report_dir)
                window = aggregate_recent(statuses, 60000)
                health_recent = [x for x in health if x["at_unix_ms"] >= int(time.time() * 1000) - 60000]
                health_p95 = percentile([float(x["duration_ms"]) for x in health_recent if x.get("ok")], 95)
                degraded = (
                    len(health_recent) >= 3 and any(not x.get("ok") for x in health_recent[-3:])
                ) or (
                    health_p95 is not None and health_p95 > args.health_p95_stop_ms
                ) or (
                    window["sample_count"] >= 20 and window["error_rate"] >= 0.10
                ) or (
                    window["steady_http"].get("p95_ms") is not None and window["steady_http"]["p95_ms"] > args.http_p95_stop_ms and window.get("steady_sample_count", 0) >= 20
                ) or (
                    window["realtime"].get("p95_ms") is not None and window["realtime"]["p95_ms"] > args.realtime_p95_stop_ms and window["realtime"].get("count", 0) >= 10
                )
                consecutive_degraded = consecutive_degraded + 1 if degraded else 0
                print(f"SAMPLE groups={groups_started} clients={len(processes)} health_p95={health_p95} steady_http_p95={window['steady_http'].get('p95_ms')} realtime_p95={window['realtime'].get('p95_ms')} error_rate={window['error_rate']:.3f}", flush=True)
                if consecutive_degraded >= 3:
                    stop_reason = "performance_redline_reached"
                    break
            if now >= next_summary_at:
                statuses = load_client_status(report_dir)
                window = aggregate_recent(statuses, max(60000, int(args.interval_seconds * 1000)))
                health_window = [x for x in health if x["at_unix_ms"] >= int(time.time() * 1000) - max(60000, args.interval_seconds * 1000)]
                group_summaries.append({"group": groups_started, "clients": len(processes), "steady_http_p95_ms": window["steady_http"].get("p95_ms"), "error_rate": window["error_rate"], "health_p95_ms": percentile([float(x["duration_ms"]) for x in health_window if x.get("ok")], 95)})
                next_summary_at = now + max(30, args.interval_seconds)
            if groups_started >= args.groups and all(entry["process"].poll() is not None for entry in processes):
                stop_reason = "all_clients_finished"
                break
            time.sleep(1)
        else:
            stop_reason = "max_runtime_reached"
    except KeyboardInterrupt:
        stop_reason = "operator_interrupted"
    finally:
        stop_all(processes, stop_file)
        for entry in processes:
            entry["log"].close()
    statuses = load_client_status(report_dir)
    final_window = aggregate_recent(statuses, 60000)
    report = {
        "run_id": run_id,
        "server_url": args.server_url,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started_at)),
        "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "groups_requested": args.groups,
        "groups_started": groups_started,
        "clients_per_group": args.clients_per_group,
        "clients_started": len(processes),
        "interval_seconds": args.interval_seconds,
        "stop_reason": stop_reason,
        "thresholds": {"health_p95_ms": args.health_p95_stop_ms, "http_p95_ms": args.http_p95_stop_ms, "realtime_p95_ms": args.realtime_p95_stop_ms, "error_rate": 0.10},
        "health_samples": health,
        "final_window": final_window,
        "group_summaries": group_summaries,
        "client_reports": [str(entry["report"].relative_to(ROOT)) for entry in processes],
        "server_resource_metrics": "unavailable_from_external_client; provide cloud OTLP/host metrics for CPU, memory, GC, PostgreSQL and RoomActor queue attribution",
        "market_scope": "listing_purchase_cancel; auction_bid_endpoint_not_present_in_project",
    }
    report_path = report_dir / "load-test-report.json"
    write_report(report_path, report)
    print(f"REPORT {report_path}", flush=True)
    return 0 if stop_reason in {"performance_redline_reached", "max_groups_reached", "all_clients_finished", "max_runtime_reached", "operator_interrupted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
