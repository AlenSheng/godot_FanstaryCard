"""Keep each Godot fixture's settings and user data inside its evidence directory."""
import os
import shutil
import ctypes
import subprocess
import time
from pathlib import Path


class FixtureResourceGuard(RuntimeError):
    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


def guarded_run(command, *, env, timeout=90, wait_seconds=0):
    """Keep the local Windows reserve while owning exactly one Godot child."""
    options = dict(env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if os.name != "nt":
        return subprocess.run(command, timeout=timeout, **options)
    reserve, startup = 6 * 1024 ** 3, 1024 ** 3
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total", "available", "total_page", "available_page",
                                                 "total_virtual", "available_virtual", "extended")]
    def available():
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError()
        return status.available
    admission_start = time.monotonic()
    while True:
        samples = []
        for _ in range(3):
            samples.append(available())
            time.sleep(1)
        if min(samples) >= reserve + startup:
            break
        if time.monotonic() - admission_start >= wait_seconds:
            raise FixtureResourceGuard("Resource admission unavailable; no Godot child started")
        time.sleep(min(10, max(0, wait_seconds - (time.monotonic() - admission_start))))
    child = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS, **options)
    started = time.monotonic()
    try:
        while True:
            try:
                stdout, stderr = child.communicate(timeout=.25)
                return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if available() < reserve:
                    child.kill()
                    stdout, stderr = child.communicate(timeout=10)
                    raise FixtureResourceGuard("Owned Godot fixture reached memory guard", stdout + stderr)
                if time.monotonic() - started >= timeout:
                    child.kill()
                    stdout, stderr = child.communicate(timeout=10)
                    raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)


def isolated_environment(work: Path, **overrides):
    # Network errors use the same lightweight language tables as the UI.
    # Isolated protocol projects need the text dependency, but no fonts or art.
    repository = Path(__file__).resolve().parents[2]
    dependencies = [repository / "client/ui/palette.gd",
                    repository / "client/data/localization_registry.json",
                    repository / "client/data/localization_legacy.json"]
    dependencies += list((repository / "client/data/locales").glob("*.json"))
    for source in dependencies:
        target = work / source.relative_to(repository / "client")
        if target.resolve() == source.resolve():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    env = dict(os.environ, **overrides)
    directories = {
        "XDG_DATA_HOME": work / "runtime" / "data",
        "XDG_CONFIG_HOME": work / "runtime" / "config",
        "XDG_CACHE_HOME": work / "runtime" / "cache",
    }
    if os.name == "nt":
        directories.update({"APPDATA": work / "runtime" / "roaming",
                            "LOCALAPPDATA": work / "runtime" / "local"})
    for key, directory in directories.items():
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    return env
