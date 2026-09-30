#!/usr/bin/env python3
"""Verify saved evidence bytes and result receipts; does not rerun gameplay."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = "4f174ac04accafbb1ec34cbda85d962fecbd523e"


def read(name):
    return json.loads((ROOT / name).read_text())


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trx_counters(name):
    ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
    counters = ET.parse(ROOT / name).find(".//t:Counters", ns)
    return {k: int(v) for k, v in counters.attrib.items()}


def verify():
    inventory = read("file-index.json")
    for row in inventory:
        path = ROOT / row["path"]
        require(path.is_file(), f"Missing archived file: {row['path']}")
        require(path.stat().st_size == row["bytes"], f"Byte size: {row['path']}")
        require(digest(path) == row["sha256"], f"SHA256: {row['path']}")

    captures = read("new-capture-index.json")
    require(len(captures) == 272, "Expected 128 full native PNGs and 144 title crops")
    full = 0
    for row in captures:
        path = ROOT / row["path"]
        require(row["source_sha"] == SOURCE, f"Capture source: {row['path']}")
        require(digest(path) == row["sha256"], f"Capture SHA256: {row['path']}")
        with Image.open(path) as img:
            require(list(img.size) == row["pixels"], f"Capture dimensions: {row['path']}")
        full += "/pixels/" not in row["path"]
    require(full == 128, "Native full viewport count")

    for label, count in [("representatives", 48), ("mail", 24), ("codex", 20), ("monster-titles", 36)]:
        report = read(label + "/report.json")
        require(report["source_sha"] == SOURCE, f"Runtime source: {label}")
        require(report["ok"] and not report["errors"], f"Runtime result: {label}")
        require(report["screenshots"] == count, f"Screenshot count: {label}")
        require(all(report.get("checks", {}).values()), f"Checks: {label}")

    monsters = read("monster-titles/report.json")
    require(len(monsters["pixel_checks"]) == 72, "Monster native pixel comparisons")
    require(len(monsters["title_metrics"]) == 72, "Monster title observations")
    species = set()
    for row in monsters["title_metrics"]:
        require(row["fits"] and row["full_species"] and row["font_is_themed_title"], row["key"])
        require(row["single_line"] and row["lines"] == 1 and row["font_size"] >= 16, row["key"])
        species.add(row["species_name"])
    require(len(species) == 24, "Twelve species in each of two languages")
    for row in monsters["pixel_checks"]:
        require(row["equal"], row["key"])
        with Image.open(ROOT / "monster-titles" / row["actual"]) as actual, Image.open(ROOT / "monster-titles" / row["reference"]) as reference:
            require(actual.size == reference.size, row["key"])
            require(actual.convert("RGBA").tobytes() == reference.convert("RGBA").tobytes(), row["key"])

    mail = read("mail/report.json")
    require(len(mail["pixel_checks"]) == 8, "Mail native pixel groups")
    require(all(x["buttons_with_pixel_difference"] == 0 for x in mail["pixel_checks"]), "Mail button pixels")
    require(all(x["fits"] for x in mail["button_metrics"]), "Mail actual themed font metrics")

    for path in ["callback/report.json", "http-codec/results.json", "http-boundary/result.json", "ui-modules.json", "new-session-modules.json"]:
        require(read(path)["ok"], path)
    require(len(read("ui-modules.json")["tests"]) == 19, "Nineteen original UI modules")
    require(len(read("new-session-modules.json")["tests"]) == 2, "Two new original session modules")
    for file in ["local-commands.json", "native-commands.json"]:
        for row in read(file):
            require(row["source_sha"] == SOURCE and row["exit_code"] == 0, row["label"])

    ready = read("ready-stop-compat/report.json")
    require(ready["source_sha"] == SOURCE and ready["ok"] and ready["passed_case_count"] == 5, "READY/STOP original receipts")
    require(ready["owned_server_stopped"] and ready["owned_postgres_stopped"], "READY cleanup")
    require(not read("ready-stop/report.json")["ok"], "Retain initial READY failure")
    passed = trx_counters("ack/ack-process-02/results/targeted.trx")
    failed = trx_counters("ack/ack-process-01/results/targeted.trx")
    require(passed["total"] == 7 and passed["passed"] == 7 and passed["failed"] == 0 and passed["notExecuted"] == 0, "Original ACK/STOP/cycle TRX")
    require(failed["total"] == 7 and failed["failed"] == 7, "Retain original ACK startup failure")
    for attempt in ["ack-process-01", "ack-process-02"]:
        cleanup = read(f"ack/{attempt}/schema-cleanup-check.json")
        require(cleanup["exit_code"] == 0 and cleanup["remaining_owned_schemas"] == "0", attempt + " schema cleanup")
        require(read(f"ack/{attempt}/inputs.json")["source_sha"] == SOURCE, attempt + " source")

    guard = read("preservation-final.json")
    require(guard["existing_non_ui_paths"] == 7550 and guard["production_ui_paths"] == 13, "Frozen input counts")
    for field in ["source_commit_mismatches", "final_worktree_mismatches", "ui_mismatches", "conflicts", "new_production_changes_during_verification"]:
        require(not guard[field], field)
    original = []
    for i in range(1, 9):
        original.extend(read(f"non-ui-inputs-{i:02}.json"))
    require(len(original) == 7550 and len({x["path"] for x in original}) == 7550, "Original non-UI index")

    repo = ROOT.parents[2]
    git_verified = False
    if (repo / "client/project.godot").exists():
        tree = subprocess.check_output(["git", "ls-tree", "-r", "-z", SOURCE], cwd=repo)
        entries = {}
        for line in tree.split(b"\0"):
            if not line:
                continue
            metadata, path = line.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            entries[path.decode()] = {"mode": mode, "type": kind, "blob": blob}
        for row in original:
            require(entries[row["path"]] == {k: row[k] for k in ["mode", "type", "blob"]}, "Non-UI source blob: " + row["path"])
        for group in read("source-map.json").values():
            if not isinstance(group, dict):
                continue
            for path, spec in group.items():
                require(digest(repo / path) == spec["sha256"], "Final preserved source bytes: " + path)
        git_verified = True

    preview = read("library-preview.json")
    require(digest(ROOT / "monster-titles/monsters_1_en_1280.png") == "2a28f1910d556b01d5023377eb2a5d138e978c21cbede2f7f4484d8f70cf6e55", "Persisted Library PNG source")
    return {"ok": True, "checked_archived_files": len(inventory), "tested_source_sha": SOURCE, "native_full_pngs": full, "native_title_crop_pngs": 144, "native_monster_pixel_comparisons": 72, "mail_pixel_groups": 8, "ready_stop_passed": 5, "ack_cycle_stop_passed": 7, "failed_attempts_preserved": True, "non_ui_input_entries": len(original), "git_source_and_preserved_bytes_verified": git_verified, "library_preview_id": preview["library_file_id"], "qualification": "Evidence verification only; no gameplay rerun and no CI or LIVE acceptance."}


if __name__ == "__main__":
    try:
        result = verify()
    except Exception as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
