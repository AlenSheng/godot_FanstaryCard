"""Check release prerequisites, then optionally export the Windows Steam preset."""

import argparse
import configparser
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from release_protection import PRIVATE, SOURCE, TEMPLATE, engine_path, engine_version, load_key, template_status


ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "client"


def read_config(path):
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read_string("[godot_header]\n" + path.read_text(encoding="utf-8"))
    return config


def unquote(value):
    return value.strip().strip('"')


def protection_checks(preset):
    blockers = []
    for option in ("encrypt_pck", "encrypt_directory"):
        if not preset.getboolean("preset.0", option, fallback=False):
            blockers.append("Protected exports require " + option + "=true.")
    if unquote(preset.get("preset.0", "encryption_include_filters", fallback="")) != "*":
        blockers.append("Every PCK file must match encryption_include_filters=\"*\".")
    if unquote(preset.get("preset.0", "encryption_exclude_filters", fallback="")):
        blockers.append("Encryption exclusions are not allowed.")
    if preset.getint("preset.0", "script_export_mode", fallback=0) != 2:
        blockers.append("Scripts must be exported as compressed binary tokens.")
    if preset.getboolean("preset.0.options", "binary_format/embed_pck", fallback=False):
        blockers.append("The encrypted PCK verifier requires a standalone PCK.")
    custom = unquote(preset.get("preset.0.options", "custom_template/release", fallback=""))
    if not custom or (CLIENT / custom).resolve() != TEMPLATE.resolve():
        blockers.append("Release preset must use the verified private template.")
    return blockers


