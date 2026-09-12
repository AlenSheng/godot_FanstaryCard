"""Keep the published server/client config packages on the same version."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConfigAlignmentTests(unittest.TestCase):
    def test_published_server_and_client_versions_match(self):
        server = ROOT / "server/config/generated"
        client = ROOT / "client/data/generated"
        catalog = json.loads((ROOT / "client/data/catalog.json").read_text(encoding="utf-8"))
        server_version = (server / "fantasycard.config.version.txt").read_text(encoding="utf-8").strip()
        client_version = (client / "fantasycard.config.version.txt").read_text(encoding="utf-8").strip()
        self.assertTrue(server_version)
        self.assertEqual(server_version, client_version)
        self.assertEqual(server_version, catalog["version"])
        self.assertEqual(
            (server / "fantasycard.config.sha256").read_text(encoding="utf-8").strip(),
            (client / "fantasycard.config.sha256").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            (server / "fantasycard.config.bytes").read_bytes(),
            (client / "fantasycard.config.bytes").read_bytes(),
        )

    def test_start_alignment_script_treats_running_mismatch_as_rebuild(self):
        script = (ROOT / "server/assert-config-alignment.ps1").read_text(encoding="utf-8")
        helper = (ROOT / "server/config-alignment.ps1").read_text(encoding="utf-8")
        starter = (ROOT / "server/start-server.bat").read_text(encoding="utf-8")
        native = (ROOT / "server/local-server.ps1").read_text(encoding="utf-8")
        self.assertIn("does not match client", helper)
        self.assertIn("exit 1", script)
        self.assertIn("exit 2", script)
        self.assertIn("assert-config-alignment.ps1", starter)
        self.assertIn("force-recreate", starter)
        self.assertIn("Assert-RunningConfigAlignment", native)
        self.assertIn("Rebuilding the local server so it matches the client", native)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
