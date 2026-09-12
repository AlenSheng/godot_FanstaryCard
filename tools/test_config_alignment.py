"""Keep the published server/client config packages on the same version."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

import config_alignment as alignment

ROOT = Path(__file__).resolve().parents[1]


def _write_package(root: Path, version: str, payload: bytes, digest: str) -> None:
    for relative in ("server/config/generated", "client/data/generated"):
        directory = root / relative
        directory.mkdir(parents=True)
        (directory / "fantasycard.config.bytes").write_bytes(payload)
        (directory / "fantasycard.config.version.txt").write_text(version + "\n", encoding="utf-8")
        (directory / "fantasycard.config.sha256").write_text(digest + "\n", encoding="utf-8")
    catalog = root / "client/data/catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps({"version": version, "tables": {}}), encoding="utf-8")


class ConfigAlignmentTests(unittest.TestCase):
    def test_published_server_and_client_versions_match(self):
        identity = alignment.published_identity(ROOT)
        self.assertEqual(identity["version"], "gdd-0.67-gameplay-completion-1")

    def test_published_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root, "client-new", b"bundle-a", "hash-a")
            (root / "server/config/generated/fantasycard.config.version.txt").write_text("server-old\n", encoding="utf-8")
            with self.assertRaisesRegex(alignment.ConfigAlignmentError, "not aligned"):
                alignment.published_identity(root)

    def test_running_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_package(root, "gdd-0.67-gameplay-completion-1", b"bundle-a", "hash-a")

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = json.dumps({"configVersion": "gdd-0.67-shop-rotation-1"}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_args):
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}/health/ready"
                with self.assertRaisesRegex(alignment.ConfigAlignmentError, "does not match client"):
                    alignment.assert_running_matches(root, url)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_start_scripts_rebuild_when_running_version_drifts(self):
        starter = (ROOT / "server/start-server.bat").read_text(encoding="utf-8")
        native = (ROOT / "server/local-server.ps1").read_text(encoding="utf-8")
        self.assertIn("assert-config-alignment.ps1", starter)
        self.assertIn("force-recreate", starter)
        self.assertIn("Assert-RunningConfigAlignment", native)
        self.assertIn("Rebuilding the local server so it matches the client", native)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