def protected_export(executable, key, candidate, base_destination):
    from verify_encrypted_pck import verify_pck

    working = Path(tempfile.mkdtemp(prefix="client-", dir=PRIVATE))
    package_dir = working / "package"
    package_dir.mkdir()
    export_path = package_dir / "Relicbound.exe"
    env = os.environ.copy()
    env["GODOT_SCRIPT_ENCRYPTION_KEY"] = key
    with (working / "export.log").open("w", encoding="utf-8") as log:
        run = subprocess.run([str(executable), "--headless", "--path", str(CLIENT), "--export-release",
                              "Windows Desktop", str(export_path)], env=env, stdout=log,
                             stderr=subprocess.STDOUT, timeout=600)
    if run.returncode or not export_path.is_file() or not export_path.with_suffix(".pck").is_file():
        raise ValueError("Godot export failed; inspect " + str(working / "export.log"))
    verification = verify_pck(export_path.with_suffix(".pck"), key)
    clean_env = {name: value for name, value in os.environ.items()
                 if name not in ("GODOT_SCRIPT_ENCRYPTION_KEY", "SCRIPT_AES256_ENCRYPTION_KEY")}
    smoke = subprocess.run([str(export_path), "--headless", "--quit-after", "30"],
                           cwd=package_dir, env=clean_env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    startup_log = smoke.stdout + smoke.stderr
    (working / "startup.log").write_text(startup_log, encoding="utf-8")
    if smoke.returncode or "SCRIPT ERROR" in startup_log or "ERROR:" in startup_log:
        raise ValueError("Encrypted game startup failed; inspect " + str(working / "startup.log"))
    negative = subprocess.run([str(executable), "--headless", "--path", str(package_dir), "--main-pack",
                              str(export_path.with_suffix(".pck")), "--quit-after", "1"],
                             cwd=package_dir, env=clean_env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    negative_log = negative.stdout + negative.stderr
    (working / "wrong-key.log").write_text(negative_log, encoding="utf-8")
    # Godot 4.7 can return zero after a pack-load error; require its explicit rejection diagnostics.
    if "Can't open encrypted pack directory." not in negative_log or "Cannot open resource pack" not in negative_log:
        raise ValueError("The stock engine did not demonstrate rejection of the encrypted package.")
    legal_sources = [
        (SOURCE / "LICENSE.txt", "Godot-LICENSE.txt"),
        (SOURCE / "COPYRIGHT.txt", "Godot-COPYRIGHT.txt"),
        (CLIENT / "assets/fonts/LICENSE-SourceHanSans.txt", "LICENSE-SourceHanSans.txt"),
        (CLIENT / "assets/fonts/LICENSE-SourceHanSerif.txt", "LICENSE-SourceHanSerif.txt"),
        (CLIENT / "assets/audio/LICENSE.txt", "Audio-CC0.txt"),
    ]
    for item in package_dir.rglob("*"):
        if item.is_file() and item.suffix.lower() not in (".exe", ".pck", ".dll"):
            raise ValueError("Unexpected loose file in exported package: " + str(item.relative_to(package_dir)))
    licenses = package_dir / "licenses"
    licenses.mkdir()
    for source, name in legal_sources:
        shutil.copy2(source, licenses / name)
    # Promote only validated outputs; neither build logs nor private inputs are distributed.
    destination = (ROOT / "builds/windows-protected-candidate" if candidate else base_destination.parent) / working.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_dir, destination)
    verification.update(startup_passed=True, stock_engine_rejected=True, candidate=candidate)
    (destination / "protection-verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    if candidate:
        (destination / "CANDIDATE-NOT-FOR-DISTRIBUTION.txt").write_text(
            "Encryption/startup validation candidate. Steam and production service prerequisites are not satisfied.\n",
            encoding="utf-8")
    return str(destination / export_path.name), verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", action="store_true", help="Export only after every prerequisite passes")
    parser.add_argument("--executable", help="Godot executable; defaults to the project's configured engine")
    parser.add_argument("--candidate", action="store_true", help="Validate encryption/startup only; retain production platform blockers in report")
    args = parser.parse_args()
    project = read_config(CLIENT / "project.godot")
    preset = read_config(CLIENT / "export_presets.cfg")
    blockers = []
    if project.getint("platform", "steam/app_id", fallback=0) <= 0:
        blockers.append("Configure the game's real platform/steam/app_id.")
    if not unquote(project.get("platform", "steam/web_api_identity", fallback="")):
        blockers.append("Configure platform/steam/web_api_identity to match the server.")
    if not unquote(project.get("platform", "server_url", fallback="")).startswith("https://"):
        blockers.append("Configure an HTTPS platform/server_url for the release.")
    steam_extensions = [p for p in CLIENT.rglob("*.gdextension") if ".godot" not in p.parts and "steam" in str(p.relative_to(CLIENT)).lower()]
    release_library = False
    for extension in steam_extensions:
        config = read_config(extension)
        for selector, value in config.items("libraries") if config.has_section("libraries") else []:
            if "windows" not in selector or "x86_64" not in selector or "debug" in selector:
                continue
            path = unquote(value)
            if path.startswith("res://") and (CLIENT / path.removeprefix("res://")).is_file():
                release_library = True
    if not release_library:
        blockers.append("Install a compatible GodotSteam GDExtension and its Windows x86_64 release library.")
    release_blockers = list(blockers)
    blockers = protection_checks(preset)
    executable, version, key = None, "", ""
    try:
        executable = engine_path(args.executable)
        version = engine_version(executable)
        key = load_key()
        template_status(version, key)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        blockers.append(str(error))
    export_path = (CLIENT / unquote(preset.get("preset.0", "export_path"))).resolve()
    if not export_path.is_relative_to((ROOT / "builds").resolve()):
        blockers.append("Export destination must remain inside this project's builds directory.")
    active_blockers = blockers + ([] if args.candidate else release_blockers)
    report = {"ready": not active_blockers, "production_ready": not blockers and not release_blockers,
              "candidate": args.candidate, "exported": False, "engine_version": version,
              "preset": "Windows Desktop", "output": str(export_path), "blockers": active_blockers,
              "production_blockers": release_blockers}
    if args.export and not active_blockers:
        try:
            report["output"], report["verification"] = protected_export(executable, key, args.candidate, export_path)
            report["exported"] = True
        except (OSError, ValueError, ImportError, subprocess.SubprocessError) as error:
            report["ready"] = False
            report["blockers"].append(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] and (not args.export or report["exported"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
