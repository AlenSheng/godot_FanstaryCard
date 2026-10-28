"""Restore exact historical register snapshots from the bounded release archive.

Use a private output directory. Existing files are verified and never replaced.
The archive preserves historical decisions; extraction grants no acceptance.
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import os
import shutil
import tarfile
import uuid

KIND = "lossless_historical_register_archive"
PREFIX = "docs/reports/pr13-stages-20261009/"


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def destination(root, name):
    relative = PurePosixPath(name)
    if (relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name
            or not name.startswith(PREFIX) or not name.endswith("/register.json")):
        raise ValueError("Invalid register member path")
    result = (root / name).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Register output escapes the selected directory")
    return result


def check_space(output, required):
    location = output
    while not location.exists():
        location = location.parent
    usage = shutil.disk_usage(location)
    floor = max(3_000_000_000, int(usage.total * 0.05))
    if usage.free - required < floor:
        raise ValueError("Extraction would cross the 3GB/5% disk reserve")


def restore(archive, manifest, output, member=None):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    data = json.loads(Path(manifest).read_bytes())
    if data.get("kind") != KIND or file_sha(archive) != data.get("archive_sha256"):
        raise ValueError("Archive identity does not match the manifest")
    entries = data.get("entries", [])
    if not 1 <= len(entries) <= 1000 or len(entries) != data.get("member_count"):
        raise ValueError("Invalid bounded register manifest")
    expected, paths, folded = {}, {}, set()
    for entry in entries:
        name = entry["path"]
        if name.casefold() in folded or not 0 <= entry["bytes"] <= 64 * 1024**2:
            raise ValueError("Duplicate or oversized register entry")
        folded.add(name.casefold())
        expected[name], paths[name] = entry, destination(output, name)
    if sum(row["bytes"] for row in entries) != data.get("uncompressed_bytes"):
        raise ValueError("Uncompressed size differs from the manifest")
    if member is not None and member not in expected:
        raise ValueError("Requested member is not in the archive")
    selected = {member} if member is not None else set(expected)
    existing = set()
    for name in selected:
        path = paths[name]
        if path.exists():
            if not path.is_file() or file_sha(path) != expected[name]["sha256"]:
                raise ValueError("An existing snapshot differs; no file was replaced")
            existing.add(name)
    needed = selected - existing
    check_space(output, sum(expected[name]["bytes"] for name in needed))
    if not needed:
        return {"verified_archive": True, "restored": [],
                "already_present": sorted(existing), "acceptance_granted": False}
    seen, restored = set(), []
    # Bound decoded reads: highly repetitive ledgers can expand a tiny XZ input
    # block to many MiB, making tarfile's internal compressed-stream skips slow.
    with lzma.open(archive, "rb") as decoded, tarfile.open(fileobj=decoded, mode="r|", bufsize=1024 * 1024) as source:
        for info in source:
            if (not info.isfile() or info.name not in expected or info.name in seen
                    or info.size != expected[info.name]["bytes"]):
                raise ValueError("Archive members differ from the manifest")
            seen.add(info.name)
            if info.name not in needed:
                continue
            target = destination(output, info.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".restore-" + uuid.uuid4().hex)
            try:
                digest = hashlib.sha256()
                reader = source.extractfile(info)
                with temporary.open("xb") as writer:
                    for block in iter(lambda: reader.read(1024 * 1024), b""):
                        writer.write(block)
                        digest.update(block)
                    writer.flush()
                    os.fsync(writer.fileno())
                if digest.hexdigest() != expected[info.name]["sha256"]:
                    raise ValueError("Restored snapshot SHA does not match")
                check_space(output, 0)
                # Atomic no-clobber publication; an existing target is never replaced.
                os.link(temporary, target)
                restored.append(info.name)
            finally:
                if temporary.exists() and temporary.resolve().is_relative_to(output):
                    temporary.unlink()
            if member is not None and info.name == member:
                break
    if (member is None and seen != set(expected)) or not needed.issubset(restored):
        raise ValueError("Archive is incomplete")
    return {"verified_archive": True, "restored": restored,
            "already_present": sorted(existing), "acceptance_granted": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=root / "docs/archives/pr13-register-snapshots-20261028-r1.tar.xz")
    parser.add_argument("--manifest", type=Path, default=root / "docs/archives/pr13-register-snapshots-20261028-r1.manifest.json")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--member", help="Optional exact member path for a single historical snapshot")
    args = parser.parse_args()
    print(json.dumps(restore(args.archive, args.manifest, args.output, args.member), ensure_ascii=False))
