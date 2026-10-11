#!/usr/bin/env python3
"""Reproduce the PR13 B08.4 runtime on the Tencent acceptance host.

Run prepare-runtime and build-runtime separately. For a systemd build, set
PR13_RECOVERY_SYSTEMD_UNIT to the exact pr13-<attempt> unit name so only that
currently running driver is exempt from the active-job guard. Neither phase
starts an experiment.
Preparation restores the declared 372-file Git source subset, not the former
2068-file execution directory. The complete NuGet cache is mounted read-only.
Success requires the original eight runtime hashes and exactly 56 passing
regressions. Existing attempts, starts and results are never overwritten.

Example (cloud only)::

    python3 cap_runtime_recovery.py prepare-runtime --attempt cap-runtime-recovery-r2-20261011
    python3 cap_runtime_recovery.py build-runtime --attempt cap-runtime-recovery-r2-20261011
    python3 cap_runtime_recovery.py status --attempt cap-runtime-recovery-r2-20261011

Failed scratch and original metadata remain available for evidence transfer.
This tool does not grant MAIN acceptance or recover missing experiment raw data.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


BASE = Path("/home/ubuntu/pr13-acceptance-20261009")
GIT = Path("/opt/fantasycard-github")
SOURCE_SHA = "b0423bfe6fedc3f034ba12c8400df5ebb8713f32"
IMAGE = "sha256:6ea92944e8779a5bb6e5c40faca53a40a1b02b5a0dcd47fff0815ba9cfbded1f"
SDK = "10.0.400"
ORIGINAL_INPUTS = BASE / "evidence/cap-experiment-pilot-r4/inputs.json"
ORIGINAL_RUNTIME = BASE / "evidence/cap-experiment-full/runtime-hashes.json"
SOURCE_COUNT = 372
ORIGINAL_COUNT = 2068
ROOT_RESERVE = 32 * 1024**2
DIAGNOSTIC_BUDGET = 24 * 1024**2
FINAL_METADATA_RESERVE = 16 * 1024**2
MEMORY_FLOOR = 500000000
STARTUP_RESERVE = (950 + 512) * 1024**2
EXCLUDED_PARTS = {".packages", ".artifacts", ".dotnet", "artifacts", "bin", "obj"}
DOMAIN_FILTER = (
    "FullyQualifiedName~CapEffectiveContractTests|"
    "FullyQualifiedName~CurrentNumericalBaselineTests|"
    "FullyQualifiedName~EquipmentCombatRulesTests"
)
RUNTIME_HASHES = {
    "FantasyCard.Numerics.pdb": "c54f071eb83687f4c0e56e555445df55db10d5bf861b264a47397ac628d1cbbb",
    "FantasyCard.Numerics.dll": "cb9d50683a13957eeeb442824d26b06c209356e61a0289c2dc9fe9988a68c0df",
    "FantasyCard.Numerics.runtimeconfig.json": "6eaff27a497447817e02c096da9afb530324590c005c1c011cd87bf2669f9dfd",
    "FantasyCard.Numerics.deps.json": "3f2ef034feee6d02a18bce64a2a55c898c76b29bee8748fc912ca781f8e6dc92",
    "FantasyCard.Numerics": "31792193aae65a9a253370df35bd434f0c6cf5616e269f088c4a1cd5df728616",
    "FantasyCard.Domain.pdb": "986c5b1be4366ef9e91a70c671a210d3bd2b53f72fcb53be7e1088433a80a7e5",
    "FantasyCard.Domain.dll": "6e8650494db8e95dbf6a47af0eaf880a119bc36f348a9aaa9cd9437ca969249a",
    "FantasyCard.Domain.deps.json": "84049a6e2e274b4fd62887cce60fbf77aeeee5336c87f7d5150d602fb887a553",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    # Exclusive creation also rejects concurrent or previously ended attempts.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, check=True, timeout=timeout)


def docker(*args):
    return command(["sudo", "-n", "docker", *args])


def paths(attempt):
    require(re.fullmatch(r"cap-runtime-recovery-r[1-9][0-9]*-[0-9]{8}", attempt),
            "attempt must have the form cap-runtime-recovery-rN-YYYYMMDD")
    evidence = BASE / "evidence" / attempt
    work = BASE / "work" / attempt
    scratch = Path("/dev/shm") / ("pr13-" + attempt)
    return evidence, work, work / "source", scratch


def host_only():
    require(os.name != "nt" and sys.platform.startswith("linux"), "cloud Linux host only")
    require(BASE.is_dir() and GIT.is_dir(), "expected Tencent acceptance paths absent")


def guard(root_bytes=ROOT_RESERVE, memory_bytes=0, scratch_bytes=0):
    stats = os.statvfs(BASE)
    require(stats.f_blocks > 0 and stats.f_bavail / stats.f_blocks >= .15,
            "root disk is below the frozen 15 percent floor")
    remaining = (stats.f_bavail - .15 * stats.f_blocks) * stats.f_frsize
    require(remaining >= root_bytes, "insufficient root space above the 15 percent floor")
    meminfo = Path("/proc/meminfo").read_text().splitlines()
    available = int(next(row.split()[1] for row in meminfo if row.startswith("MemAvailable:"))) * 1024
    require(available >= MEMORY_FLOOR + memory_bytes, "insufficient memory above 500 MB floor")
    if scratch_bytes:
        stats = os.statvfs("/dev/shm")
        require(stats.f_bavail * stats.f_frsize >= scratch_bytes, "insufficient shared-memory scratch")


def health():
    with urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=10) as response:
        require(response.status == 200, "production readiness failed")


def no_cap_job(container_name):
    units = command(["systemctl", "list-units", "--state=running", "--no-legend", "--plain", "pr13-cap-*"]).stdout.decode()
    # When invoked within its own unit, this driver is the sole permitted unit.
    names = [row.split()[0].removesuffix(".service") for row in units.splitlines() if row.split()]
    own_unit = os.environ.get("PR13_RECOVERY_SYSTEMD_UNIT", "")
    require(not any(name != own_unit for name in names), "another active cap job must finish first")
    if own_unit:
        require(own_unit == container_name, "own systemd unit must equal the attempt container name")
    names = docker("ps", "--format", "{{.Names}}").stdout.decode().splitlines()
    require(not any(name.startswith("pr13-cap-") for name in names), "active cap container")
    names = docker("ps", "-a", "--format", "{{.Names}}").stdout.decode().splitlines()
    require(container_name not in names, "existing attempt container must not be restarted")


def source_contract():
    raw = ORIGINAL_INPUTS.read_bytes()
    original = json.loads(raw)
    require(original.get("source_sha") == SOURCE_SHA, "original source revision mismatch")
    all_hashes = original.get("source_hashes", {})
    require(len(all_hashes) == ORIGINAL_COUNT, "original input count mismatch")
    selected = {}
    for name, value in all_hashes.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and ".." not in relative.parts and "\\" not in name,
                "unsafe original input path")
        require(re.fullmatch(r"[0-9a-f]{64}", value), "invalid original input hash")
        if not (set(relative.parts) & EXCLUDED_PARTS):
            selected[name] = value
    require(len(selected) == SOURCE_COUNT, "declared 372-file recovery subset changed")
    require("tools/pr13_cap_effective_experiment.py" in selected, "experiment verifier missing")
    require("server/tools/FantasyCard.Numerics/CapEffectiveExperiment.cs" in selected,
            "native experiment entry missing")
    require(json.loads(ORIGINAL_RUNTIME.read_text()) == RUNTIME_HASHES,
            "original eight runtime hashes differ from the frozen contract")
    return raw, selected


def prepare_runtime(attempt):
    host_only()
    evidence, work, source, _ = paths(attempt)
    name = "pr13-" + attempt
    no_cap_job(name)
    require(not evidence.exists() and not work.exists(), "existing attempt cannot be overwritten")
    raw, hashes = source_contract()
    require((BASE / "cache/nuget").is_dir(), "complete package cache missing")
    rows = command(["git", "-C", str(GIT), "ls-tree", "-r", "-l", SOURCE_SHA,
                    "--", "server", "tools/pr13_cap_effective_experiment.py"]).stdout.decode()
    entries = {}
    for row in rows.splitlines():
        fields, filename = row.split("\t", 1)
        mode, kind, oid, size = fields.split()
        if filename in hashes:
            require(kind == "blob" and mode in ("100644", "100755"), "unsupported Git source entry")
            entries[filename] = {"oid": oid, "bytes": int(size), "executable": mode == "100755"}
    require(set(entries) == set(hashes), "Git tree does not contain the exact declared subset")
    new_bytes = sum(entry["bytes"] for entry in entries.values())
    budget = new_bytes + len(hashes) * 4096 + ROOT_RESERVE
    guard(root_bytes=budget)
    health()
    evidence.mkdir()
    work.mkdir()
    source.mkdir()
    result = {
        "ok": False, "attempt": attempt, "source_sha": SOURCE_SHA, "image_sha": IMAGE,
        "original_input_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "original_input_files": ORIGINAL_COUNT, "recovered_source_subset_files": SOURCE_COUNT,
        "excluded_old_cache_and_build_output_files": ORIGINAL_COUNT - SOURCE_COUNT,
        "original_execution_directory_restored": False, "new_source_logical_bytes": new_bytes,
        "root_disk_reserve_bytes": budget, "complete_package_cache_mounted_readonly": True,
        "compilation_dispatched": False, "large_experiment_dispatched": False,
        "original_results_overwritten": False, "main_acceptance_granted": False,
    }
    try:
        for filename, entry in sorted(entries.items()):
            destination = source / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = command(["git", "-C", str(GIT), "cat-file", "blob", entry["oid"]]).stdout
            require(len(content) == entry["bytes"] and hashlib.sha256(content).hexdigest() == hashes[filename],
                    "Git blob does not match the original input hash: " + filename)
            with destination.open("xb") as stream:
                stream.write(content)
            if entry["executable"]:
                destination.chmod(0o755)
            require(digest(destination) == hashes[filename], "restored source hash mismatch")
        guard()
        write_json(evidence / "inputs.json", {
            **result, "source_hashes": hashes, "readonly_complete_package_cache": str(BASE / "cache/nuget"),
            "restore_package_path": "/cache/nuget",
        })
        write_json(evidence / "original-inputs-reference.json", {
            "source": str(ORIGINAL_INPUTS), "sha256": hashlib.sha256(raw).hexdigest(),
            "source_sha": SOURCE_SHA, "source_files": ORIGINAL_COUNT, "original_metadata_unchanged": True,
        })
        result.update(ok=True, recovered_source_subset_hashes_match_original_and_git=True,
                      persistent_source=str(source), proposed_systemd_unit=name,
                      rebuilt_hashes_must_be_identical_to_original=True,
                      missing_original_raw_unit="Mage-E1-Water-L5-B0",
                      missing_unit_requires_separate_named_recovery_attempt=True)
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
        raise
    finally:
        write_json(evidence / "prepare.json", result)
    return result


def container_build():
    """Only the fixed image runs this internal phase; logs go to its /ram bind."""
    require(os.environ.get("PR13_RECOVERY_CONTAINER") == "1", "internal container phase only")
    ram = Path("/ram")
    version = subprocess.check_output(["dotnet", "--version"], text=True).strip()
    require(version == SDK, "exact .NET SDK required")
    write_json(ram / "sdk.json", {"dotnet_version": version})
    stages = [
        ("compile", ["dotnet", "build", "/work/server/tools/FantasyCard.Numerics/FantasyCard.Numerics.csproj",
                     "-c", "Release", "-o", "/ram/runtime", "--ignore-failed-sources", "-p:NuGetAudit=false",
                     "-p:RestorePackagesPath=/cache/nuget"], 240),
        ("help", ["dotnet", "/ram/runtime/FantasyCard.Numerics.dll", "--cap-effective-experiment", "--help"], 30),
        ("domain", ["dotnet", "test", "/work/server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj",
                    "-c", "Release", "--filter", DOMAIN_FILTER, "--logger", "trx;LogFileName=cap-runtime-recovery.trx",
                    "--results-directory", "/ram/test-results", "-p:RestoreIgnoreFailedSources=true",
                    "-p:NuGetAudit=false", "-p:RestorePackagesPath=/cache/nuget"], 300),
    ]
    status = {}
    for phase, args, timeout in stages:
        with (ram / (phase + ".log")).open("x") as stream:
            completed = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        status[phase] = {"exit_code": completed.returncode}
        write_json(ram / (phase + "-result.json"), status[phase])
        if completed.returncode:
            return completed.returncode
    write_json(ram / "inner-result.json", status)
    return 0


def owned_state(cid, owner):
    state = json.loads(docker("inspect", cid).stdout)[0]
    require(state["Id"] == cid and state["Config"]["Labels"].get("codex.owner") == owner,
            "container ownership mismatch")
    return state


def build_runtime(attempt):
    host_only()
    evidence, work, source, scratch = paths(attempt)
    name = "pr13-" + attempt
    require((evidence / "prepare.json").is_file(), "run prepare-runtime first")
    require(json.loads((evidence / "prepare.json").read_text()).get("ok") is True,
            "preparation did not succeed")
    for target in (evidence / "build-result.json", evidence / "build-started.json", work / "runtime", scratch):
        require(not target.exists(), "existing build state cannot be restarted: " + str(target))
    no_cap_job(name)
    original_raw, hashes = source_contract()
    meta = json.loads((evidence / "inputs.json").read_text())
    require(meta["source_hashes"] == hashes and meta["source_sha"] == SOURCE_SHA,
            "prepared source contract mismatch")
    require(meta["original_input_manifest_sha256"] == hashlib.sha256(original_raw).hexdigest(),
            "original input manifest changed")
    require(all(digest(source / path) == expected for path, expected in hashes.items()),
            "prepared source inputs changed")
    guard(memory_bytes=STARTUP_RESERVE, scratch_bytes=256 * 1024**2)
    health()
    write_json(evidence / "build-started.json", {"attempt": attempt, "source_sha": SOURCE_SHA,
                                               "started_unix": time.time(), "image_sha": IMAGE})
    scratch.mkdir()
    mounted_source = scratch / "source"
    mounted_source.mkdir()
    cid = None
    owner = name
    result = {"ok": False, "attempt": attempt, "source_sha": SOURCE_SHA, "image_sha": IMAGE,
              "original_runtime_hashes": RUNTIME_HASHES, "main_acceptance_granted": False,
              "large_experiment_dispatched": False, "original_results_overwritten": False,
              "runtime_revalidation_required_before_full_experiment": True}
    try:
        for path in hashes:
            destination = mounted_source / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, destination)
        write_json(evidence / "build-source-subset.json", {
            "source_sha": SOURCE_SHA, "mounted_code_files": sorted(hashes), "source_files": SOURCE_COUNT,
            "excluded_preexisting_build_and_package_cache": True,
        })
        shutil.copyfile(Path(__file__), scratch / "runner.py")
        cid = docker("create", "--name", name, "--label", "codex.owner=" + owner,
                     "--memory", "950m", "--cpus", "1", "--network", "none", "--user", "1000:1000",
                     "-e", "PR13_RECOVERY_CONTAINER=1", "-v", str(mounted_source) + ":/work",
                     "-v", str(scratch) + ":/ram", "-v", str(BASE / "cache") + ":/cache:ro",
                     IMAGE, "python3", "/ram/runner.py", "_container-build").stdout.decode().strip()
        require(re.fullmatch(r"[0-9a-f]{64}", cid), "invalid created container identity")
        docker("start", cid)
        deadline = time.monotonic() + 700
        while True:
            state = owned_state(cid, owner)
            if not state["State"]["Running"]:
                break
            guard()
            health()
            require(time.monotonic() < deadline, "native recovery build deadline exceeded")
            time.sleep(5)
        result.update(exit_code=state["State"]["ExitCode"], oom_killed=state["State"]["OOMKilled"])
        require(result["exit_code"] == 0 and not result["oom_killed"], "native build or regression failed")
        runtime = scratch / "runtime"
        rebuilt = {path.name: digest(path) for path in runtime.iterdir() if path.is_file()}
        result["rebuilt_runtime_hashes"] = rebuilt
        result["runtime_hashes_identical_to_original"] = rebuilt == RUNTIME_HASHES
        result["new_pilot_required_due_to_runtime_hash_difference"] = rebuilt != RUNTIME_HASHES
        result["runtime_hash_differences"] = {
            path: {"original": RUNTIME_HASHES.get(path), "rebuilt": rebuilt.get(path)}
            for path in sorted(set(RUNTIME_HASHES) | set(rebuilt)) if RUNTIME_HASHES.get(path) != rebuilt.get(path)
        }
        require(rebuilt == RUNTIME_HASHES, "runtime must match all eight original hashes exactly")
        require(sum(path.stat().st_size for path in runtime.iterdir() if path.is_file()) <= 8 * 1024**2,
                "runtime exceeds the persistent size budget")
        trx = scratch / "test-results/cap-runtime-recovery.trx"
        counter = ET.parse(trx).find(".//{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters")
        require(counter is not None, "regression TRX counters missing")
        counters = {key: int(value) for key, value in counter.attrib.items()}
        result["domain_regression_counters"] = counters
        exact = counters.get("total") == 56 and counters.get("passed") == 56 and counters.get("failed") == 0
        result["domain_regression_exact_56_passed"] = exact
        require(exact, "exactly 56 regressions must pass without failures or skips")
        unchanged = all(digest(source / path) == expected for path, expected in hashes.items())
        result["source_inputs_unchanged"] = unchanged
        require(unchanged, "persistent original source inputs changed")
        guard()
        (work / "runtime").mkdir()
        for path in runtime.iterdir():
            if path.is_file():
                shutil.copyfile(path, work / "runtime" / path.name)
        require({path.name: digest(path) for path in (work / "runtime").iterdir()} == RUNTIME_HASHES,
                "persisted runtime hash mismatch")
        result.update(ok=True, rebuilt_runtime_persisted=True, persistent_runtime=str(work / "runtime"),
                      runtime_revalidation_required_before_full_experiment=False)
    except Exception as error:
        result.update(error=type(error).__name__, detail=str(error))
    finally:
        result["finalization_completed"] = False
        try:
            content = b""
            if cid:
                state = owned_state(cid, owner)
                if state["State"]["Running"]:
                    docker("stop", "--time", "5", cid)
                require(not owned_state(cid, owner)["State"]["Running"], "owned container did not stop")
                result["owned_container_not_running"] = True
                logs = docker("logs", cid)
                content = logs.stdout + logs.stderr
                require(len(content) <= 4 * 1024**2, "container log exceeds evidence budget; preserved in Docker")
            names = ["compile.log", "help.log", "domain.log", "sdk.json", "inner-result.json",
                     "compile-result.json", "help-result.json", "domain-result.json",
                     "test-results/cap-runtime-recovery.trx"]
            diagnostics = []
            for filename in names:
                path = scratch / filename
                if path.exists():
                    require(path.stat().st_size <= 4 * 1024**2, "diagnostic exceeds persistent budget: " + filename)
                    destination = evidence / path.name
                    require(not destination.exists(), "existing diagnostic must not be overwritten")
                    diagnostics.append((path, destination))
            require(not cid or not (evidence / "container.log").exists(), "existing container log cannot be overwritten")
            diagnostic_bytes = len(content) + sum(path.stat().st_size for path, _ in diagnostics)
            result["diagnostic_aggregate_bytes"] = diagnostic_bytes
            require(diagnostic_bytes <= DIAGNOSTIC_BUDGET,
                    "aggregate diagnostics exceed 24 MiB; scratch and stopped container logs retained")
            file_overhead = (len(diagnostics) + bool(cid)) * 4096
            needed = diagnostic_bytes + file_overhead + 65536 + 4096
            # Check the complete persistent write before writing any diagnostic.
            # A further 16 MiB remains above the disk floor for result metadata.
            guard(root_bytes=needed + FINAL_METADATA_RESERVE)
            if cid:
                with (evidence / "container.log").open("xb") as stream:
                    stream.write(content)
            for path, destination in diagnostics:
                shutil.copyfile(path, destination)
            if cid:
                docker("rm", "-v", cid)
                result["owned_container_removed"] = True
            result["finalization_completed"] = True
        except Exception as error:
            result.update(ok=False, finalization_error=type(error).__name__, finalization_detail=str(error))
            if cid:
                result["owned_container_retained"] = not result.get("owned_container_removed", False)
        result["scratch_preserved"] = str(scratch)
        try:
            metadata_bytes = len(json.dumps(result, indent=2, sort_keys=True).encode("utf-8")) + 1
            require(metadata_bytes <= 65536, "result metadata exceeds 64 KiB budget")
            guard(root_bytes=metadata_bytes + 4096 + FINAL_METADATA_RESERVE)
            write_json(evidence / "build-result.json", result)
        except Exception as error:
            result.update(ok=False, finalization_completed=False, result_metadata_persisted=False,
                          result_metadata_error=type(error).__name__, result_metadata_detail=str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("phase", choices=("prepare-runtime", "build-runtime", "status", "_container-build"))
    parser.add_argument("--attempt", help="fresh cap-runtime-recovery-rN-YYYYMMDD identity")
    args = parser.parse_args()
    if args.phase == "_container-build":
        return container_build()
    if not args.attempt:
        parser.error("--attempt is required")
    if args.phase == "prepare-runtime":
        result = prepare_runtime(args.attempt)
    elif args.phase == "build-runtime":
        result = build_runtime(args.attempt)
    else:
        host_only()
        evidence, _, _, _ = paths(args.attempt)
        result = {"attempt": args.attempt}
        for name in ("prepare.json", "build-started.json", "build-result.json"):
            path = evidence / name
            result[name] = json.loads(path.read_text()) if path.is_file() else None
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("ok") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
