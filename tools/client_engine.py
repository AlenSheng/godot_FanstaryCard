"""Human/CI entry point using the public GameFactory Godot client."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "GameFactory-3A"))
from engine_adapters.godot import GodotClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "validate", "test", "play", "integration", "art-preview", "codex-preview", "codex-integration", "assets", "import"])
    args = parser.parse_args()
    executable = os.environ.get("A3GAME_GODOT_EXECUTABLE")
    if not executable:
        manifest = ROOT / "tools/engine-local/godot-4.7.2-stable-windows-x86_64.json"
        executable = json.loads(manifest.read_text())["executable"]
    client = GodotClient(project_path=str(ROOT / "client"), godot_executable=executable)
    if args.action == "create":
        result = client.project.create(project_name="FantasyCard")
    elif args.action == "validate":
        result = client.project.validate(check_engine=True)
        diagnostics = result.get("payload", {}).get("main_scene_load_process", {}).get("stderr", "")
        if "SCRIPT ERROR" in diagnostics or "Failed to load script" in diagnostics:
            result["ok"] = False
            result.setdefault("errors", []).append(diagnostics)
    elif args.action == "test":
        result = client.testing.run_automation_tests(test_root="res://tests")
    elif args.action == "assets":
        result = client.assets.register_resource(resource_path="res://assets/portal.png", asset_type="texture", asset_id="camp-portal")
    elif args.action == "import":
        result = client.runtime.launch_editor(extra_args=["--headless", "--import", "--quit", "--log-file", str(ROOT / "client/import.log")])
    elif args.action in ("integration", "art-preview", "codex-preview", "codex-integration"):
        preview = args.action == "art-preview"
        codex = args.action.startswith("codex-")
        evidence = {"art-preview": "art", "integration": "live", "codex-preview": "codex", "codex-integration": "codex-live"}[args.action]
        report = ROOT / f"client/evidence/{evidence}/report.json"
        previous = report.stat().st_mtime_ns if report.exists() else 0
        scene = "res://tests/art_preview.tscn" if preview else "res://tests/integration.tscn"
        if codex:
            scene = "res://tests/" + args.action.replace("-", "_") + ".tscn"
        log = f"client/{args.action}.log"
        # Keep automated visual/self-check runs compact and non-fullscreen. The
        # client viewport uses canvas scaling, so gameplay coordinates remain
        # authoritative while the spawned window is a manageable 800x600.
        result = client.runtime.launch_game(scene_path=scene, headless=False, extra_args=["--windowed", "--resolution", "800x600", "--log-file", str(ROOT / log)])
        if result.get("ok"):
            process_id = result["payload"]["process_id"]
            deadline = time.monotonic() + 410
            try:
                while time.monotonic() < deadline:
                    if report.exists() and report.stat().st_mtime_ns != previous:
                        result = json.loads(report.read_text(encoding="utf-8"))
                        break
                    time.sleep(1)
                else:
                    result = {"ok": False, "error": "Live integration timeout"}
            finally:
                # Keep the owning client alive throughout the run for bounded cleanup.
                client.runtime.stop_game(process_id)
    else:
        result = client.runtime.launch_game(headless=False)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
