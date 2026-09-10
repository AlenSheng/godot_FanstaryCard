"""Verify encrypted Godot PCK directory and every payload without extracting files."""

import hashlib
import io
from pathlib import Path, PurePosixPath
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Truncated PCK data.")
    return data


def number(stream, fmt):
    return struct.unpack("<" + fmt, read_exact(stream, struct.calcsize("<" + fmt)))[0]


def decrypt_block(stream, key, total_size):
    digest = read_exact(stream, 16)
    length = number(stream, "Q")
    iv = read_exact(stream, 16)
    padded = (length + 15) & ~15
    if padded > total_size or padded > total_size - stream.tell():
        raise ValueError("Invalid encrypted block length.")
    decryptor = Cipher(algorithms.AES(key), modes.CFB(iv)).decryptor()
    data = (decryptor.update(read_exact(stream, padded)) + decryptor.finalize())[:length]
    if hashlib.md5(data).digest() != digest:
        raise ValueError("PCK key mismatch or corrupted encrypted payload.")
    return data


def verify_pck(path, key_hex, require_game=True):
    path = Path(path)
    key = bytes.fromhex(key_hex)
    if len(key) != 32 or not any(key):
        raise ValueError("A nonzero AES-256 key is required.")
    total_size = path.stat().st_size
    entries = []
    with path.open("rb") as stream:
        magic, version, major, minor, patch, flags = struct.unpack("<6I", read_exact(stream, 24))
        if magic != 0x43504447 or version not in (2, 3, 4):
            raise ValueError("Unsupported standalone PCK format.")
        if not flags & 1 or flags & ~3:
            raise ValueError("PCK directory must be encrypted; sparse/delta bundles are not accepted.")
        file_base = number(stream, "Q")
        if version in (3, 4):
            directory_offset = number(stream, "Q")
            if directory_offset >= total_size:
                raise ValueError("PCK directory offset is out of bounds.")
            stream.seek(directory_offset)
        else:
            read_exact(stream, 64)
        count = number(stream, "I")
        if not 0 < count <= 100000:
            raise ValueError("Invalid PCK file count.")
        directory = io.BytesIO(decrypt_block(stream, key, total_size))
        seen = set()
        for _ in range(count):
            path_length = number(directory, "I")
            if not 0 < path_length <= 16384:
                raise ValueError("Invalid PCK path length.")
            name = read_exact(directory, path_length).rstrip(b"\0").decode("utf-8")
            name = name.removeprefix("res://")
            parts = PurePosixPath(name).parts
            if not parts or ".." in parts or name.startswith("/") or "\\" in name or name in seen:
                raise ValueError("Unsafe or duplicate PCK path.")
            seen.add(name)
            offset = number(directory, "Q") + file_base
            size = number(directory, "Q")
            digest = read_exact(directory, 16)
            entry_flags = number(directory, "I")
            if entry_flags != 1:
                raise ValueError("PCK contains an unencrypted or unsupported file: " + name)
            if offset >= total_size:
                raise ValueError("PCK payload offset is out of bounds.")
            entries.append((name, offset, size, digest))
        if directory.read():
            raise ValueError("Unexpected trailing directory data.")
        for name, offset, size, digest in entries:
            stream.seek(offset)
            data = decrypt_block(stream, key, total_size)
            if len(data) != size or hashlib.md5(data).digest() != digest:
                raise ValueError("PCK directory/payload checksum mismatch: " + name)
    names = [entry[0] for entry in entries]
    forbidden_extensions = {".gd", ".cs", ".py", ".pdb", ".key", ".dpapi", ".psd", ".blend", ".blend1"}
    forbidden = [name for name in names if PurePosixPath(name).suffix in forbidden_extensions
                 or name.startswith(("tests/", "evidence/", "platform/export_"))
                 or "export_credentials" in name]
    if forbidden:
        raise ValueError("Development sources or secrets leaked into PCK: " + ", ".join(forbidden[:10]))
    scripts = sum(name.endswith(".gdc") for name in names)
    if require_game:
        required = {"project.binary", "assets/imported/manifest.json", "data/catalog.json"}
        if not required.issubset(names) or not scripts:
            raise ValueError("PCK is missing essential game files or compiled scripts.")
    return {"ok": True, "format": version, "engine": f"{major}.{minor}.{patch}",
            "directory_encrypted": True, "files_checked": len(entries),
            "encrypted_files": len(entries), "compiled_scripts": scripts,
            "plaintext_scripts": 0, "pck_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
