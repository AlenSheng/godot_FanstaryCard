"""A saved remote accepted status cannot turn a lost SSH session into success."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import deployment as d
import ship
from test_controls import manifest,SOURCE,CONTROL,BASELINE,OLD


class ShippingOutcome(unittest.TestCase):
    def test_failed_transport_keeps_unknown_even_with_remote_accepted_file(self):
        previous=Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            try:
                os.chdir(root)
                artifact=root/'image-artifact';artifact.mkdir()
                trusted=root/'trusted/tools/cloud';trusted.mkdir(parents=True)
                (trusted/'remote_deploy.py').write_text('mock controller')
                (trusted/'deployment.py').write_text('mock validation')
                (artifact/'image.tar.gz').write_bytes(b'mock archive')
                (artifact/'image-validation.json').write_text('{}')
                row=manifest()
                for path,field in ((artifact/'image.tar.gz','archive_sha256'),
                    (artifact/'image-validation.json','image_validation_sha256'),
                    (trusted/'remote_deploy.py','remote_sha256'),(trusted/'deployment.py','deployment_sha256')):
                    row[field]=d.file_hash(path)
                import hashlib
                row['health_sha256']=hashlib.sha256(b'mock health').hexdigest()
                (artifact/'manifest.json').write_text(json.dumps(row))
                remote={**row,'baseline_revision':BASELINE,'baseline_image_id':OLD,'checkout_sha':BASELINE,
                    'events':[{'status':'accepted','utc_epoch':1}],'status':'accepted',
                    'backup':{'name':f'actions-21-1-before-{SOURCE}.dump','sha256':'d'*64,'bytes':12}}
                def transfer(args,**kwargs):
                    if args[0]=='scp' and any('/result.json' in str(value) for value in args):
                        Path(args[-1]).write_text(json.dumps(remote))
                    return subprocess.CompletedProcess(args,0)
                def health(updater,path):Path(path).write_text('mock health')
                context={'GITHUB_RUN_ID':'21','GITHUB_RUN_ATTEMPT':'1','COMMIT_SHA':SOURCE,'GITHUB_SHA':CONTROL,
                    # Deliberately invalid fixture data; no real key is created/read.
                    'TEST_SERVER_SSH_KEY':'MOCK_ONLY_NOT_A_KEY',
                    'TEST_SERVER_KNOWN_HOSTS':'43.172.70.182 ssh-ed25519 MOCK_PUBLIC_DATA'}
                with patch.dict(os.environ,context,clear=True),patch.object(ship,'extract_health',side_effect=health), \
                     patch.object(ship,'validate_image_proof'),patch.object(ship.subprocess,'run',side_effect=transfer), \
                     patch.object(ship,'supervise',side_effect=RuntimeError('connection lost')), \
                     patch('sys.stdout',new=io.StringIO()),self.assertRaises(RuntimeError):ship.main()
                evidence=root/'deploy-evidence'
                self.assertEqual(json.loads((evidence/'result.json').read_text())['status'],'accepted')
                self.assertEqual(json.loads((evidence/'shipping.json').read_text()),{'status':'unknown','recovery_required':True})
                self.assertTrue(json.loads((evidence/'runner.json').read_text())['recovery_required'])
            finally:os.chdir(previous)


if __name__=='__main__':unittest.main()
