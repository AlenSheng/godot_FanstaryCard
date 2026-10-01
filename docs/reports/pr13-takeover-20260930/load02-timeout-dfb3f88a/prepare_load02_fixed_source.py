"""Materialize only the declared fixed-source files for isolated replay.

No database, deployment, upload, or input-repository mutation is performed.
The result is an explicitly partial source copy, not a clean full checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("source-dfb3f88a73ef-fixed.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    spec = json.loads(args.manifest.read_text())
    source = spec["integration_sha"]
    if len(source) != 40 or git(repo, "rev-parse", source + "^{commit}").decode().strip() != source:
        parser.error("The declared exact commit must exist in the authorized local repository.")
    args.output.mkdir(parents=True, exist_ok=False)
    checked = []
    for entry in spec["files"]:
        rel = PurePosixPath(entry["path"])
        if rel.is_absolute() or ".." in rel.parts or ".git" in rel.parts:
            raise ValueError("Invalid source manifest path")
        blob = git(repo, "rev-parse", source + ":" + entry["path"]).decode().strip()
        content = git(repo, "cat-file", "blob", blob)
        if blob != entry["git_blob"] or len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("Fixed source byte mismatch: " + entry["path"])
        path = args.output / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        checked.append(entry)
    # Original Python tools inspect HEAD. Expose actual objects read-only through
    # Git's native alternate mechanism without copying history or credentials.
    subprocess.run(["git", "init", "--quiet", "--initial-branch=evidence", str(args.output)], check=True)
    common = Path(git(repo, "rev-parse", "--git-common-dir").decode().strip())
    if not common.is_absolute():
        common = repo / common
    objects = (common / "objects").resolve()
    info = args.output / ".git/objects/info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "alternates").write_text(str(objects) + "\n")
    (args.output / ".git/HEAD").write_text(source + "\n")
    git(args.output, "read-tree", source)
    if git(args.output, "rev-parse", "HEAD").decode().strip() != source:
        raise ValueError("Replay HEAD mismatch")
    proof = {"integration_sha": source, "files": checked,
             "copy_scope": "Declared partial source only; historical evidence and generated caches excluded.",
             "git_object_alternate": str(objects), "full_clean_checkout": False,
             "tests_executed": 0, "database_access": False,
             "source_git_dirty": None,
             "missing_reasons": {"source_git_dirty": "Partial source copy with missing unrelated tracked historical artifacts; fixed manifest byte equality is the provenance claim."}}
    (args.output / "FIXED_SOURCE.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({"integration_sha": source, "fixed_files_verified": len(checked), "full_clean_checkout": False, "tests_executed": 0}))


if __name__ == "__main__":
    main()
