"""Audit boundary tests: actual bytes, missing raw and outside-root links."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.pr13_historical_inventory_audit import inventory


class HistoricalInventoryAuditTests(unittest.TestCase):
    def test_matched_missing_and_wrong_bytes_stay_distinct_and_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'raw'
            raw.mkdir()
            (raw / 'match.jsonl').write_bytes(b'original\n')
            (raw / 'wrong.jsonl').write_bytes(b'changed\n')
            digest = hashlib.sha256(b'original\n').hexdigest()
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'files': [
                {'path': name, 'bytes': 9, 'sha256': digest}
                for name in ('match.jsonl', 'wrong.jsonl', 'missing.jsonl')]}))
            before = manifest.read_bytes()
            result = inventory(manifest, raw)
            self.assertEqual(result['counts'], {'Matched': 1, 'HashOrSizeMismatchQuarantined': 1, 'Missing': 1})
            self.assertFalse(result['all_raw_available_and_matching'])
            self.assertFalse(result['historical_totals_reconciled'])
            self.assertEqual(manifest.read_bytes(), before)
            self.assertEqual((raw / 'wrong.jsonl').read_bytes(), b'changed\n')

    def test_outside_root_and_broken_links_are_quarantined_without_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'raw'
            raw.mkdir()
            outside = root / 'outside.jsonl'
            outside.write_bytes(b'outside\n')
            try:
                (raw / 'outside.jsonl').symlink_to(outside)
                (raw / 'broken.jsonl').symlink_to(root / 'does-not-exist')
            except OSError as error:
                self.skipTest(str(error))
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'files': [
                {'path': name, 'bytes': 8, 'sha256': hashlib.sha256(b'outside\n').hexdigest()}
                for name in ('outside.jsonl', 'broken.jsonl')]}))
            result = inventory(manifest, raw)
            self.assertEqual(result['counts'], {'UnsafeTypeQuarantined': 2})
            self.assertTrue(all(not row['raw_read'] for row in result['files']))

    def test_duplicate_and_traversing_members_reject_the_whole_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'manifest.json'
            base = {'path': 'same.jsonl', 'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
            for rows in ([base, base], [{**base, 'path': '../outside.jsonl'}]):
                manifest.write_text(json.dumps({'files': rows}))
                with self.assertRaises(ValueError):
                    inventory(manifest, root / 'missing-root')


if __name__ == '__main__':
    unittest.main()
