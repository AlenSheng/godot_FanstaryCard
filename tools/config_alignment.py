"""Compare published FantasyCard config packages and an optional running server."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen


class ConfigAlignmentError(Exception):
    """Published files or the running server do not share one configVersion."""


def published_identity(root: Path) -> dict[str, str]:
    server = root / "server/config/generated"
    client = root / "client/data/generated"
    catalog = json.loads((root / "client/data/catalog.json").read_text(encoding="utf-8"))
    server_version = (server / "fantasycard.config.version.txt").read_text(encoding="utf-8").strip()
    client_version = (client / "fantasycard.config.version.txt").read_text(encoding="utf-8").strip()
    catalog_version = str(catalog.get("version", "")).strip()
    if not server_version:
        raise ConfigAlignmentError("Published server config version is empty.")
    if server_version != client_version or server_version != catalog_version:
        raise ConfigAlignmentError(
            "Published config versions are not aligned. "
            f"server={server_version} client={client_version} catalog={catalog_version}"
        )
    server_hash = (server / "fantasycard.config.sha256").read_text(encoding="utf-8").strip()
    client_hash = (client / "fantasycard.config.sha256").read_text(encoding="utf-8").strip()
    if server_hash != client_hash:
        raise ConfigAlignmentError(f"Published config hashes differ ({server_hash} vs {client_hash}).")
    server_bytes = (server / "fantasycard.config.bytes").read_bytes()
    client_bytes = (client / "fantasycard.config.bytes").read_bytes()
    if server_bytes != client_bytes:
        raise ConfigAlignmentError("Published server/client config bytes differ.")
    return {"version": server_version, "sha256": server_hash}


def running_config_version(url: str) -> str:
    root = url.rstrip("/")
    if root.endswith("/health/ready"):
        root = root[: -len("/health/ready")]
    with urlopen(root + "/", timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    version = str(payload.get("configVersion", "")).strip()
    if not version:
        raise ConfigAlignmentError(f"Server at {root}/ did not return configVersion.")
    return version


def assert_running_matches(root: Path, url: str) -> str:
    expected = published_identity(root)["version"]
    actual = running_config_version(url)
    if actual != expected:
        raise ConfigAlignmentError(f"Running server config '{actual}' does not match client '{expected}'.")
    return actual
