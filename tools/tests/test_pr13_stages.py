"""Regression checks for fail-closed preregistration and truthful stage evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import pr13_stages as stages


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profiles = stages.read(stages.ROOT / stages.PROFILE)

    def test_frozen_profile_is_complete(self):
        self.assertEqual(stages.validate_profiles(self.profiles), [])

    def test_invalid_or_missing_deadline_is_rejected(self):
        for value in (None, False, 0, float("nan"), float("inf")):
            with self.subTest(value=value):
                profile = copy.deepcopy(self.profiles)
                profile["profiles"]["OFFLINE"]["deadline_seconds"] = value
                self.assertTrue(stages.validate_profiles(profile))

    def test_overlapping_seed_blocks_are_rejected(self):
        self.profiles["profiles"]["EXPERIMENT"]["seed_blocks"][1]["start"] = 100500
        self.assertIn("Experiment seed blocks overlap", stages.validate_profiles(self.profiles))

    def test_50_clients_cannot_prove_100_active(self):
        self.profiles["profiles"]["CAPACITY"]["active_targets"] = [50, 50]
        self.assertTrue(stages.validate_profiles(self.profiles))

    def test_remote_scope_cannot_be_implied(self):
        self.profiles["execution_boundary"] = "production"
        self.assertTrue(stages.validate_profiles(self.profiles))


class ConfigHashTests(unittest.TestCase):
    def test_equal_declared_hashes_do_not_hide_wrong_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = b"\x0a\x02v1\x1a\x05table"
            expected = hashlib.sha256(canonical).hexdigest()
            published = b"\x0a\x02v1\x12\x20" + bytes.fromhex(expected) + b"\x1a\x05table"
            for folder in (root / "server/config/generated", root / "client/data/generated"):
                folder.mkdir(parents=True)
                (folder / "fantasycard.config.bytes").write_bytes(published)
                (folder / "fantasycard.config.sha256").write_text(expected)
                (folder / "fantasycard.config.version.txt").write_text("v1")
            (root / "config").mkdir()
            (root / "config/FantasyCard_Config.xlsx").write_bytes(b"test-source")
            stages.write(root / "client/data/catalog.json", {"version": "v1"})
            self.assertEqual(stages.config_identity(root)["content_sha256"], expected)
            for folder in (root / "server/config/generated", root / "client/data/generated"):
                (folder / "fantasycard.config.bytes").write_bytes(published[:-1] + b"X")
            with self.assertRaisesRegex(ValueError, "embedded hash"):
                stages.config_identity(root)


class StageTests(unittest.TestCase):
    def test_full_coverage_no_runtime_acceptance_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "S0"
            summary = stages.freeze(output)
            self.assertEqual(summary["counts"]["tasks"], 132)
            self.assertEqual(summary["counts"]["cases"], 396)
            self.assertEqual(summary["counts"]["runtime_accepted"], 0)
            self.assertFalse(summary["runtime_acceptance"])
            self.assertEqual(stages.check(output, verify_current=False), summary["counts"])
            report = output / "LOAD-01.1/report.json"
            row = stages.read(report)
            row["status"] = "Accepted"
            stages.write(report, row)
            with self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
                stages.check(output, verify_current=False)

    def test_immutable_stage_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "overwrite"):
                stages.freeze(Path(directory))

    def test_file_record_refuses_paths_outside_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                stages.file_record(stages.ROOT / stages.PLAN, Path(directory))


if __name__ == "__main__":
    unittest.main()
