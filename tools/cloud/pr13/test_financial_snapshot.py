import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.cloud.pr13 import financial_snapshot as capture


class OwnedFinancialSnapshotTests(unittest.TestCase):
    def test_outside_or_existing_output_is_rejected_before_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory);root=base/'live-evidence';root.mkdir()
            existing=root/'existing.json';existing.write_text('original')
            with patch.object(capture.isolated_runtime,'BASE',base), patch.object(capture.isolated_runtime,'owned') as owned:
                for path in [base/'outside.json',existing]:
                    with self.assertRaises(ValueError):capture.capture({},path,'before')
                owned.assert_not_called()
            self.assertEqual(existing.read_text(),'original')

    def test_unowned_database_blocks_query_and_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);target=base/'live-evidence/snapshot.json'
            with patch.object(capture.isolated_runtime,'BASE',base), \
                    patch.object(capture.isolated_runtime,'owned',side_effect=ValueError('foreign container')), \
                    patch.object(capture.isolated_runtime,'docker') as docker:
                with self.assertRaises(ValueError):capture.capture({},target,'before')
                docker.assert_not_called()
            self.assertFalse(target.exists())
