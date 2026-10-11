"""Verify a cloud B09.2 rendered fixture segment on G without native execution.

Only archive, image, JSON and wire metadata are inspected. A successful receipt
does not certify LIVE, human experience, hardware FPS or the whole PR13 task.
"""
import argparse
import base64
import gzip
import hashlib
import itertools
import json
from pathlib import Path, PurePosixPath
import struct
import tarfile
import zlib


BLOCK = 65536
NATIVE_SOURCE = "1341e160afc67ba826d4b37250c9ec58f8c99462"
SEEDS = (460001, 461001, 462001)
RESOLUTIONS = ((1920, 1080), (1280, 720), (960, 540))
FPS = (30, 60, 144)
DELAYS = (0, 250, 1000)
LANGUAGES = ("zh-CN", "zh-TW", "en", "ja", "ko")
POOL_HINTS = {
    "zh-CN": "只影响本局；新卡进入弃牌，不补抽。",
    "zh-TW": "只影響本局；新卡進入棄牌，不補抽。",
    "en": "This run only. New cards enter discard; no bonus draw.",
    "ja": "今回の探索のみ。新カードは捨て札へ。追加ドローなし。",
    "ko": "이번 탐험에만 적용. 새 카드는 버린 카드 더미로 이동하며 추가 드로우는 없습니다."
}
NATIVE_RELATIVE = "attempt-2/outputs/wire-vectors.jsonl"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_parts(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name,
            "Unsafe archive/member path")
    parts = PurePosixPath(name).parts
    require(not name.startswith("/") and all(p not in ("", ".", "..") for p in parts),
            "Absolute or traversing member path")
    require(PurePosixPath(*parts).as_posix() == name, "Noncanonical member path")
    return parts


def resolve_member(root, name):
    parts = safe_parts(name)
    candidate = root.joinpath(*parts)
    for parent in (candidate,) + tuple(candidate.parents):
        if parent == root.parent:
            break
        require(not parent.is_symlink(), "Symlink in local member path")
    require(candidate.resolve().is_relative_to(root.resolve()), "Member escapes destination")
    return candidate


