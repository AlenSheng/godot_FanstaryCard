#!/usr/bin/env python3
"""Validate shipped UI assets and index actual Godot viewport captures.

Contact sheets only resize existing evidence thumbnails, never runtime artwork.
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
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((repo / "client/assets/imported/manifest.json").read_text())
    errors, assets, references = [], [], []
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
            if "%" in literal or literal.endswith("/"):
                continue
            target = repo / "client" / literal.removeprefix("res://")
            # Evidence files are output paths, not runtime dependencies.
            if literal.startswith("res://evidence/"):
                continue
            exists = target.exists()
            references.append({"source": str(path.relative_to(repo)), "resource": literal, "exists": exists})
            if not exists:
                errors.append(f"missing literal reference {path.relative_to(repo)}: {literal}")
    save_json(args.out / "assets.json", {"ok": not errors, "manifest_files": len(assets),
              "codex_cards": 220, "monster_species": len(manifest["monsters"]),
              "literal_references": references, "files": assets, "errors": errors})
    evidence = []
    for phase in ["before", "after"]:
        folder = args.evidence_root / phase
        report = json.loads((folder / "report.json").read_text())
        captures = report["captures"]
        for capture in captures:
            path = folder / capture["file"]
            evidence.append({"phase": phase, "file": capture["file"], "sha256": digest(path),
                             "pixels": capture["pixels"], "source_sha": report["source_sha"]})
        for start in range(0, len(captures), 49):
            batch = captures[start:start + 49]
            canvas = Image.new("RGB", (1680, 1162), "#18252a")
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 5), f"{phase} | {report['source_sha']} | actual Godot viewport captures", fill="white")
            for n, capture in enumerate(batch):
                x, y = (n % 7) * 240, 30 + (n // 7) * 161
                with Image.open(folder / capture["file"]) as src:
                    thumb = src.convert("RGB")
                    thumb.thumbnail((238, 134))
                    canvas.paste(thumb, (x, y))
                draw.text((x + 2, y + 137), capture["name"].replace("_", " "), fill="white")
            canvas.save(args.out / f"{phase}-contact-{start // 49 + 1}.jpg", quality=90)
    save_json(args.out / "capture-index.json", {"screenshots": len(evidence), "captures": evidence})
    print(json.dumps({"ok": not errors, "assets": len(assets), "literal_references": len(references),
                      "captures": len(evidence), "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
