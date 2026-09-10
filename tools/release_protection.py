"""Build and validate the private Godot template used by protected exports."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "tools/engine-local/protected"
SOURCE = PRIVATE / "godot"
TEMPLATE = PRIVATE / "windows_release_x86_64.exe"
RECEIPT = PRIVATE / "template.json"
PYTHON = PRIVATE / "venv/Scripts/python.exe"
SOURCE_URL = "https://github.com/godotengine/godot.git"
BUILD_FLAGS = [
    "platform=windows", "arch=x86_64", "target=template_release",
    "production=yes", "debug_symbols=no", "dev_build=no", "lto=none",
    "optimize=speed", "winrt=no", "d3d12=no", "vulkan=no",
    "module_mono_enabled=no", "use_static_cpp=yes",
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def key_id(key):
    return hashlib.sha256(bytes.fromhex(key)).hexdigest()


def key_path():
    return ROOT / "release-encryption.key"


def load_key(create=False):
    value = os.environ.get("GODOT_SCRIPT_ENCRYPTION_KEY", "")
    if not value:
        path = key_path()
        if not path.is_file():
            if not create:
                raise ValueError("Private release key missing; run tools/release_protection.py build-template.")
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("x", encoding="ascii") as stream:
                    stream.write(secrets.token_hex(32) + "\n")
            except FileExistsError:
                pass
        value = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value) or int(value, 16) == 0:
        raise ValueError("Release key must be a nonzero 256-bit hexadecimal value.")
    return value.lower()


def engine_path(override=None):
    value = override or os.environ.get("A3GAME_GODOT_EXECUTABLE")
    if not value:
        record = ROOT / "tools/engine-local/godot-4.7.2-stable-windows-x86_64.json"
        value = json.loads(record.read_text(encoding="utf-8"))["executable"] if record.is_file() else ""
    if not value or not Path(value).is_file():
        raise ValueError("Configure an existing Godot executable.")
    return Path(value).resolve()


def engine_version(executable):
    result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=30, check=True)
    match = re.search(r"\d+\.\d+\.\d+\.stable(?:\.[\w]+)*", result.stdout)
    if not match:
        raise ValueError("Protected builds require a stable, versioned Godot executable.")
    return match.group(0)


def template_status(version, key):
    if not TEMPLATE.is_file() or not RECEIPT.is_file():
        raise ValueError("Private encryption template missing; run tools/release_protection.py build-template.")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("engine_version") != version:
        raise ValueError("Encryption template was built for a different Godot version; rebuild it.")
    if receipt.get("key_id") != key_id(key):
        raise ValueError("Encryption template and export key do not match; rebuild the template.")
    if receipt.get("template_sha256") != sha256(TEMPLATE):
        raise ValueError("Encryption template checksum changed; rebuild it.")
    if receipt.get("build_flags") != BUILD_FLAGS:
        raise ValueError("Encryption template build settings changed; rebuild it.")
    return receipt


def build_template(executable, jobs):
    version = engine_version(executable)
    release = version.split(".stable", 1)[0]
    tag = release + "-stable"
    key = load_key(create=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if not PYTHON.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(PRIVATE / "venv")], check=True)
    subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "tools/release-requirements.txt")], check=True)
    if not (SOURCE / ".git").is_dir():
        subprocess.run(["git", "-c", "core.longpaths=true", "clone", "--depth", "1", "--branch", tag,
                        SOURCE_URL, str(SOURCE)], check=True)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(SOURCE), *args], text=True).strip()

    if git("remote", "get-url", "origin") != SOURCE_URL:
        raise ValueError("Template source origin is not the official Godot repository.")
    commit = git("rev-parse", "HEAD")
    if commit != git("rev-parse", tag + "^{commit}") or git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Template source must be the unmodified matching Godot release tag.")
    official_commit = version.rsplit(".", 1)[-1]
    if "official" in version and not commit.startswith(official_commit):
        raise ValueError("Template source commit does not match the installed official editor.")
    env = os.environ.copy()
    env["SCRIPT_AES256_ENCRYPTION_KEY"] = key
    log = PRIVATE / "template-build.log"
    print("Building private template; compiler log: " + str(log), flush=True)
    with log.open("w", encoding="utf-8") as output:
        build = subprocess.run([str(PYTHON), "-m", "SCons", *BUILD_FLAGS, "-j", str(jobs)],
                               cwd=SOURCE, env=env, stdout=output, stderr=subprocess.STDOUT)
    if build.returncode:
        raise ValueError("Private template compilation failed; inspect " + str(log))
    binary = SOURCE / "bin/godot.windows.template_release.x86_64.exe"
    if not binary.is_file() or bytes.fromhex(key) not in binary.read_bytes():
        raise ValueError("Compiled template does not contain the intended embedded key.")
    shutil.copy2(binary, TEMPLATE)
    receipt = {"engine_version": version, "source_url": SOURCE_URL, "source_tag": tag,
               "source_commit": commit, "template_sha256": sha256(TEMPLATE),
               "key_id": key_id(key), "build_flags": BUILD_FLAGS}
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "build-template"])
    parser.add_argument("--executable")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    args = parser.parse_args()
    try:
        executable = engine_path(args.executable)
        if args.action == "build-template":
            report = build_template(executable, max(1, args.jobs))
        else:
            report = template_status(engine_version(executable), load_key())
        print(json.dumps({"ready": True, **report}, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"ready": False, "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