def verify_archive(archive, receipt, destination):
    """Stream all members, reject links/specials, and verify existing extraction."""
    require(archive.is_file() and not archive.is_symlink(), "Missing/local linked archive")
    require(archive.stat().st_size == receipt["bytes"] and sha(archive) == receipt["sha256"],
            "Archive byte count or SHA mismatch")
    # gzip must be read to EOF, including its trailer; tar EOF alone does not
    # guarantee CRC verification of the enclosing gzip stream.
    with gzip.open(archive, "rb") as stream:
        for _ in iter(lambda: stream.read(BLOCK), b""):
            pass
    destination.mkdir(parents=True, exist_ok=True)
    require(not destination.is_symlink(), "Linked extraction directory")
    members = {}
    root_name = None
    with tarfile.open(archive, mode="r|gz") as stream:
        for member in stream:
            require(member.isfile(), "Tar links, directories and special members are rejected")
            parts = safe_parts(member.name)
            require(len(parts) >= 2 and member.name not in members, "Duplicate/unnested archive member")
            if root_name is None:
                root_name = parts[0]
            require(parts[0] == root_name, "Mixed archive roots")
            require(member.size <= 64 * 1024**2 and len(members) < 10000, "Unexpected segment member size/count")
            relative = PurePosixPath(*parts[1:]).as_posix()
            path = resolve_member(destination, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.exists()
            require(not existing or path.is_file(), "Nonfile extraction destination")
            digest = hashlib.sha256()
            size = 0
            source = stream.extractfile(member)
            require(source is not None, "Missing tar member stream")
            target = None if existing else path.open("xb")
            try:
                for block in iter(lambda: source.read(BLOCK), b""):
                    size += len(block)
                    digest.update(block)
                    if target is not None:
                        target.write(block)
            finally:
                if target is not None:
                    target.close()
                source.close()
            require(size == member.size and path.stat().st_size == size and sha(path) == digest.hexdigest(),
                    "Extracted member bytes/SHA mismatch: " + relative)
            members[member.name] = {"path": relative, "bytes": size, "sha256": digest.hexdigest()}
    require(root_name is not None, "Empty archive")
    manifest_path = resolve_member(destination, "manifest.json")
    require(manifest_path.is_file() and sha(manifest_path) == receipt["manifest_sha256"],
            "Manifest missing or SHA mismatch")
    manifest = read_json(manifest_path)
    rows = manifest["files"]
    require(len(rows) == receipt["members"] and len(members) == len(rows) + 1,
            "Archive/manifest member count mismatch")
    names = set()
    for row in rows:
        path = row["path"]
        safe_parts(path)
        require(path != "manifest.json" and path not in names, "Duplicate manifest path")
        names.add(path)
        actual = members.get(root_name + "/" + path)
        require(actual is not None and actual["bytes"] == row["bytes"] and actual["sha256"] == row["sha256"],
                "Member is absent or disagrees with manifest: " + path)
    expected = names | {"manifest.json"}
    require({m["path"] for m in members.values()} == expected, "Unlisted tar member")
    local_files = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    require(local_files - {"local-backup-receipt.json"} == expected, "Unlisted extracted file")
    return manifest


def png_validate(path):
    """Check every PNG chunk CRC and every deflated scanline without pixel buffers."""
    decoder = zlib.decompressobj()
    header = None
    row_bytes = None
    decoded = 0
    chunks = 0
    saw_idat = False
    idat_ended = False
    with path.open("rb") as stream:
        require(stream.read(8) == b"\x89PNG\r\n\x1a\n", "PNG signature mismatch")
        while True:
            raw_length = stream.read(4)
            require(len(raw_length) == 4, "Truncated PNG length")
            length = struct.unpack(">I", raw_length)[0]
            kind = stream.read(4)
            require(len(kind) == 4 and length <= 64 * 1024**2, "Invalid PNG chunk")
            require(chunks > 0 or kind == b"IHDR", "PNG IHDR must be first")
            require(kind != b"IDAT" or not idat_ended, "Noncontiguous PNG IDAT")
            crc = zlib.crc32(kind)
            remaining = length
            capture = bytearray() if kind == b"IHDR" else None
            while remaining:
                block = stream.read(min(BLOCK, remaining))
                require(block, "Truncated PNG data")
                remaining -= len(block)
                crc = zlib.crc32(block, crc)
                if capture is not None:
                    capture.extend(block)
                if kind == b"IDAT":
                    require(header is not None, "PNG IDAT before IHDR")
                    data = block
                    while data:
                        pixels = decoder.decompress(data, BLOCK)
                        data = decoder.unconsumed_tail
                        for offset in range((-decoded) % row_bytes, len(pixels), row_bytes):
                            require(pixels[offset] <= 4, "Invalid PNG row filter")
                        decoded += len(pixels)
                        require(decoded <= row_bytes * header[1], "PNG inflated data exceeds dimensions")
                        require(not decoder.unused_data, "Extra deflate bytes in PNG")
                    saw_idat = True
            raw_crc = stream.read(4)
            require(len(raw_crc) == 4 and struct.unpack(">I", raw_crc)[0] == crc & 0xffffffff,
                    "PNG chunk CRC mismatch")
            if kind == b"IHDR":
                require(header is None and length == 13, "Duplicate/invalid PNG IHDR")
                width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", capture)
                # Godot Image.save_png emits noninterlaced 8 bit RGB/RGBA.
                require(0 < width <= 8192 and 0 < height <= 8192 and depth == 8 and color in (2, 6)
                        and compression == filtering == interlace == 0, "Unexpected Godot PNG format")
                header = (width, height)
                row_bytes = 1 + width * (3 if color == 2 else 4)
            elif kind != b"IDAT" and saw_idat:
                idat_ended = True
            chunks += 1
            if kind == b"IEND":
                require(length == 0 and saw_idat and decoder.eof and not decoder.unused_data
                        and decoded == row_bytes * header[1] and not stream.read(1),
                        "PNG IEND/deflate/scanline length mismatch")
                break
    return {"size": list(header), "decoded_scanline_bytes": decoded, "chunks": chunks}


def varint(raw, position):
    value = 0
    for offset in range(10):
        require(position < len(raw), "Truncated Protobuf varint")
        byte = raw[position]
        position += 1
        require(offset != 9 or byte <= 1, "Overflow Protobuf varint")
        value |= (byte & 127) << (offset * 7)
        if not byte & 128:
            return value, position
    raise ValueError("Overlong Protobuf varint")


def protobuf_fields(raw, allowed):
    require(0 < len(raw) <= 16384, "Unexpected Protobuf payload size")
    result = {}
    position = 0
    while position < len(raw):
        key, position = varint(raw, position)
        field, wire = key >> 3, key & 7
        require(field in allowed and allowed[field] == wire and field not in result,
                "Unknown, duplicate or mistyped Protobuf field")
        if wire == 0:
            result[field], position = varint(raw, position)
        else:
            length, position = varint(raw, position)
            require(length <= len(raw) - position, "Truncated Protobuf byte field")
            result[field] = raw[position:position + length]
            position += length
    return result


def decode64(value):
    require(isinstance(value, str), "Nonstring base64 payload")
    return base64.b64decode(value, validate=True)


def choose_command(raw):
    fields = protobuf_fields(raw, {1: 2, 2: 0, 3: 2})
    require(1 in fields and fields.get(2, 0) in (0, 1), "Invalid choose candidate/bool")
    return {"candidate_id": fields[1].decode("utf-8"), "accept": bool(fields.get(2, 0)),
            "replace_instance_id": fields.get(3, b"").decode("utf-8")}


def native_rows(path, expected_sha):
    if path.suffix == ".json":
        data = read_json(path)
        require(data["source_sha"] == expected_sha, "Native fixture source mismatch")
        return data["rows"]
    with path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    require(rows and all(row["source_sha"] == expected_sha for row in rows), "Native vectors source mismatch")
    return rows


def resolve_native(directory, manifest, explicit):
    """Require a hashed original fixture, not candidate IDs supplied by UI itself."""
    inputs = read_json(directory / "metadata/inputs.json")
    source_name = "client/tests/data/pool_capacity_native_witnesses.json"
    candidates = [(directory / "metadata/pool_capacity_native_witnesses.json", "segment-manifest"),
                  (directory / "outputs/pool_capacity_native_witnesses.json", "segment-manifest")]
    repo = Path(__file__).resolve().parents[1]
    candidates.append((repo / source_name, "source-inputs"))
    if explicit is not None:
        candidates.insert(0, (explicit.resolve(), "explicit"))
    for path, proof in candidates:
        if path.is_file():
            digest = sha(path)
            if path.resolve().is_relative_to(directory.resolve()):
                relative = path.resolve().relative_to(directory.resolve()).as_posix()
                matching = [r for r in manifest["files"] if r["path"] == relative]
                require(len(matching) == 1 and matching[0]["sha256"] == digest,
                        "Unanchored original fixture")
            else:
                require(inputs.get(source_name) == digest, "Original fixture does not match frozen inputs")
            if path.suffix == ".json":
                require(inputs.get(source_name) == digest, "Archived original fixture does not match frozen inputs")
            return path, {"path": str(path), "sha256": digest, "anchor": proof}
    root = repo / "outputs/pr13-tencent-20261009/pool-capacity-wire-local-verified/pool-capacity-wire-delivery"
    path = root / NATIVE_RELATIVE
    old_receipt = repo / "outputs/pr13-tencent-20261009/pool-capacity-wire-delivery-receipt.json"
    require(path.is_file() and old_receipt.is_file(), "Original native vectors/fixture are missing")
    receipt = read_json(old_receipt)
    require(receipt.get("ok") is True, "Original native transfer receipt unsuccessful")
    original_manifest = root / "manifest.json"
    require(sha(original_manifest) == receipt["manifest_sha256"], "Original native manifest SHA mismatch")
    matches = [r for r in read_json(original_manifest)["files"] if r["path"] == NATIVE_RELATIVE]
    require(len(matches) == 1 and path.stat().st_size == matches[0]["bytes"] and sha(path) == matches[0]["sha256"],
            "Original native vectors SHA/size mismatch")
    return path, {"path": str(path), "sha256": sha(path), "anchor": "previous-G-native-manifest",
                  "manifest_sha256": receipt["manifest_sha256"]}


def verify_segment(directory, manifest, explicit_native=None):
    meta = read_json(directory / "metadata/preregistration.json")
    segment = manifest["segment"]
    require(all(meta.get(k) == v for k, v in segment.items()), "Segment/preregistration disagreement")
    case, hero, cap, language = segment["case"], segment["hero"], segment["capacity"], segment["language"]
    require(case in ("PR13-B09.2-T01", "PR13-B09.2-T02", "PR13-B09.2-T03")
            and hero in ("Guardian", "Mage", "Priest") and cap in (3, 5, 8) and language in LANGUAGES,
            "Unknown render segment")
    require(segment["id"] == f"{hero}-{cap}-{case[-3:]}-{language}", "Segment ID mismatch")
    require(meta["native_source_sha"] == NATIVE_SOURCE and meta["whole_task_accepted"] is False
            and meta["fixture_matrix_only"] is True, "Segment scope or native source disagreement")
    result = read_json(directory / "metadata/result.json")
    runtime = read_json(directory / "outputs" / case / "result.json")
    native = read_json(directory / "outputs" / case / "native-result.json")
    require(result["ok"] is True and result["shutdown_resources_clean"] is True
            and result["whole_task_accepted"] is False and result["diagnostic_only"] is False,
            "Cloud segment unsuccessful or scope changed")
    require(result["source_sha"] == meta["render_source_sha"] and result["segment"] == segment["id"],
            "Cloud execution source/segment mismatch")
    require(runtime["ok"] is True and runtime["exit_code"] == 0 and runtime["native_clean"] is True
            and runtime["source_inputs_unchanged"] is True and runtime["owned_container_removed"] is True
            and runtime["oom_killed"] is False and runtime["production_changed"] is False,
            "Renderer lifecycle or source failure")
    require(native["ok"] is True and native["diagnostic_only"] is False and native["whole_task_accepted"] is False
            and native["display_driver"] != "headless", "Missing native rendered result")
    expected_count = 162 if case.endswith("T03") else 81
    observations = native["observations"]
    require(len(observations) == expected_count == segment["expected_rows"] == runtime["observations"],
            "Segment observation count mismatch")
    require(segment["expected_PNGs"] == runtime["screenshots"] == 9, "Segment PNG count mismatch")
    original_path, original_proof = resolve_native(directory, manifest, explicit_native)
    original = [r for r in native_rows(original_path, NATIVE_SOURCE)
                if r["case_id"] == case and r["actual"]["hero"] == hero and r["actual"]["capacity"] == cap]
    if case.endswith("T01"):
        original = [r for r in original if r["actual"]["occupancy"] == cap - 1]
    elif case.endswith("T02"):
        original = [r for r in original if r["actual"]["pile"] == dict(zip(SEEDS, ("Hand", "Library", "Discard"))).get(r["actual"]["seed"])]
    require(len(original) == (6 if case.endswith("T03") else 3), "Original native witness count mismatch")
    originals = {}
    for row in original:
        a = row["actual"]
        occupancy = len(a["before"]["Players"][0]["MonsterPool"]["Active"])
        key = (a["seed"], occupancy)
        require(key not in originals, "Duplicate original native witness")
        originals[key] = row
    occupancies = (0, cap) if case.endswith("T03") else ((cap - 1,) if case.endswith("T01") else (cap,))
    expected_keys = set(itertools.product(RESOLUTIONS, FPS, DELAYS, SEEDS, occupancies))
    keys = set()
    images = {}
    checks = ("passed", "entry_clicked", "dialog_inside_window", "command_exact",
              "state_unchanged_until_response", "original_after_pool_applied", "closed_after_actual_click")
    for observation in observations:
        require(all(observation.get(k) is True for k in checks), "Unsuccessful rendered observation")
        require(observation["case_id"] == case and observation["hero"] == hero
                and observation["capacity"] == cap and observation["language"] == language
                and observation["native_source_sha"] == NATIVE_SOURCE
                and observation["diagnostic_only"] is False
                and observation["request_header_projection_only"] is True, "Observation scope/source mismatch")
        key = (tuple(observation["resolution"]), observation["frame_cap"],
               observation["controlled_response_delay_ms"], observation["seed"], observation["native_occupancy"])
        require(key in expected_keys and key not in keys, "Duplicate or unexpected render matrix key")
        keys.add(key)
        require(observation["cycle"] == SEEDS.index(observation["seed"]) + 1, "Seed/cycle mismatch")
        original = originals[(observation["seed"], observation["native_occupancy"])]
        a = original["actual"]
        require(observation["native_candidate_id"] == a["candidate"]["InstanceId"]
                and observation["native_replacement_pile"] == a.get("pile", ""), "Native candidate/pile mismatch")
        envelope = protobuf_fields(decode64(original["request_wire"]), {1: 0, 2: 2, 3: 2, 4: 0, 5: 2, 6: 2, 7: 2})
        require(envelope.get(1) == 1 and envelope.get(2) == b"monster.choose" and 5 in envelope,
                "Unexpected native command envelope")
        require(observation.get("actual_command_wire") and observation.get("actual_command_payload"),
                "Native render evidence did not retain actual command wire/payload; cloud rerun required")
        expected_wire = decode64(observation["expected_native_wire_payload"])
        actual_wire = decode64(observation["actual_command_wire"])
        require(expected_wire == envelope[5], "Expected payload was not original native command")
        expected = choose_command(expected_wire)
        actual = choose_command(actual_wire)
        payload = observation["actual_command_payload"]
        require(isinstance(payload, dict) and set(payload) <= {"candidate_id", "accept", "replace_instance_id"}
                and isinstance(payload.get("accept"), bool) and isinstance(payload.get("candidate_id"), str)
                and isinstance(payload.get("replace_instance_id", ""), str), "Invalid actual command JSON")
        normalized = payload | {"replace_instance_id": payload.get("replace_instance_id", "")}
        require(actual == expected == normalized, "Independent command wire/JSON mismatch")
        require(actual["candidate_id"] == a["candidate"]["InstanceId"]
                and actual["accept"] == (not case.endswith("T03"))
                and actual["replace_instance_id"] == ((a.get("replacement") or {}).get("InstanceId", "")),
                "Command does not represent the original native decision")
        if case.endswith("T02"):
            require(observation["full_accept_initially_disabled"] is True
                    and observation["actual_replacement_selected"] is True, "Full-pool replacement control failed")
        require(observation["labels"] and all(label["inside"] is True and label["all_lines_visible"] is True
                and label["text"] for label in observation["labels"]), "Rendered label is missing/clipped")
        require(POOL_HINTS[language] in {label["text"] for label in observation["labels"]},
                "Rendered language-specific pool hint does not match requested locale")
        if "actual_language" in observation:
            require(observation["actual_language"] == language,
                    "Actual selected UI language differs from requested locale")
        require(observation["input_traces"], "Missing actual input trace")
        picture = observation["screenshot"]
        should_capture = key[2] == 0 and original is next(iter(originals.values()))
        require(bool(picture) == should_capture, "Unexpected screenshot capture stratum")
        if picture:
            require(picture == f"{case}_{language}_{key[0][0]}_{key[1]}_{cap}.png" and picture not in images,
                    "Duplicate or unexpected screenshot name")
            path = resolve_member(directory, "outputs/" + case + "/" + picture)
            image = png_validate(path)
            require(image["size"] == observation["window_geometry"]["pixel_size"], "PNG/native pixel dimensions mismatch")
            images[picture] = {"path": path.relative_to(directory).as_posix(), "sha256": sha(path), **image}
    require(keys == expected_keys and len(images) == 9, "Incomplete render matrix/PNG witnesses")
    actual_images = {r["path"] for r in manifest["files"] if r["path"].endswith(".png")}
    require(actual_images == {image["path"] for image in images.values()}, "Unexpected or unreferenced PNG")
    engine = (directory / "outputs" / case / "engine.log").read_text(encoding="utf-8", errors="replace")
    require(not any(marker in engine for marker in ("SCRIPT ERROR", "Parse Error", "Failed to load script",
                "resources still in use", "ObjectDB instances were leaked")), "Native log has errors/leaks")
    return {"segment": segment, "matrix_rows_verified": len(keys), "presentation_combinations": 27,
            "PNG_CRC_deflate_verified": 9, "independent_wire_command_rows_verified": len(keys),
            "native_original_proof": original_proof, "images": list(images.values()),
            "render_source_sha": meta["render_source_sha"], "native_source_sha": NATIVE_SOURCE,
            "normal_shutdown_clean": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="G extraction root containing metadata/outputs")
    parser.add_argument("--receipt", type=Path, required=True, help="Transfer receipt with archive SHA/size and manifest SHA")
    parser.add_argument("--archive", type=Path, help="Defaults to receipt.local_archive/archive_file or receipt-name.private.tar.gz")
    parser.add_argument("--native-witnesses", type=Path, help="Original JSON fixture, anchored to frozen inputs")
    args = parser.parse_args(argv)
    receipt = read_json(args.receipt)
    require(receipt.get("ok") is True, "Transfer receipt unsuccessful")
    archive = args.archive
    if archive is None:
        name = receipt.get("local_archive") or receipt.get("archive_file")
        archive = Path(name) if name else args.receipt.with_name(args.receipt.name.replace("-receipt.json", ".private.tar.gz"))
    directory = args.directory.resolve()
    manifest = verify_archive(archive.resolve(), receipt, directory)
    result = verify_segment(directory, manifest, args.native_witnesses)
    output = receipt | result | {"ok": True, "local_archive": str(archive.resolve()), "local_directory": str(directory),
              "members_verified": len(manifest["files"]), "archive_gzip_CRC_verified": True,
              "no_native_business_executed_locally": True, "whole_task_accepted": False,
              "full_matrix_accepted": False, "LIVE_accepted": False, "human_experience_accepted": False,
              "hardware_FPS_accepted": False, "scope": "one cloud software-rendered fixture language segment"}
    path = directory / "local-backup-receipt.json"
    if path.exists():
        require(read_json(path) == output, "Existing local verification receipt differs; preserve it")
    else:
        path.write_bytes((json.dumps(output, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({k: v for k, v in output.items() if k not in ("images", "native_original_proof")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
