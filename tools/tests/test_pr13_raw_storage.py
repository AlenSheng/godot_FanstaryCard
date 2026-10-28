import gzip
import json
import tempfile
import unittest
from pathlib import Path

from tools.pr13_raw_storage import compress_raw
from tools.pr13_simulation_report import load_run
from tools.tests.test_pr13_simulation_contracts import fixture, row


class RawStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = [row(seed, profile) for seed in range(3) for profile in ('Baseline', 'TargetedO6Hp095')]
        fixture(self.root, self.rows)

    def test_compressed_evidence_preserves_native_bytes_matrix_and_summary(self):
        before = (self.root / 'encounters.jsonl').read_bytes(); summary = (self.root / 'summary.json').read_bytes()
        original = load_run(self.root)
        storage = compress_raw(self.root)
        self.assertFalse((self.root / 'encounters.jsonl').exists())
        self.assertEqual(before, gzip.decompress((self.root / 'encounters.jsonl.gz').read_bytes()))
        self.assertEqual(summary, (self.root / 'summary.native.json').read_bytes())
        after = load_run(self.root)
        self.assertEqual(original[0], after[0]); self.assertEqual(original[2], after[2])
        self.assertEqual(len(before), storage['uncompressed_bytes'])

    def test_corrupted_compressed_evidence_is_rejected(self):
        compress_raw(self.root); p = self.root / 'encounters.jsonl.gz'; raw = bytearray(p.read_bytes()); raw[-1] ^= 1; p.write_bytes(raw)
        with self.assertRaises(ValueError): load_run(self.root)

    def test_changed_uncompressed_hash_is_rejected(self):
        compress_raw(self.root); p = self.root / 'summary.json'; summary = json.loads(p.read_text())
        summary['RawSha256'] = '0' * 64; p.write_text(json.dumps(summary))
        with self.assertRaises(ValueError): load_run(self.root)

    def test_ambiguous_plain_and_compressed_or_escape_path_is_rejected(self):
        compress_raw(self.root); (self.root / 'encounters.jsonl').write_text('stale\n')
        with self.assertRaises(ValueError): load_run(self.root)
        (self.root / 'encounters.jsonl').unlink(); p = self.root / 'summary.json'; summary = json.loads(p.read_text())
        summary['RawStorage']['file'] = '../encounters.jsonl.gz'; p.write_text(json.dumps(summary))
        with self.assertRaises(ValueError): load_run(self.root)


if __name__ == '__main__': unittest.main()
