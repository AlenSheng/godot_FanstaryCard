import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools.restore_pr13_register_snapshots import KIND, PREFIX, restore


class RegisterArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fc-register-archive-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "restore"
        self.name = PREFIX + "fixture/register.json"

    def archive(self, name=None, expected_sha=None):
        name = self.name if name is None else name
        payload = b'{"state":"historical-failure","accepted":false}\n'
        archive = self.root / "sample.tar.xz"
        with tarfile.open(archive, "w:xz") as stream:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            stream.addfile(info, io.BytesIO(payload))
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"kind": KIND,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "member_count": 1, "uncompressed_bytes": len(payload),
            "entries": [{"path": name, "bytes": len(payload),
                         "sha256": expected_sha or hashlib.sha256(payload).hexdigest()}]}))
        return archive, manifest, payload

    def test_exact_restore_preserves_failure_and_is_repeatable(self):
        archive, manifest, payload = self.archive()
        result = restore(archive, manifest, self.output)
        self.assertEqual((self.output / self.name).read_bytes(), payload)
        self.assertFalse(result["acceptance_granted"])
        repeated = restore(archive, manifest, self.output)
        self.assertEqual(repeated["restored"], [])
        self.assertEqual(repeated["already_present"], [self.name])

    def test_existing_other_bytes_are_not_overwritten(self):
        archive, manifest, _ = self.archive()
        target = self.output / self.name
        target.parent.mkdir(parents=True)
        target.write_bytes(b"keep this original")
        with self.assertRaisesRegex(ValueError, "existing snapshot differs"):
            restore(archive, manifest, self.output)
        self.assertEqual(target.read_bytes(), b"keep this original")

    def test_path_traversal_is_rejected_before_writes(self):
        archive, manifest, _ = self.archive("../outside/register.json")
        with self.assertRaisesRegex(ValueError, "Invalid register member path"):
            restore(archive, manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_member_hash_is_not_published(self):
        archive, manifest, _ = self.archive(expected_sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "snapshot SHA"):
            restore(archive, manifest, self.output)
        self.assertFalse((self.output / self.name).exists())
        self.assertEqual(list(self.output.rglob("*.restore-*")), [])

    def test_wrong_archive_is_rejected(self):
        archive, manifest, _ = self.archive()
        archive.write_bytes(archive.read_bytes() + b"different")
        with self.assertRaisesRegex(ValueError, "Archive identity"):
            restore(archive, manifest, self.output)

    def test_disk_floor_is_not_lowered(self):
        archive, manifest, _ = self.archive()
        usage = type("Usage", (), {"total": 100_000_000_000,
                                  "used": 96_000_000_000, "free": 4_000_000_000})()
        with patch("tools.restore_pr13_register_snapshots.shutil.disk_usage", return_value=usage):
            with self.assertRaisesRegex(ValueError, "3GB/5%"):
                restore(archive, manifest, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
