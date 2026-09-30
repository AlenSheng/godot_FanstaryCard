"""Verify archived bytes and native title pixels without rerunning Godot."""
from pathlib import Path
import hashlib
import json
from PIL import Image

root = Path(__file__).resolve().parent
inventory = json.loads((root / "file-index.json").read_text())
for entry in inventory:
    path = root / entry["path"]
    assert path.stat().st_size == entry["bytes"], entry["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
for entry in json.loads((root / "image-index.json").read_text()):
    with Image.open(root / entry["path"]) as picture:
        assert list(picture.size) == entry["pixels"], entry["path"]
        assert picture.mode == entry["mode"], entry["path"]

counts = {}
for phase in ("before", "after"):
    report = json.loads((root / phase / "report.json").read_text())
    differences = 0
    for check in report["pixel_checks"]:
        with Image.open(root / phase / check["actual"]) as actual:
            with Image.open(root / phase / check["reference"]) as reference:
                equal = actual.convert("RGBA").tobytes() == reference.convert("RGBA").tobytes()
                assert actual.size == reference.size == tuple(check["pixels"]), check["key"]
        assert equal == check["equal"], check["key"]
        differences += not equal
    counts[phase] = differences
assert counts == {"before": 27, "after": 0}, counts
print(json.dumps({"ok": True, "files": len(inventory), "native_pixel_differences": counts}))
