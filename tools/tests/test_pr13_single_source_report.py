"""Cross-view provenance and real CLI rejection for single-source reports."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.pr13_single_source_report import build_model, create_bundle, validate_bundle
from tools.pr13_audit_replay import REDLINES


class SingleSourceReportTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory) / 'raw'; root.mkdir()
        events = [dict(run_id='run',client_id='client',process_epoch='epoch',event_seq=i,cycle_id='client:1',match_id='match',at_unix_ms=at,event_type=kind)
                  for i,at,kind in [(1,99,'settlement.acknowledged'),(2,110,'cycle.completed')]]
        raw = b''.join((json.dumps(x)+'\n').encode() for x in events); (root/'events.jsonl').write_bytes(raw)
        manifest = dict(files=[dict(path='events.jsonl',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())])
        return root, manifest, dict(run_id='run',stop_ms=100,final_ms=200)

    def test_all_presentations_share_the_same_cutoff_totals(self):
        with tempfile.TemporaryDirectory() as d:
            root,manifest,options = self.fixture(d); output=Path(d)/'report';create_bundle(root,manifest,output,**options)
            model=json.loads((output/'model.json').read_bytes());summary=json.loads((output/'summary.json').read_bytes());distribution=json.loads((output/'distribution.json').read_bytes())
            self.assertEqual([r['completed_cycles'] for r in summary],[0,1,1])
            for row in summary:
                self.assertEqual(row['completed_cycles'],sum(x['completed_cycles'] for x in distribution if x['cutoff']==row['cutoff']))
                self.assertEqual(row['completed_cycles'],model['audit']['derived'][row['cutoff']]['completed_cycles'])
            self.assertIn('| final | 1 | 1 |',(output/'report.md').read_text())
            self.assertEqual(model['contexts'],[dict(run_id='run',client_id='client',process_epoch='epoch')])
            self.assertFalse(model['audit']['current_acceptance'])

    def test_different_output_locations_have_identical_bytes_and_leave_raw_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root,manifest,options=self.fixture(d);before=(root/'events.jsonl').read_bytes()
            one=create_bundle(root,manifest,Path(d)/'one',**options);two=create_bundle(root,manifest,Path(d)/'two',**options)
            self.assertEqual(one,two);self.assertEqual((root/'events.jsonl').read_bytes(),before)

    def test_edited_summary_or_model_cannot_become_the_authority(self):
        for filename in ['summary.json','model.json']:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as d:
                root,manifest,options=self.fixture(d);out=Path(d)/'out';create_bundle(root,manifest,out,**options)
                value=json.loads((out/filename).read_bytes())
                if filename=='model.json':value['audit']['derived']['final']['completed_cycles']+=1
                else:value[-1]['completed_cycles']+=1
                (out/filename).write_text(json.dumps(value))
                with self.assertRaises(ValueError):validate_bundle(root,manifest,out,**options)

    def test_legacy_has_separate_views_and_retains_redlines_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root,manifest,options=self.fixture(d);current=Path(d)/'current';legacy=Path(d)/'legacy'
            original=create_bundle(root,manifest,current,**options);create_bundle(root,manifest,legacy,**options,algorithm='legacy-accounting')
            self.assertEqual(json.loads((legacy/'model.json').read_bytes())['audit']['legacy_redlines'],REDLINES)
            self.assertTrue(all((current/name).read_bytes()==raw for name,raw in original.items()))
            with self.assertRaises(ValueError):create_bundle(root,manifest,current,**options,algorithm='legacy-accounting')

    def test_foreign_run_or_changed_raw_cannot_generate_views(self):
        with tempfile.TemporaryDirectory() as d:
            root,manifest,options=self.fixture(d)
            with self.assertRaises(ValueError):build_model(root,manifest,**dict(options,run_id='foreign'))
            (root/'events.jsonl').write_bytes(b'changed')
            with self.assertRaises(ValueError):create_bundle(root,manifest,Path(d)/'out',**options)
            self.assertFalse((Path(d)/'out').exists())

    def test_actual_cli_rejects_a_single_edited_body_count(self):
        with tempfile.TemporaryDirectory() as d:
            root,manifest,options=self.fixture(d);out=Path(d)/'out';mf=Path(d)/'manifest.json';mf.write_text(json.dumps(manifest))
            tool=Path(__file__).resolve().parents[1]/'pr13_single_source_report.py'
            common=[sys.executable,'-B',str(tool),'--input',str(root),'--manifest',str(mf),'--run-id','run','--stop-ms','100','--final-ms','200']
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)
            generated=subprocess.run(common+['--output',str(out)],capture_output=True,timeout=30,creationflags=flags)
            self.assertEqual(generated.returncode,0,generated.stderr)
            body=(out/'report.md').read_text();self.assertIn('| final | 1 | 1 |',body);(out/'report.md').write_text(body.replace('| final | 1 | 1 |','| final | 1 | 2 |'))
            checked=subprocess.run(common+['--check',str(out)],capture_output=True,timeout=30,creationflags=flags)
            self.assertEqual(checked.returncode,3);self.assertEqual(json.loads(checked.stdout)['state'],'Rejected')


if __name__=='__main__':unittest.main()
