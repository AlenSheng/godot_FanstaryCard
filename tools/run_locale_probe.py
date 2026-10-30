"""Run the offline locale/card regressions with the UI suite's memory reserve."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from validate_ui_hidden import MemoryStatus, RESERVE, START_BUDGET, write_json

ROOT = Path(__file__).resolve().parents[1]


def available_memory():
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    return status.available


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = list((ROOT / "client").rglob("*.gd")) + list((ROOT / "client/data").rglob("*.json"))
    sources += [ROOT / "client/project.godot", Path(__file__).resolve()]
    sources = sorted(p for p in set(sources) if ".godot" not in p.parts)
    pin = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    write_json(output / "source-pin.original.json", pin)
    child = None
    try:
        start = time.monotonic()
        with (output / "admission.original.jsonl").open("x", encoding="utf-8") as log:
            while True:
                samples = []
                for _ in range(3):
                    samples.append(available_memory())
                    time.sleep(1)
                log.write(json.dumps({"samples": samples, "reserve_bytes": RESERVE,
                                      "startup_budget_bytes": START_BUDGET}) + "\n")
                log.flush()
                if min(samples) >= RESERVE + START_BUDGET:
                    break
                if time.monotonic() - start >= args.wait_seconds:
                    raise RuntimeError("Resource admission unavailable; no process started")
                time.sleep(min(10, max(0, args.wait_seconds - (time.monotonic() - start))))
        env = os.environ.copy()
        env.update({"APPDATA": str(output / "user-profile"), "LOCALAPPDATA": str(output / "local-profile"),
                    "FANTASYCARD_SERVER_URL": "http://127.0.0.1:9", "FANTASYCARD_REVIEW_LOCALES": args.locale,
                    "FANTASYCARD_LOCALE_PROBE_REPORT": str(output / "report.json"),
                    "NATIVE_REGRESSION_REPORT": str(output / "report.json")})
        command = [str(args.godot.resolve()), "--headless", "--path", str(ROOT / "client"),
                   "--audio-driver", "Dummy"]
        command += (["--script", "res://tests/localization_pack_probe.gd"] if args.suite == "catalog"
                    else ["--editor", "--import", "--quit"] if args.suite == "import"
                    else ["res://tests/run_native_regressions.tscn"])
        with (output / "stdout.original.log").open("xb") as stdout, (output / "stderr.original.log").open("xb") as stderr:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr,
                                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            write_json(output / "started.original.json", {"pid": child.pid, "command": command})
            start = time.monotonic()
            while child.poll() is None:
                if available_memory() < RESERVE or time.monotonic() - start > 120:
                    raise RuntimeError("Owned locale probe reached resource/time guard")
                if b"SCRIPT ERROR:" in (output / "stderr.original.log").read_bytes()[-16384:]:
                    child.kill()
                    child.wait(timeout=10)
                    break
                time.sleep(.25)
        report_path = output / "report.json"
        report = json.loads(report_path.read_bytes()) if report_path.exists() else {}
        unchanged = all(hashlib.sha256(p.read_bytes()).hexdigest() == pin[str(p.relative_to(ROOT))] for p in sources)
        diagnostics = (output / "stderr.original.log").read_bytes()
        suite_ok = args.suite == "import" or report.get("ok", False)
        ok = child.returncode == 0 and suite_ok and unchanged and not diagnostics
        write_json(output / "terminal.original.json", {"ok": ok, "native_exit": child.returncode,
                   "source_unchanged": unchanged, "locale": args.locale, "actual_game_matches": 0})
        errors = report.get("errors", []) if args.suite in ["catalog", "import"] else [row for row in report.get("suites", []) if not row.get("result", {}).get("ok", False)]
        print(json.dumps({"ok": ok, "locale": args.locale, "suite": args.suite, "errors": errors}, ensure_ascii=True))
        return 0 if ok else 1
    except Exception as error:
        write_json(output / "failure.original.json", {"error": str(error), "type": type(error).__name__})
        return 1
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--locale", required=True)
    parser.add_argument("--suite", choices=["catalog", "native", "import"], default="catalog")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=0)
    options = parser.parse_args()
    if options.wait_seconds < 0 or not options.godot.is_file():
        parser.error("Use an existing Godot executable and nonnegative admission wait")
    raise SystemExit(run(options))
