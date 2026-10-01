"""Materialize one declared commit for an isolated source-internal build.

This preparation performs no database access and executes no runtime tests.
Historical evidence and the input repository remain read-only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

GENERATED = {"bin", "obj", ".godot", ".packages", "__pycache__"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    source = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", args.source + "^{commit}"], text=True
    ).strip()
    if len(args.source) != 40 or source != args.source:
        parser.error("Use the exact full 40-character commit SHA from the receipt.")
    args.output.mkdir(parents=True, exist_ok=False)
    excluded = []
    process = subprocess.Popen(
        ["git", "-C", str(repo), "archive", source], stdout=subprocess.PIPE
    )
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                if any(part in GENERATED for part in Path(member.name).parts):
                    if member.isfile():
                        excluded.append(member.name)
                    continue
                archive.extract(member, args.output, filter="data")
    finally:
        process.stdout.close()
    if process.wait() != 0:
        raise RuntimeError("Fixed source archive failed; retain partial output for diagnosis.")
    files = []
    for path in sorted(args.output.rglob("*")):
        if path.is_file():
            content = path.read_bytes()
            files.append({"path": path.relative_to(args.output).as_posix(),
                          "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    proof = {"source_sha": source, "source_files": files,
             "excluded_generated_files": excluded, "tests_executed": 0,
             "source_git_dirty": None,
             "missing_reasons": {"source_git_dirty": "Exact git archive with generated caches excluded; no .git in isolated source."},
             "build_output_rule": "Build only inside this actual source; never reuse prior bin/obj."}
    (args.output / "FIXED_SOURCE.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({"source_sha": source, "source_files": len(files),
                      "excluded_generated_files": len(excluded), "tests_executed": 0}))


if __name__ == "__main__":
    main()
