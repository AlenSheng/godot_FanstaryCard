"""Windows-only Godot checks with no windows on the user's active desktop.

Use --scripts-only for headless compilation. Render checks always use a new
inactive desktop; this tool never calls SwitchDesktop or falls back to Default.
Output directories are immutable. Review the PNGs before visual acceptance.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import datetime
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import time
import uuid

GIB = 1024 ** 3
RESERVE = 6 * GIB
START_BUDGET = GIB


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class MemoryStatus(ctypes.Structure):
    _fields_ = [("length", W.DWORD), ("load", W.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in (
            "total", "available", "total_page", "available_page",
            "total_virtual", "available_virtual", "extended")]


class StartupInfo(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR),
                ("title", W.LPWSTR)] + [(name, W.DWORD) for name in (
                    "x", "y", "width", "height", "columns", "rows", "fill", "flags")] + [
        ("show", W.WORD), ("reserved_bytes", W.WORD), ("reserved_data", W.LPVOID),
        ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE),
                ("pid", W.DWORD), ("tid", W.DWORD)]


def run(args):
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
    kernel.CreateMutexW.restype = W.HANDLE
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.ReleaseMutex.argtypes = [W.HANDLE]
    mutex_name = "Local\\FantasyCardUI_" + hashlib.sha256(str(root).lower().encode()).hexdigest()[:24]
    mutex = kernel.CreateMutexW(None, False, mutex_name)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if kernel.WaitForSingleObject(mutex, 0) not in (0, 0x80):
        kernel.CloseHandle(mutex)
        write_json(output / "terminal.original.json", {"state": "AnotherOwnedUIValidationRunning", "native_started": False})
        return 2

    def free_memory():
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return status.available

    def admit(stage):
        start = time.monotonic()
        with (output / (stage + ".admission.original.jsonl")).open("x", encoding="utf-8") as log:
            while True:
                samples = []
                for _ in range(3):
                    samples.append(free_memory())
                    time.sleep(1)
                log.write(json.dumps({"at": datetime.datetime.now().isoformat(), "samples": samples,
                                      "reserve_bytes": RESERVE, "startup_budget_bytes": START_BUDGET}) + "\n")
                log.flush()
                if min(samples) >= RESERVE + START_BUDGET:
                    return
                if time.monotonic() - start >= args.wait_seconds:
                    raise RuntimeError(stage + ": resource admission unavailable; no process started")
                time.sleep(min(10, max(0, args.wait_seconds - (time.monotonic() - start))))

    epoch = uuid.uuid4().hex
    env = os.environ.copy()
    env.update({"APPDATA": str(output / "user-profile"),
                "FANTASYCARD_ART_EVIDENCE": str(output),
                "FANTASYCARD_CODEX_EVIDENCE": str(output),
                "FANTASYCARD_SERVER_URL": "http://127.0.0.1:9",
                "FANTASYCARD_LOAD_RUN_ID": "ui-visual-review-" + epoch,
                "FANTASYCARD_LOAD_CLIENT_ID": "hidden-ui-validator",
                "FANTASYCARD_LOAD_PROCESS_EPOCH": epoch,
                "FANTASYCARD_REVIEW_ISOLATED_DESKTOP": "1",
                "FANTASYCARD_REVIEW_WIDTHS": str(args.width),
                "FANTASYCARD_REVIEW_LOCALES": args.locale,
                "FANTASYCARD_REVIEW_SCREENS": args.screens,
                "FANTASYCARD_REVIEW_CARD_REGRESSION": "1" if args.card_regression else "0"})
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    sources = list((root / "client/ui").glob("*.gd")) + list((root / "client/tests").glob("ui_*"))
    sources += [root / "client/tests" / (args.scene + ".gd"), root / "client/project.godot"]
    sources += list((root / "client/assets/fonts").glob("*.otf*"))
    sources += list((root / "client/assets/fonts").glob("*.ttf*"))
    sources += list((root / "client/data").rglob("*.json"))
    sources += list((root / "client/ui").glob("*.tscn"))
    sources += [Path(__file__).resolve()]
    sources += list((root / "client").rglob("*.gd"))
    sources += list((root / "client").rglob("*.tscn"))
    sources = sorted(set(sources))
    pin = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    write_json(output / "source-pin.original.json", pin)
    try:
        admit("headless")
        command = [str(args.godot.resolve()), "--headless", "--path", str(root / "client"),
                   "--audio-driver", "Dummy", "res://tests/ui_visual_validation.tscn"]
        with (output / "headless.stdout.original.log").open("xb") as stdout, (output / "headless.stderr.original.log").open("xb") as stderr:
            child = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, creationflags=flags)
            write_json(output / "headless.started.original.json", {"pid": child.pid, "command": command})
            start = time.monotonic()
            try:
                while child.poll() is None:
                    if free_memory() < RESERVE or time.monotonic() - start > 45:
                        raise RuntimeError("Owned headless process reached resource/time guard")
                    time.sleep(.25)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
        diagnostic = json.loads((output / "headless-script-review.json").read_bytes())
        if child.returncode or not diagnostic["ok"] or (output / "headless.stderr.original.log").stat().st_size:
            raise RuntimeError("Headless validation failed; preserve diagnostics and do not start render")
        if args.scripts_only:
            write_json(output / "terminal.original.json", {"state": "HeadlessPassed", "native_exit": 0,
                                                           "render_started": False, "whole_visual_acceptance": False})
            return 0
        admit("render")
        result = render_private(root, output, args, env, flags, kernel, user, free_memory)
        unchanged = all(hashlib.sha256(p.read_bytes()).hexdigest() == pin[str(p.relative_to(root))] for p in sources)
        result["source_unchanged"] = unchanged
        result["whole_visual_acceptance"] = False
        write_json(output / "terminal.original.json", result)
        review_path = output / ("review.json" if args.scene == "ui_visual_review" else "report.json")
        if result["native_exit"] or result["stop_reason"] or not unchanged or not review_path.exists():
            return 1
        review = json.loads(review_path.read_bytes())
        if args.scene != "ui_visual_review":
            return 0 if review.get("ok", False) else 1
        return 0 if review["render_capture_complete"] and not review["legacy_layout_observations"] and all(review["checks"].values()) else 1
    except Exception as error:
        write_json(output / "failure.original.json", {"error": str(error), "type": type(error).__name__})
        return 1
    finally:
        kernel.ReleaseMutex(mutex)
        kernel.CloseHandle(mutex)


def render_private(root, output, args, env, flags, kernel, user, free_memory):
    user.GetProcessWindowStation.restype = W.HANDLE
    user.GetThreadDesktop.restype = W.HANDLE
    user.GetThreadDesktop.argtypes = [W.DWORD]
    user.OpenInputDesktop.restype = W.HANDLE
    user.OpenInputDesktop.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    user.GetUserObjectInformationW.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD)]
    user.CreateDesktopW.restype = W.HANDLE
    user.CreateDesktopW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPVOID, W.DWORD, W.DWORD, W.LPVOID]
    user.CloseDesktop.argtypes = [W.HANDLE]
    user.SetThreadDesktop.argtypes = [W.HANDLE]
    kernel.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL, W.DWORD,
                                     W.LPVOID, W.LPCWSTR, ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
    kernel.CreateProcessW.restype = W.BOOL
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    kernel.TerminateProcess.argtypes = [W.HANDLE, W.UINT]

    def object_name(handle):
        buffer = ctypes.create_unicode_buffer(1024)
        needed = W.DWORD()
        if not user.GetUserObjectInformationW(handle, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value

    def input_desktop():
        handle = user.OpenInputDesktop(0, False, 1)
        if not handle:
            return None
        try:
            return object_name(handle)
        finally:
            user.CloseDesktop(handle)

    original_desktop = user.GetThreadDesktop(kernel.GetCurrentThreadId())
    original_name = object_name(original_desktop)
    input_before = input_desktop()
    name = "CodexFantasyUI_" + uuid.uuid4().hex
    desktop = user.CreateDesktopW(name, None, None, 0, 0x000F01FF, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    process = None
    checks = []
    reason = None
    start = time.monotonic()
    try:
        command = [str(args.godot.resolve()), "--path", str(root / "client"), "--windowed", "--single-window",
                   "--resolution", f"{args.width}x{args.width * 9 // 16}", "--rendering-method", "gl_compatibility",
                   "--display-driver", "windows", "--audio-driver", "Dummy", "--max-fps", "30",
                   "res://tests/" + args.scene + ".tscn"]
        if args.verbose:
            command.append("--verbose")
        environment = ctypes.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda p: p[0].upper())) + "\0\0")
        with open(os.devnull, "rb") as stdin, (output / "stdout.original.log").open("xb") as stdout, (output / "stderr.original.log").open("xb") as stderr:
            for stream in (stdin, stdout, stderr):
                os.set_inheritable(stream.fileno(), True)
            startup = StartupInfo()
            startup.cb = ctypes.sizeof(startup)
            startup.desktop = object_name(user.GetProcessWindowStation()) + "\\" + name
            startup.flags = 0x100 | 1
            startup.show = 0
            startup.stdin, startup.stdout, startup.stderr = [msvcrt.get_osfhandle(f.fileno()) for f in (stdin, stdout, stderr)]
            info = ProcessInfo()
            if not kernel.CreateProcessW(str(args.godot.resolve()), ctypes.create_unicode_buffer(subprocess.list2cmdline(command)), None, None,
                                         True, flags | 0x400, environment, str(root), ctypes.byref(startup), ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = info.process
            kernel.CloseHandle(info.thread)
            write_json(output / "started.original.json", {"pid": info.pid, "thread_id": info.tid, "command": command,
                       "desktop": startup.desktop, "input_desktop_before": input_before,
                       "desktop_switch_calls": 0, "at": datetime.datetime.now().isoformat()})
            while kernel.WaitForSingleObject(process, 0) == 258:
                if free_memory() < RESERVE:
                    reason = "MemoryReserveBreached"
                if time.monotonic() - start > 180:
                    reason = "OwnedRendererDeadline"
                tail = (output / "stderr.original.log").read_bytes()[-16384:]
                if b"SCRIPT ERROR:" in tail or b"Parse Error:" in tail:
                    reason = "SceneScriptError"
                thread_desktop = user.GetThreadDesktop(info.tid)
                if thread_desktop:
                    actual = object_name(thread_desktop)
                    checks.append(actual)
                    if actual != name:
                        reason = "OwnedThreadLeftPrivateDesktop"
                if reason:
                    kernel.TerminateProcess(process, 1)
                    break
                time.sleep(.25)
            kernel.WaitForSingleObject(process, 10000)
            code = W.DWORD()
            if not kernel.GetExitCodeProcess(process, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
        input_after = input_desktop()
        # Exit status alone can hide cleanup/rendering diagnostics.
        if b"ERROR:" in (output / "stderr.original.log").read_bytes():
            reason = reason or "NativeDiagnosticError"
        if not checks:
            reason = reason or "NoPrivateDesktopObservation"
        return {"pid": info.pid, "native_exit": code.value, "stop_reason": reason,
                "private_desktop_checks": len(checks), "all_checked_threads_private": bool(checks) and set(checks) == {name},
                "input_desktop_unchanged": input_before == input_after if input_before is not None and input_after is not None else None,
                "desktop_switch_calls": 0, "seconds": round(time.monotonic() - start, 2),
                "PNGs": len(list(output.glob("*.png"))), "actual_game_matches": 0}
    finally:
        if process:
            if kernel.WaitForSingleObject(process, 0) == 258:
                kernel.TerminateProcess(process, 1)
                kernel.WaitForSingleObject(process, 10000)
            kernel.CloseHandle(process)
        restored = object_name(user.GetThreadDesktop(kernel.GetCurrentThreadId())) == original_name or bool(user.SetThreadDesktop(original_desktop))
        closed = bool(user.CloseDesktop(desktop))
        write_json(output / "desktop-cleanup.original.json", {"own_thread_restored": restored, "owned_desktop_closed": closed,
                                                            "desktop_switch_calls": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New immutable evidence directory")
    parser.add_argument("--scripts-only", action="store_true")
    parser.add_argument("--card-regression", action="store_true")
    registry = json.loads((Path(__file__).resolve().parents[1] / "client/data/localization_registry.json").read_text(encoding="utf-8"))
    parser.add_argument("--locale", choices=["zh-CN", "en"] + list(registry.get("languages", {})), default="zh-CN")
    parser.add_argument("--width", type=int, choices=[960, 1280, 1920], default=960)
    parser.add_argument("--screens", default="", help="Comma-separated screen families; empty means all")
    parser.add_argument("--scene", choices=["ui_visual_review", "codex_preview", "deck_builder_preview", "equipment_compare_preview", "ui_typography_probe", "ui_branch_sync_preview", "ui_google_branch_review"], default="ui_visual_review")
    parser.add_argument("--wait-seconds", type=int, default=0, help="Admission wait; does not reduce the fixed memory reserve")
    parser.add_argument("--verbose", action="store_true", help="Keep native verbose diagnostics in evidence logs")
    options = parser.parse_args()
    if options.wait_seconds < 0 or not options.godot.is_file():
        parser.error("Use a valid Godot executable and nonnegative admission wait")
    raise SystemExit(run(options))
