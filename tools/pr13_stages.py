"""Freeze and verify current PR13 stage inputs without inventing runtime results."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PLAN = "docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json"
PROFILE = "docs/plans/PR13_LOCAL_PROFILES_20261008.json"
QUEUES = (
    "docs/plans/GAMEPLAY_LOAD_EXECUTION_20260929.json",
    "docs/plans/PR13_REMAINING_QUEUE_20260930.json",
    "docs/plans/PR13_COMBAT_EXPERIENCE_QUEUE_20260930.json",
)
HISTORY = "docs/reports/pr13-execution-20260930/register.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                   encoding="utf-8").strip()


def file_record(path, root=ROOT):
    path = Path(path).resolve()
    relative = path.relative_to(root.resolve()).as_posix()
    return {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)}


def validate_profiles(profiles):
    errors = []
    expected = {"OFFLINE", "POSTGRES", "LIVE", "RENDER", "EXPERIMENT", "CAPACITY", "AUDIT"}
    if set(profiles.get("profiles", {})) != expected:
        errors.append("All seven profiles must be frozen")
    for name, value in profiles.get("profiles", {}).items():
        for key in ("deadline_seconds", "cleanup_seconds"):
            number = value.get(key)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0:
                errors.append(f"{name}: positive finite {key} required")
        if not value.get("pass_criteria") or not value.get("stop_conditions"):
            errors.append(f"{name}: observable pass and stop conditions required")
    capacity = profiles.get("profiles", {}).get("CAPACITY", {})
    if capacity.get("active_targets") != [50, 100] or capacity.get("online_targets") != [50, 100]:
        errors.append("Capacity must preserve both 50 and 100 online/active targets")
    if capacity.get("coverage_fraction") != 0.95 or capacity.get("hold_seconds") != 600 or capacity.get("continuous_seconds") != 120:
        errors.append("Capacity acceptance thresholds differ from the frozen initial contract")
    experiment = profiles.get("profiles", {}).get("EXPERIMENT", {})
    blocks = experiment.get("seed_blocks", [])
    if len(blocks) != 3:
        errors.append("Experiment requires three disjoint seed blocks")
    seen = set()
    for block in blocks:
        start, count = block.get("start"), block.get("count")
        if type(start) is not int or type(count) is not int or count < 1000:
            errors.append("Seed blocks require explicit integer start and count >= 1000")
            continue
        seeds = set(range(start, start + count))
        if seen & seeds:
            errors.append("Experiment seed blocks overlap")
        seen |= seeds
    if profiles.get("execution_boundary") != "local_loopback_and_disposable_database":
        errors.append("Local scope must not silently authorize a remote target")
    return errors


def config_bundle_identity(payload):
    try:
        from export_client_catalog import fields
    except ModuleNotFoundError:
        from tools.export_client_catalog import fields
    bundle = fields(payload)
    if set(bundle) != {1, 2, 3} or len(bundle[1]) != 1 or len(bundle[2]) != 1 or len(bundle[2][0]) != 32:
        raise ValueError("Invalid config bundle identity")

    def varint(number):
        result = bytearray()
        while number >= 128:
            result.append((number & 127) | 128)
            number >>= 7
        result.append(number)
        return bytes(result)

    # ConfigCompiler hashes EncodeBundle(version, [], tables), excluding field 2.
    canonical = b"".join(varint((tag << 3) | 2) + varint(len(value)) + value
                         for tag in (1, 3) for value in bundle[tag])
    content_hash = hashlib.sha256(canonical).hexdigest()
    if bundle[2][0].hex() != content_hash:
        raise ValueError("Config bundle content does not match its embedded hash")
    return {"version": bundle[1][0].decode("utf-8"), "content_sha256": content_hash}


def config_identity(root=ROOT):
    server = root / "server/config/generated"
    client = root / "client/data/generated"
    paths = [server / "fantasycard.config.bytes", client / "fantasycard.config.bytes"]
    hashes = [digest(path) for path in paths]
    declarations = [(folder / "fantasycard.config.sha256").read_text().strip().lower()
                    for folder in (server, client)]
    versions = [(folder / "fantasycard.config.version.txt").read_text().strip()
                for folder in (server, client)]
    catalog = read(root / "client/data/catalog.json")
    identities = [config_bundle_identity(path.read_bytes()) for path in paths]
    if len(set(hashes)) != 1 or len(set(declarations + [row["content_sha256"] for row in identities])) != 1:
        raise ValueError("Config content or declared hash differs between server and client")
    if not versions[0] or len(set(versions + [str(catalog.get("version"))] + [row["version"] for row in identities])) != 1:
        raise ValueError("Config versions differ between server, client and catalog")
    return {"source_sha256": digest(root / "config/FantasyCard_Config.xlsx"),
            "bytes_sha256": hashes[0], "content_sha256": declarations[0], "version": versions[0],
            "catalog_sha256": digest(root / "client/data/catalog.json"),
            "source_export_revalidated": False,
            "source_export_reason": "Source and published packages are frozen; isolated regeneration is required at S3/S4."}


def source_files():
    files = git("ls-files", "client", "server", "protocol", "tools", "config", ".github/workflows").splitlines()
    allowed = {".py", ".gd", ".tscn", ".cs", ".csproj", ".slnx", ".proto", ".json", ".yml", ".ps1", ".sql", ".bytes", ".xlsx", ".godot", ".txt", ".sha256"}
    excluded = {"bin", "obj", "artifacts", ".godot", "local-backups", "__pycache__"}
    return [ROOT / file for file in files if Path(file).suffix in allowed
            and not excluded.intersection(Path(file).parts)
            and not file.startswith("tools/engine-local/")]


def historical_blockers(plan, profiles):
    history = read(ROOT / HISTORY)
    known = {task["id"] for package in plan["packages"] for task in package["subtasks"]}
    result = {}
    replacement = profiles.get("history_resolution", {})
    replacement_tasks = set(replacement.get("replacement_tasks", []))
    if replacement_tasks and (replacement.get("original_evidence_state") != "DeletedAndUnrecoverable"
                              or replacement.get("runtime_acceptance") is not False
                              or not replacement.get("user_instruction") or not replacement.get("interpretation")):
        raise ValueError("Historical replacement must carry explicit user instruction and preserve non-acceptance")
    for task in history["tasks"]:
        if task.get("state") != "Blocked" or task["task_id"] not in known:
            continue
        if task["task_id"] in replacement_tasks:
            continue
        item = dict(task["observation"])
        item.update(stage="S0", recorded_runtime_stage=task["observation"].get("stage"),
                    owner="MAIN", source=HISTORY, historical_only=True,
                    next_action="Locate and hash original per-client raw and launch manifests; continue independent current fixtures.")
        result[task["task_id"]] = item
    return result


def freeze(output, handbook=None, config_export=None):
    try:
        import pr13_plan
    except ModuleNotFoundError:
        from tools import pr13_plan
    plan = read(ROOT / PLAN)
    errors = pr13_plan.validate(plan)
    profiles = read(ROOT / PROFILE)
    errors.extend(validate_profiles(profiles))
    if errors:
        raise ValueError("\n".join(errors))
    if output.exists():
        raise ValueError("Refusing to overwrite a frozen stage; use a new output directory")
    config = config_identity()
    if config_export:
        exported = []
        for folder in ("server", "client"):
            path = config_export / folder / "fantasycard.config.bytes"
            if digest(path) != config["bytes_sha256"]:
                raise ValueError("Source re-export differs from frozen published config")
            exported.append(file_record(path))
        config.update(source_export_revalidated=True,
                      source_export_reason="Isolated current workbook export matches both published packages byte for byte.",
                      isolated_export_files=exported)
    source_sha = git("rev-parse", "HEAD")
    source_manifest = [file_record(path) for path in source_files()]
    inputs = [file_record(ROOT / path) for path in (PLAN, PROFILE, *QUEUES, HISTORY)]
    user_handbook = None
    if handbook:
        supplied = handbook.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
        canonical = (ROOT / PLAN).with_suffix(".md").read_text(encoding="utf-8").strip()
        if supplied != canonical:
            raise ValueError("User handbook differs from canonical plan; resolve scope before freezing")
        user_handbook = {"sha256": digest(handbook), "canonical_content_matches": True}
    blockers = historical_blockers(plan, profiles)
    if not config["source_export_revalidated"]:
        blockers["PR13-B12.1"] = {
            "task_id": "PR13-B12.1", "stage": "S0", "owner": "MAIN", "historical_only": False,
            "reason": "Source workbook regeneration has not been compared with the published packages",
            "missing_input_or_environment": "Isolated current source export", "affected_gates": ["G0", "G1", "G5"],
            "unblock_condition": "Run the existing exporter into an isolated directory and verify exact byte parity",
            "next_action": "Repeat S0 with --config-export and the actual isolated output",
        }
    ownership = {scope: {"writer": "MAIN", "package_refs": []}
                 for package in plan["packages"] for scope in package["write_scope"]}
    for package in plan["packages"]:
        for scope in set(package["write_scope"]):
            ownership[scope]["package_refs"].append(package["id"])
    reports = []
    for package in plan["packages"]:
        for task in package["subtasks"]:
            selected = {name: profiles["profiles"][name] for name in task["profiles"]}
            missing = {
                "effective_room_policy": "No runtime started at S0; default policy source is pinned in source manifest.",
                "runtime_image_digest": "Local process profile; container image is not selected. Assemblies are hashed after build.",
                "sample_population": "S0 registers budgets; no runtime sample has been observed.",
                "cutoff_monotonic": "No runtime cutoff exists before execution.",
                "window_or_drain_or_final": "No runtime window exists before execution.",
                "asset_and_route_postconditions": "Measured at S4/S5, never inferred from source.",
            }
            report = {field: None for field in plan["evidence_contract"]["report_fields"]}
            report.update(task_id=task["id"], stage="S0", integration_sha=source_sha,
                          config_source_hash=config["source_sha256"], config_bytes_hash=config["bytes_sha256"],
                          profile_hash=canonical_hash(selected), algorithm_version="pr13-local-stage-contract-v1",
                          case_ids=[case["id"] for case in task["test_cases"]],
                          expected={"runtime_cases": task["test_cases"], "pass_criteria": task["pass_criteria"]},
                          actual={"scope_frozen": True, "runtime_executed": False,
                                  "profile_budgets": selected, "inputs": task["inputs"],
                                  "dependencies": task["requires_before_integration"],
                                  "dependency_phase": "S4/S5 integration only", "writer": "MAIN",
                                  "write_scope": package["write_scope"], "task_contract_hash": canonical_hash(task)},
                          status="Blocked" if task["id"] in blockers else "ReadyForAcceptance",
                          commands=["python tools/pr13_plan.py --check", "python tools/pr13_stages.py check --input <S0 directory>"],
                          tool_versions={"python": sys.version.split()[0], "dotnet_required": "10.0.400"},
                          exit_codes=[], skip_reasons=[], reviewer="MAIN", rollback=task["rollback"],
                          remaining_blockers=[blockers[task["id"]]] if task["id"] in blockers else [],
                          missing_reasons=missing, artifact_manifest="manifest.json",
                          accepted_by=None, stage_states={f"S{i}": "Queued" for i in range(1, 7)})
            reports.append(report)
    output.mkdir(parents=True)
    for report in reports:
        destination = output / report["task_id"]
        destination.mkdir()
        write(destination / "report.json", report)
    write(output / "profiles.json", profiles)
    write(output / "ownership.json", ownership)
    write(output / "source-manifest.json", {"source_sha": source_sha, "source_tree": git("rev-parse", "HEAD^{tree}"),
                                           "files": source_manifest, "files_hash": canonical_hash(source_manifest)})
    write(output / "input-manifest.json", {"files": inputs, "user_handbook": user_handbook, "config": config})
    summary = {"schema_version": 1, "stage": "S0", "kind": "stage_input_freeze_not_runtime_acceptance",
               "date": "2026-10-08", "created_utc": datetime.now(timezone.utc).isoformat(),
               "integration_sha": source_sha, "release_base": git("rev-parse", "origin/release"),
               "pr13_head": git("rev-parse", "origin/fix/gameplay-load-evidence-20260929"),
               "plan_hash": digest(ROOT / PLAN), "profile_hash": canonical_hash(profiles),
               "config": config, "execution_boundary": profiles["execution_boundary"],
               "counts": {"packages": 33, "tasks": len(reports), "cases": sum(len(x["case_ids"]) for x in reports),
                          "states": dict(Counter(x["status"] for x in reports)), "runtime_accepted": 0},
               "all_s0_ready": not blockers, "runtime_acceptance": False,
               "blocking_inputs": list(blockers.values()),
               "scope_decisions": {"history_resolution": profiles.get("history_resolution"),
                                   "human_experience_decision": profiles.get("human_experience_decision")},
               "gate_coverage": {gate["id"]: [task["id"] for package in plan["packages"]
                                             for task in package["subtasks"] if gate["id"] in task["gate_refs"]]
                                 for gate in plan["gates"]},
               "next_stage": "S1 for tasks with frozen inputs; history attribution remains Blocked"}
    write(output / "summary.json", summary)
    write(output / "manifest.json", {"files": [file_record(path, output) for path in sorted(output.rglob("*")) if path.is_file()]})
    return summary


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def check(output, verify_current=True):
    summary = read(output / "summary.json")
    errors = []
    for record in read(output / "manifest.json")["files"]:
        path = (output / record["path"]).resolve()
        if not path.is_relative_to(output.resolve()) or not path.is_file():
            errors.append("Missing or escaped artifact: " + record["path"])
        elif file_record(path, output) != record:
            errors.append("Artifact hash mismatch: " + record["path"])
    profiles = read(output / "profiles.json")
    errors.extend(validate_profiles(profiles))
    if canonical_hash(profiles) != summary["profile_hash"]:
        errors.append("Profile hash mismatch")
    plan = read(ROOT / PLAN)
    if digest(ROOT / PLAN) != summary["plan_hash"]:
        errors.append("Plan has changed since S0")
    if verify_current:
        for record in read(output / "source-manifest.json")["files"] + read(output / "input-manifest.json")["files"]:
            path = ROOT / record["path"]
            if not path.is_file() or file_record(path) != record:
                errors.append("Frozen input changed: " + record["path"])
    tasks = {task["id"]: task for package in plan["packages"] for task in package["subtasks"]}
    reports = [read(path) for path in sorted(output.glob("*/report.json"))]
    if set(row["task_id"] for row in reports) != set(tasks) or len(reports) != 132:
        errors.append("Stage must cover all 132 tasks exactly once")
    for report in reports:
        task = tasks.get(report["task_id"])
        if not task:
            continue
        if set(plan["evidence_contract"]["report_fields"]) - set(report):
            errors.append(report["task_id"] + ": missing report fields")
        if report["actual"]["task_contract_hash"] != canonical_hash(task):
            errors.append(report["task_id"] + ": task contract changed")
        if report["accepted_by"] is not None or report["status"] not in {"ReadyForAcceptance", "Blocked"}:
            errors.append(report["task_id"] + ": S0 cannot claim runtime acceptance")
        selected = {name: profiles["profiles"][name] for name in task["profiles"]}
        if report["profile_hash"] != canonical_hash(selected):
            errors.append(report["task_id"] + ": task profile mismatch")
        for key in plan["evidence_contract"]["report_fields"]:
            if report[key] is None and key not in report["missing_reasons"]:
                errors.append(report["task_id"] + ": unexplained null " + key)
    coverage = {gate["id"]: [task["id"] for package in plan["packages"] for task in package["subtasks"]
                            if gate["id"] in task["gate_refs"]] for gate in plan["gates"]}
    if summary["gate_coverage"] != coverage:
        errors.append("Gate coverage must use all gate_refs, not only critical tasks")
    if errors:
        raise ValueError("\n".join(errors))
    return summary["counts"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    freeze_mode = modes.add_parser("freeze")
    freeze_mode.add_argument("--output", required=True, type=Path)
    freeze_mode.add_argument("--handbook", type=Path)
    freeze_mode.add_argument("--config-export", type=Path, help="Actual isolated workbook export directory containing server/ and client/")
    check_mode = modes.add_parser("check")
    check_mode.add_argument("--input", required=True, type=Path)
    check_mode.add_argument("--historical", action="store_true", help="Verify artifact integrity without claiming current source parity")
    args = parser.parse_args()
    try:
        result = freeze(args.output, args.handbook, args.config_export) if args.mode == "freeze" else check(args.input, not args.historical)
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result.get("counts", result), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
