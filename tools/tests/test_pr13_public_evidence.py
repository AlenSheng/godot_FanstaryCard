"""Immutable public archive checks, including secret-safe rejection."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.pr13_public_evidence import inspect_public,validated_files,derived_identity
from tools.pr13_ci_evidence import classify_runs
from tools.gameplay_load_validation import aggregate_window

class PublicEvidenceTests(unittest.TestCase):
    def test_nested_credentials_are_rejected_without_echoing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            for data in ({'request':{'access_token':'private-fixture-value'}},{'ticket_body':{'status':'Ready'}},{'log':'Authorization: Bearer private-fixture-value'}):
                path.write_text(json.dumps(data),encoding='utf8')
                with self.assertRaises(ValueError) as error: inspect_public(path)
                self.assertNotIn('private-fixture-value',str(error.exception))

    def test_manifest_overwrite_and_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'result.json'; path.write_bytes(b'{}')
            entry={'path':path.name,'bytes':2,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            validated_files(root,[entry]); path.write_bytes(b'{"changed":true}')
            with self.assertRaises(ValueError): validated_files(root,[entry])
            with self.assertRaises(ValueError): validated_files(root,[dict(entry,path='../outside.json')])

    def test_parent_and_derivation_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'raw.jsonl'; derived=Path(directory)/'summary.json'
            parent.write_bytes(b'{"event_seq":1}\n'); derived.write_bytes(b'{"count":1}\n')
            record=derived_identity(parent,derived)
            self.assertEqual(record['relation'],'derived_from')
            self.assertNotEqual(record['parent']['sha256'],record['derived']['sha256'])
            self.assertFalse(record['original_overwritten'])

    def test_old_ci_success_cannot_satisfy_current_source(self):
        result=classify_runs('current',[{'head_sha':'old','status':'completed','conclusion':'success'}])
        self.assertEqual(result['historical_workflow_count'],1)
        self.assertFalse(result['all_returned_workflows_passed'])
        self.assertFalse(result['runtime_acceptance'])

    def test_transport_phase_without_attributable_hook_stays_null(self):
        result=aggregate_window([{'operations':[],'telemetry':[{'type':'http_attempt','duration_ms':12,'status':200,'tls_handshake_ms':0}]}])
        tls=result['transport_phase_timings']['tls_handshake_ms']
        self.assertIsNone(tls['p95_ms']); self.assertEqual(tls['quality'],'unavailable')
        self.assertTrue(tls['missing_reason'])

if __name__ == '__main__': unittest.main()
