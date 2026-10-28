import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools import pr13_local_runtime as runtime


def inspection(scope="disposable-local", address="127.0.0.1"):
    return [{"Id": "owned-container", "Image": "sha256:owned-pg-image",
             "Config": {"Labels": {"codex.scope": scope, "codex.task": "pr13-stages-20261008"},
                        "Env": ["POSTGRES_PASSWORD=fixture-only"]},
             "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": address, "HostPort": "54321"}]}}}]


class OwnedRuntimeTests(unittest.TestCase):
    def result(self, value):
        return SimpleNamespace(stdout=json.dumps(value), check_returncode=lambda: None)

    def test_unowned_or_public_database_is_refused_before_any_write(self):
        for info in (inspection(scope="production"), inspection(address="0.0.0.0")):
            with self.subTest(info=info), patch.object(runtime, "run", return_value=self.result(info)) as command:
                with self.assertRaises(ValueError):
                    runtime.owned_database_info("container")
                self.assertEqual(command.call_count, 1)
                self.assertEqual(command.call_args.args[0][:2], ["docker", "inspect"])

    def test_credentials_are_excluded_from_runtime_record(self):
        with patch.object(runtime, "run", return_value=self.result(inspection())):
            host = runtime.LocalRuntime(Path("unused"), "container")
        self.assertNotIn("fixture-only", json.dumps(host.record))
        self.assertNotIn("password", host.record)

    def test_failed_database_creation_keeps_source_failure_and_closes_log(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runtime, "run", return_value=self.result(inspection())):
                host = runtime.LocalRuntime(Path(directory) / "scenario", "container")
            with patch.object(runtime, "run", side_effect=OSError("create failed")):
                with self.assertRaises(OSError):
                    host.__enter__()
            self.assertTrue(host.log.closed)
            self.assertFalse(host.database_created)
            self.assertTrue(host.record["database_removed"])


if __name__ == "__main__":
    unittest.main()
