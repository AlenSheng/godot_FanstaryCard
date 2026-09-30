#!/usr/bin/env python3
"""Index fresh, after-only native integration captures without inventing a before phase.

Contact sheets resize evidence thumbnails only. Runtime artwork is never edited.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    args.out.mkdir(parents=True, exist_ok=True)
    errors, assets, references, captures = [], [], [], []
    manifest = json.loads((repo / "client/assets/imported/manifest.json").read_text())
    for key, entry in sorted(manifest["files"].items()):
        path = repo / "client" / entry["path"].removeprefix("res://")
        if not path.is_file():
            errors.append(f"missing {key}: {entry['path']}")
            continue
        with Image.open(path) as img:
            img.load()
            row = {"key": key, "path": entry["path"], "pixels": list(img.size),
                   "mode": img.mode, "sha256": digest(path)}
        assets.append(row)
        if row["sha256"] != entry.get("imported_sha256"):
            errors.append(f"imported_sha256 mismatch {key}")
    for path in sorted((repo / "client").rglob("*")):
        if not path.is_file() or path.suffix not in {".gd", ".tscn", ".tres", ".godot"}:
            continue
        if path.suffix == ".gd" and "tests" in path.relative_to(repo / "client").parts:
            continue
        for literal in sorted(set(re.findall(r'"(res://[^"\n]+)"', path.read_text()))):
            if "%" in literal or literal.endswith("/") or literal.startswith("res://evidence/"):
                continue
            exists = (repo / "client" / literal.removeprefix("res://")).exists()
            references.append({"source": str(path.relative_to(repo)), "resource": literal, "exists": exists})
            if not exists:
                errors.append(f"missing literal reference {path.relative_to(repo)}: {literal}")
    save_json(args.out / "assets.json", {"ok": not errors, "source_sha": args.source_sha,
              "manifest_files": len(assets), "monster_species": len(manifest["monsters"]),
              "literal_references": references, "files": assets, "errors": errors.copy()})
    counts = {}
    for suite, subfolder, expected in [("render", "after", 150), ("mail", "after", 36),
                                        ("codex", "after", 30), ("art", "", 66),
                                        ("settings", "", 12)]:
        folder = args.evidence_root / suite / subfolder
        report = json.loads((folder / "report.json").read_text())
        if not report.get("ok") or report.get("source_sha") != args.source_sha:
            errors.append(f"invalid report or source: {suite}")
        paths = sorted(folder.glob("*.png"))
        advertised = report.get("captures", [{"file": path.name} for path in paths])
        if {p.name for p in paths} != {c["file"] for c in advertised}:
            errors.append(f"capture list differs from actual PNGs: {suite}")
        if len(paths) != expected or report["screenshots"] != expected:
            errors.append(f"capture count differs from {expected}: {suite}")
        rows = []
        for capture in advertised:
            path = folder / capture["file"]
            with Image.open(path) as img:
                img.load()
                pixels = list(img.size)
            if "pixels" in capture and pixels != capture["pixels"]:
                errors.append(f"dimensions differ from report: {path}")
            row = {"suite": suite, "file": str(path.relative_to(args.evidence_root)),
                   "sha256": digest(path), "bytes": path.stat().st_size, "pixels": pixels,
                   "source_sha": report["source_sha"]}
            rows.append(row)
            captures.append(row)
        counts[suite] = len(rows)
        save_json(args.out / f"{suite}-capture-index.json", {"screenshots": len(rows), "captures": rows})
        for start in range(0, len(rows), 49):
            canvas = Image.new("RGB", (1680, 1162), "#18252a")
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 5), f"{suite} | {args.source_sha} | NEW actual Godot viewport captures", fill="white")
            for n, row in enumerate(rows[start:start + 49]):
                x, y = (n % 7) * 240, 30 + (n // 7) * 161
                with Image.open(args.evidence_root / row["file"]) as src:
                    thumb = src.convert("RGB")
                    thumb.thumbnail((238, 134))
                    canvas.paste(thumb, (x, y))
                draw.text((x + 2, y + 137), Path(row["file"]).stem, fill="white")
            canvas.save(args.out / f"{suite}-contact-{start // 49 + 1}.jpg", quality=90)
    result = {"ok": not errors, "source_sha": args.source_sha,
              "indexer_sha256": digest(Path(__file__)), "assets": len(assets),
              "literal_references": len(references), "screenshots": len(captures),
              "suite_counts": counts, "errors": errors, "captures": captures}
    save_json(args.out / "capture-index.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "captures"}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
