import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from validate_image import export_diagnostics


class Diagnostics(unittest.TestCase):
    def test_failure_logs_and_trx_are_exported_without_private_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'private';source.mkdir();destination=root/'diagnostics'
            (source/'results').mkdir()
            (source/'tests.log').write_text('CS1739: missing constructor parameter\nBearer TEST_TOKEN_SENTINEL\nGH_TOKEN=ASSIGNMENT_SENTINEL\n')
            (source/'results'/'domain.trx').write_text('<TestRun outcome="Failed"/>')
            for name in ('mapping.xml','state.json','secret.dump','test.dll','container.log'):(source/name).write_text('PRIVATE_SENTINEL')
            export_diagnostics(source,destination)
            exported=''.join(p.read_text() for p in destination.rglob('*') if p.is_file())
            self.assertIn('CS1739',exported);self.assertNotIn('TEST_TOKEN_SENTINEL',exported)
            self.assertNotIn('ASSIGNMENT_SENTINEL',exported);self.assertNotIn('PRIVATE_SENTINEL',exported)
            self.assertEqual({x['name'] for x in json.loads((destination/'inventory.json').read_text())},{'tests.log','results/domain.trx'})


if __name__=='__main__':unittest.main()
