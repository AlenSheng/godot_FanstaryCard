import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_evidence as exporter


class EvidenceExport(unittest.TestCase):
    def test_all_profiles_keep_complete_named_reports_and_never_open_private_paths(self):
        for profile, allowed in exporter.PROFILES.items():
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); source = root/'source'; source.mkdir()
                for relative in allowed:
                    file = source/relative; file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text('ERROR: fixture failure retained\n完整诊断\n')
                private = ('runtime/data/godot/keystores/debug.keystore',
                           'runtime/config/godot/editor_settings.tres', '.env',
                           'production.pem', 'release.jks', 'signing.p12',
                           'credentials.json', 'token.log', '.aws/credentials',
                           '.ssh/id_rsa', 'http-fixture/runtime/credentials.json')
                for relative in private:
                    file = source/relative; file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text('PRIVATE_PATH_SENTINEL')
                original_open = os.open
                def guarded_open(path, *args, **kwargs):
                    self.assertNotIn(str(path), ('runtime', '.env', 'production.pem',
                        'release.jks', 'signing.p12', 'credentials.json', 'token.log', '.aws', '.ssh'))
                    return original_open(path, *args, **kwargs)
                with patch.object(exporter.os, 'open', side_effect=guarded_open):
                    result = exporter.export(source, root/'public', profile)
                self.assertFalse(result['missing']); self.assertFalse(result['rejected'])
                names = {str(p.relative_to(root/'public')) for p in (root/'public').rglob('*') if p.is_file()}
                self.assertEqual(names, set(allowed)|{'evidence-inventory.json'})
                for relative in allowed:
                    self.assertEqual((source/relative).read_bytes(), (root/'public'/relative).read_bytes())
                    row=next(row for row in result['files'] if row['name']==relative)
                    self.assertEqual(row['source_sha256'],hashlib.sha256((source/relative).read_bytes()).hexdigest())
                    self.assertEqual(row['relation'],'copied_from')

    def test_partial_failed_fixture_keeps_diagnostics_without_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'source'; source.mkdir()
            (source/'http-fixture').mkdir()
            (source/'http-fixture/import.log').write_text('Parse Error: deliberate failure\n')
            result = exporter.export(source, root/'public', 'cloud-local')
            self.assertEqual([x['name'] for x in result['files']], ['http-fixture/import.log'])
            self.assertTrue(result['missing'])
            self.assertIn('deliberate failure', (root/'public/http-fixture/import.log').read_text())

    def test_links_and_non_regular_allowed_names_are_rejected_without_reading(self):
        for attack in ('leaf-symlink', 'directory-symlink', 'hardlink', 'fifo'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);source=root/'source';source.mkdir(); private=root/'private';private.mkdir()
                secret=private/'import.log';secret.write_text('DO_NOT_READ_SENTINEL')
                if attack=='directory-symlink': (source/'http-fixture').symlink_to(private, target_is_directory=True)
                else:
                    (source/'http-fixture').mkdir();target=source/'http-fixture/import.log'
                    if attack=='leaf-symlink': target.symlink_to(secret)
                    elif attack=='hardlink': os.link(secret,target)
                    else: os.mkfifo(target)
                result=exporter.export(source,root/'public','cloud-local')
                self.assertTrue(result['rejected'])
                self.assertFalse((root/'public/http-fixture/import.log').exists())
                self.assertNotIn('DO_NOT_READ_SENTINEL',(root/'public/evidence-inventory.json').read_text())

    def test_missing_source_still_records_that_no_reports_ran(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);result=exporter.export(root/'absent',root/'public','cloud-local')
            self.assertFalse(result['files']);self.assertEqual(set(result['missing']),set(exporter.PROFILES['cloud-local']))

    def test_symlinked_source_ancestor_is_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);private=root/'private';private.mkdir();(private/'source').mkdir()
            (root/'alias').symlink_to(private,target_is_directory=True)
            with self.assertRaises(ValueError):exporter.export(root/'alias/source',root/'public','cloud-local')
            self.assertFalse((root/'public').exists())

    def test_stale_destination_never_emits_upload_path_or_deletes_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();destination=root/'public';destination.mkdir()
            existing=destination/'private.pem';existing.write_text('EXISTING_FILE_SENTINEL')
            output=root/'github-output'
            run=subprocess.run([sys.executable,exporter.__file__,'--profile','cloud-local','--source',str(source),'--destination',str(destination)],
                env=dict(os.environ,GITHUB_OUTPUT=str(output)),capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0);self.assertFalse(output.exists())
            self.assertEqual(existing.read_text(),'EXISTING_FILE_SENTINEL')

    def test_rejected_path_cli_fails_but_emits_only_safe_partial_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();(source/'http-fixture').mkdir()
            (source/'http-fixture/import.log').symlink_to(root/'never-read.pem')
            output=root/'github-output';destination=root/'public'
            run=subprocess.run([sys.executable,exporter.__file__,'--profile','cloud-local','--source',str(source),'--destination',str(destination)],
                env=dict(os.environ,GITHUB_OUTPUT=str(output)),capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertEqual(output.read_text(),'artifact_directory='+str(destination)+'\n')
            self.assertTrue(json.loads((destination/'evidence-inventory.json').read_text())['rejected'])

    def test_credential_text_is_redacted_without_losing_failure_diagnosis(self):
        value='CS1739: required argument missing\nBearer FAKE_TOKEN_SENTINEL\nGH_TOKEN=FAKE_ASSIGNMENT_SENTINEL\n"accessToken": "FAKE_JSON_SENTINEL"\n'
        result=exporter.scrub(value)
        self.assertIn('CS1739',result)
        for sentinel in ('FAKE_TOKEN_SENTINEL','FAKE_ASSIGNMENT_SENTINEL','FAKE_JSON_SENTINEL'):self.assertNotIn(sentinel,result)

    def test_noncredential_bearer_assertion_log_is_unchanged(self):
        value='HTTP fixture: ticket URL without bearer = true\n'
        self.assertEqual(exporter.scrub(value),value)



class CredentialScrub(unittest.TestCase):
    def test_basic_uri_pwd_and_private_blocks_do_not_leave_values(self):
        body=base64.b64encode(b'synthetic-only-private-block-material-in-export').decode()
        value='ERROR: original diagnosis retained\nAuthorization: Basic '+base64.b64encode(b'controlled:synthetic-only-basic-value').decode()+'\npostgresql://controlled:synthetic-only-uri-value@localhost/db\nHost=localhost;Pwd=synthetic-only-pwd-value;\n-----BEGIN PRIVATE KEY-----\n'+body+'\n-----END PRIVATE KEY-----\n'
        result=exporter.scrub(value)
        self.assertIn('ERROR: original diagnosis retained',result)
        self.assertNotIn('synthetic-only',result);self.assertNotIn(body,result)


if __name__=='__main__':unittest.main()
