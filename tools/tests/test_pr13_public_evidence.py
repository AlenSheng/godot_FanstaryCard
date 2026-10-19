"""Immutable public archive checks, including secret-safe rejection."""
import base64
import hashlib
import os
import zipfile
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.pr13_public_evidence import inspect_public,validated_files,validated_payloads,derived_identity
from tools.pr13_ci_evidence import classify_runs
from tools.pr13_acceptance_register import missing_case_profiles
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

    def test_offline_pass_cannot_discharge_mandatory_live_or_database(self):
        cases=[{'case_id':'case','status':'Passed','profiles_executed':['OFFLINE']}]
        missing=missing_case_profiles({'profiles':['OFFLINE','POSTGRES','LIVE']},cases)
        self.assertEqual(missing,{'case':['LIVE','POSTGRES']})
        self.assertEqual(missing_case_profiles({'profiles':['OFFLINE']},cases),{})

    def test_transport_phase_without_attributable_hook_stays_null(self):
        result=aggregate_window([{'operations':[],'telemetry':[{'type':'http_attempt','duration_ms':12,'status':200,'tls_handshake_ms':0}]}])
        tls=result['transport_phase_timings']['tls_handshake_ms']
        self.assertIsNone(tls['p95_ms']); self.assertEqual(tls['quality'],'unavailable')
        self.assertTrue(tls['missing_reason'])


    def test_private_text_encodings_and_formats_reject_without_echo(self):
        body=base64.b64encode(b'synthetic-only-credential-block-material-for-test').decode()
        pem='-----BEGIN OPENSSH PRIVATE KEY-----\n'+body+'\n-----END OPENSSH PRIVATE KEY-----\n'
        cases=[('key.md',pem),('key.json',json.dumps({'details':pem})),
               ('uri.md','postgresql://controlled:synthetic-only-uri-value@localhost/db'),
               ('header.log','Authorization: Basic '+base64.b64encode(b'controlled:synthetic-only-basic-value').decode()),
               ('settings.yml','api_key: synthetic-only-colon-value'),
               ('settings.txt','Host=localhost;Pwd=synthetic-only-pwd-value;')]
        with tempfile.TemporaryDirectory() as directory:
            for name,value in cases:
                with self.subTest(name=name):
                    path=Path(directory)/name;path.write_text(value,encoding='utf8')
                    with self.assertRaises(ValueError) as caught:inspect_public(path)
                    self.assertNotIn('synthetic-only',str(caught.exception));self.assertNotIn(body,str(caught.exception))

    def test_sudo_directory_and_masked_values_keep_real_password_checks(self):
        safe='    root : PWD=/ ; USER=root ; COMMAND=/usr/bin/docker inspect controlled-id'
        accepted=[('journal.log',safe),('journal.json',json.dumps({'MESSAGE':safe})),
                  ('ci.log','token=***'),('masked.json',json.dumps({'authorization':'<redacted>'}))]
        rejected=[safe+' API_KEY=synthetic-only-command-secret',
                  'Host=localhost;PWD=synthetic-only-password;',
                  'root : PWD=synthetic-only-password; USER=root ; COMMAND=/usr/bin/true']
        with tempfile.TemporaryDirectory() as directory:
            for name,value in accepted:
                path=Path(directory)/name;path.write_text(value,encoding='utf8');inspect_public(path)
            for value in rejected:
                path=Path(directory)/'credentials.log';path.write_text(value,encoding='utf8')
                with self.assertRaises(ValueError):inspect_public(path)

    def test_safe_references_certificates_and_null_fields_are_allowed(self):
        cases=[('workflow.yml','token: ${{ secrets.GITHUB_TOKEN }}\npassword: ${PGPASSWORD}\n'),
               ('safe.json',json.dumps({'token':None,'password':'','authorization':{},'tokens_count':512})),
               ('cert.md','-----BEGIN CERTIFICATE-----\nQUJDREVGR0hJSktMTU5PUFFSUlNUVVZXWFlaQUJDREVGRw==\n-----END CERTIFICATE-----')]
        with tempfile.TemporaryDirectory() as directory:
            for name,value in cases:
                path=Path(directory)/name;path.write_text(value,encoding='utf8');inspect_public(path)

    def test_same_file_and_hardlink_cannot_claim_independent_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            raw=Path(directory)/'raw.json';raw.write_bytes(b'{}')
            with self.assertRaises(ValueError):derived_identity(raw,raw)
            alias=Path(directory)/'alias.json';os.link(raw,alias)
            with self.assertRaises(ValueError):derived_identity(raw,alias)

    def test_case_variants_of_private_runtime_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'RUNTIME'/'safe.json';path.parent.mkdir();path.write_bytes(b'{}')
            entry={'path':'RUNTIME/safe.json','bytes':2,'sha256':hashlib.sha256(b'{}').hexdigest()}
            with self.assertRaises(ValueError):validated_files(root,[entry])

    def test_archive_writes_only_validated_bytes_if_source_changes_later(self):
        from tools import pr13_evidence_bundle as bundle
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);register=root/'reports';register.mkdir();path=root/'safe.json';path.write_bytes(b'{}')
            entry={'path':'safe.json','bytes':2,'sha256':hashlib.sha256(b'{}').hexdigest()}
            (register/'manifest.json').write_text(json.dumps({'source_sha':'a'*40,'files':[entry]}))
            original=bundle.validated_payloads
            def replace_after_snapshot(folder,entries):
                result=original(folder,entries)
                path.write_text(json.dumps({'access_token':'synthetic-only-replacement'}))
                return result
            output=root/'public.zip'
            with patch.object(bundle,'ROOT',root),patch.object(bundle,'validated_payloads',side_effect=replace_after_snapshot),patch('sys.argv',['bundle','--register',str(register),'--output',str(output)]),patch('builtins.print'):
                self.assertEqual(bundle.main(),0)
            with zipfile.ZipFile(output) as archive:self.assertEqual(archive.read('safe.json'),b'{}')

    def test_public_archive_rejects_opaque_types_without_breaking_source_hash_checks(self):
        from tools import pr13_evidence_bundle as bundle
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);register=root/'reports';register.mkdir();path=root/'proof.bin';path.write_bytes(b'PRIVATE_SYNTHETIC_OPAQUE_FIXTURE')
            entry={'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            # Source readers may verify arbitrary source bytes without publishing them.
            self.assertEqual(validated_files(root,[entry]),[path.resolve()])
            (register/'manifest.json').write_text(json.dumps({'source_sha':'a'*40,'files':[entry]}));output=root/'public.zip'
            with patch.object(bundle,'ROOT',root),patch('sys.argv',['bundle','--register',str(register),'--output',str(output)]):
                with self.assertRaises(ValueError):bundle.main()
            self.assertFalse(output.exists())

    def test_missing_source_identity_rejects_before_creating_bundle(self):
        from tools import pr13_evidence_bundle as bundle
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);register=root/'reports';register.mkdir();(register/'manifest.json').write_text('{"files":[]}');output=root/'public.zip'
            with patch.object(bundle,'ROOT',root),patch('sys.argv',['bundle','--register',str(register),'--output',str(output)]):
                with self.assertRaises(ValueError):bundle.main()
            self.assertFalse(output.exists())

if __name__ == '__main__': unittest.main()
