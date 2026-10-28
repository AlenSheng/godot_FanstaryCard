"""Readonly source quarantine, exact cutoff conservation and stable derivation."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.pr13_audit_replay import replay, check_files, validate_derived, REDLINES


class AuditReplayTests(unittest.TestCase):
    def fixture(self, root):
        rows = [dict(run_id='run', client_id='client', process_epoch='epoch', event_seq=i,
                     cycle_id='client:1', match_id='match', at_unix_ms=at, event_type=kind)
                for i, at, kind in [(1, 99, 'settlement.acknowledged'), (2, 110, 'cycle.completed')]]
        path = root/'events.jsonl'
        path.write_bytes(''.join(json.dumps(row)+'\n' for row in rows).encode())
        return {'files': [{'path': path.name, 'bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}

    def test_matching_raw_allows_replay_and_has_event_level_tail_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            result=replay(root,manifest,stop_ms=100,final_ms=200)
            self.assertEqual(result['status'],'Derived')
            self.assertEqual(result['derived']['running']['completed_cycles'],0)
            self.assertEqual(result['derived']['drain']['completed_cycles'],1)
            self.assertEqual(result['event_differences'][1]['cutoff'],'drain')

    def test_mismatch_is_quarantined_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root); before=(root/'events.jsonl').read_bytes()
            manifest['files'][0]['sha256']='0'*64
            result=replay(root,manifest,stop_ms=100,final_ms=200)
            self.assertEqual(result['status'],'Blocked');self.assertFalse(result['raw_read'])
            self.assertEqual(result['files'][0]['state'],'HashMismatchQuarantined')
            self.assertEqual((root/'events.jsonl').read_bytes(),before)

    def test_manifest_only_never_claims_original_raw_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root);(root/'events.jsonl').unlink()
            result=replay(root,manifest,stop_ms=100,final_ms=200)
            self.assertEqual(result['status'],'Blocked');self.assertFalse(result['raw_read'])
            self.assertIsNone(result['derived'])

    def test_same_cutoff_claim_is_checked_instead_of_overwriting_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            result=replay(root,manifest,stop_ms=100,final_ms=200,
                          claimed_totals={'running':{'completed_cycles':1}})
            self.assertEqual(result['status'],'InvalidEvidence')
            self.assertEqual(result['derived']['running']['completed_cycles'],0)

    def test_clients_and_failed_checks_keep_different_denominators(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            checks=[{'client_id':str(i),'passed':False} for i in range(52)]
            checks += [{'client_id':str(i),'passed':False} for i in range(25)]
            result=replay(root,manifest,stop_ms=100,final_ms=200,checks=checks)
            self.assertEqual(result['check_denominators'],{'failed_clients':52,'failed_checks':77})

    def test_manual_total_edit_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            result=replay(root,manifest,stop_ms=100,final_ms=200);edited=copy.deepcopy(result)
            edited['derived']['final']['completed_cycles']+=1
            with self.assertRaises(ValueError):validate_derived(edited,result)

    def test_same_raw_and_algorithm_are_byte_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            first=replay(root,manifest,stop_ms=100,final_ms=200)
            second=replay(root,manifest,stop_ms=100,final_ms=200)
            self.assertEqual(json.dumps(first,sort_keys=True).encode(),json.dumps(second,sort_keys=True).encode())

    def test_legacy_is_separate_and_retains_original_redlines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            current=replay(root,manifest,stop_ms=100,final_ms=200)
            legacy=replay(root,manifest,stop_ms=100,final_ms=200,algorithm='legacy-accounting')
            self.assertNotEqual(current['algorithm'],legacy['algorithm'])
            self.assertEqual(legacy['legacy_redlines'],REDLINES)
            self.assertFalse(legacy['current_acceptance'])

    def test_actual_legacy_consumer_keeps_its_context_404_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root); path=root/'events.jsonl'
            rows=[json.loads(x) for x in path.read_text(encoding='utf8').splitlines()]
            for i,status in enumerate([404,503],3):
                rows.append(dict(rows[0],event_seq=i,at_unix_ms=150,type='http',event_type='http',
                                 path='/api/v1/settlements/context',duration_ms=10,status=status,ok=False))
            path.write_bytes(''.join(json.dumps(r)+'\n' for r in rows).encode())
            manifest['files'][0].update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            legacy=replay(root,manifest,stop_ms=100,final_ms=200,algorithm='legacy-accounting')
            self.assertEqual(legacy['legacy_request_statistics']['sample_count'],1)
            self.assertEqual(legacy['legacy_request_statistics']['error_count'],1)

    def test_outside_path_and_unbounded_replay_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root)
            manifest['files'][0]['path']='../outside.jsonl'
            with self.assertRaises(ValueError):check_files(root,manifest)
            for budget in (True,0,1000001):
                with self.assertRaises(ValueError):replay(root,self.fixture(root),stop_ms=100,final_ms=200,max_events=budget)

    def test_matching_hash_with_bad_json_is_invalid_evidence_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); manifest=self.fixture(root);path=root/'events.jsonl'
            path.write_bytes(b'{broken\n');manifest['files'][0].update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            result=replay(root,manifest,stop_ms=100,final_ms=200)
            self.assertEqual(result['status'],'InvalidEvidence')
            self.assertEqual(result['raw_errors'][0]['line'],1)
            self.assertEqual(path.read_bytes(),b'{broken\n')


if __name__=='__main__':unittest.main()
