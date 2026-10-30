"""Prepare or run the guarded registry-language/3-size production error-tip UI matrix.

Every case delegates to tools.validate_ui_hidden.run. It owns the existing
6+1 GiB admission checks, shared mutex, private desktop and child-process guards.
This runner never changes that validator or starts Godot by another path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCALES = tuple(json.loads((ROOT / "client/data/localization_registry.json").read_text(encoding="utf-8"))["languages"])
WIDTHS = (960, 1280, 1920)
DEFAULT_OUTPUT = ROOT / "tmp/localization-error-ui-r1"


def write_once(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def case_plan(output: Path) -> list[dict]:
    return [{"locale": locale, "width": width, "output": str(output / f"{locale}-{width}")}
            for locale in LOCALES for width in WIDTHS]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT,
                        help="New immutable matrix root; existing roots are never reused")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--plan", action="store_true", help="Print the nine cases without writing or starting processes")
    args = parser.parse_args(argv)
    if args.wait_seconds < 0 or not args.godot.is_file():
        parser.error("Use an existing Godot executable and a nonnegative admission wait")
    output = args.output_root.resolve()
    plan = case_plan(output)
    if args.plan:
        print(json.dumps({"prepared_only": True, "expected_cases": len(plan), "expected_screenshots": len(plan) * 8,
                          "scene": "server_error_preview", "cases": plan}, ensure_ascii=True))
        return 0
    if os.name != "nt":
        parser.error("The existing guarded native UI validator requires Windows")
    if output.exists():
        parser.error("The matrix root already exists; choose a fresh immutable --output-root")
    sys.path.insert(0, str(ROOT / "tools"))
    from validate_ui_hidden import run

    output.mkdir(parents=True, exist_ok=False)
    pinned = [Path(__file__).resolve(), ROOT / "tools/validate_ui_hidden.py",
              ROOT / "client/tests/server_error_preview.gd", ROOT / "client/tests/server_error_preview.tscn"]
    pin = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in pinned}
    write_once(output / "matrix-plan.original.json", {"scene": "server_error_preview", "cases": plan,
               "expected_cases": len(plan), "expected_screenshots": len(plan) * 8, "source_pin": pin,
               "actual_game_matches": 0, "whole_visual_acceptance": False})
    results = []
    interrupted = False
    for case in plan:
        target = Path(case["output"])
        namespace = argparse.Namespace(godot=args.godot.resolve(), output=target,
            scene="server_error_preview", scripts_only=False, card_regression=False,
            locale=case["locale"], width=case["width"], screens="",
            wait_seconds=args.wait_seconds, verbose=args.verbose)
        try:
            exit_code = run(namespace)
            report_path = target / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            png_count = len(list(target.glob("*.png")))
            ok = exit_code == 0 and report.get("ok", False) and report.get("screenshots") == 8 and png_count == 8
            results.append({**case, "ok": ok, "guard_exit": exit_code, "screenshots": png_count,
                "failed_checks": [key for key, passed in report.get("checks", {}).items() if not passed],
                "effective_font_sizes": sorted({round(float(frame["effective_font_size"]), 4)
                                                for frame in report.get("frames", [])}),
                "actual_game_matches": report.get("actual_game_matches", 0)})
        except KeyboardInterrupt:
            interrupted = True
            results.append({**case, "ok": False, "error": "Interrupted; owned children remain governed by the validator"})
            break
        except Exception as error:
            results.append({**case, "ok": False, "error": str(error), "type": type(error).__name__})
    unchanged = all(hashlib.sha256(path.read_bytes()).hexdigest() == pin[str(path.relative_to(ROOT))] for path in pinned)
    summary = {"ok": len(results) == len(plan) and all(case["ok"] for case in results) and unchanged,
               "cases": results, "executed_cases": len(results), "expected_cases": len(plan),
               "screenshots": sum(case.get("screenshots", 0) for case in results), "expected_screenshots": len(plan) * 8,
               "interrupted": interrupted, "runner_sources_unchanged": unchanged,
               "actual_game_matches": 0, "whole_visual_acceptance": False}
    write_once(output / "matrix-report.original.json", summary)
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
