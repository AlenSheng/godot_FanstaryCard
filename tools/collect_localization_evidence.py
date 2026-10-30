"""Collect a complete native UI matrix without granting independent approval."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(cases):
    rows, screenshots, current_hashes = [], {}, {}
    for case in cases:
        folder = ROOT / case["path"]
        terminal = read(folder / "terminal.original.json")
        review = read(folder / "review.json")
        pin = read(folder / "source-pin.original.json")
        mismatches = []
        for relative, expected in pin.items():
            path = ROOT / relative
            if relative not in current_hashes:
                current_hashes[relative] = digest(path) if path.is_file() else None
            if current_hashes[relative] != expected:
                mismatches.append(relative)
        pngs = sorted(folder.glob("*.png"))
        failed = [key for key, value in review["checks"].items() if not value]
        ok = (terminal.get("native_exit") == 0 and not terminal.get("stop_reason")
              and terminal.get("source_unchanged") is True and not mismatches
              and terminal.get("all_checked_threads_private") is True
              and review.get("render_capture_complete") is True
              and review["languages"] == [case["locale"]] and review["widths"] == [case["width"]]
              and len(pngs) == review["expected_frames"] == review["screenshots"]
              and not failed and not review["legacy_layout_observations"])
        rows.append({**case, "ok": ok, "frames": len(pngs), "checks": len(review["checks"]),
                     "failed_checks": failed, "source_mismatches": mismatches,
                     "layout_errors": review["legacy_layout_observations"],
                     "terminal_sha256": digest(folder / "terminal.original.json"),
                     "review_sha256": digest(folder / "review.json"), "actual_game_matches": 0})
        screenshots.update({str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in pngs})
    return {"local_ui_passed": bool(rows) and all(row["ok"] for row in rows), "cases": rows,
            "screenshots": sum(row["frames"] for row in rows), "checks": sum(row["checks"] for row in rows),
            "screenshot_sha256": screenshots, "runtime_source_sha256": current_hashes,
            "independent_review_passed": False, "game_batch_passed": False, "deployed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = collect(read(args.cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit("Use a new immutable evidence output")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["local_ui_passed", "screenshots", "checks", "independent_review_passed"]}))
    raise SystemExit(0 if report["local_ui_passed"] else 1)
