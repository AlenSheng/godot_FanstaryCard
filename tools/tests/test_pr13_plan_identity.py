import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.pr13_acceptance_register import plan_identity


class CrossPlatformPlanIdentityTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.path=self.root/'docs/plan.json'
        self.path.parent.mkdir(parents=True)
        self.git('init','-q')

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),'-c','core.autocrlf=false',
            '-c','user.name=PR13 fixture','-c','user.email=fixture@example.invalid',*args],stderr=subprocess.DEVNULL).decode().strip()

    def commit(self,payload):
        self.path.write_bytes(payload)
        self.git('add','docs/plan.json');self.git('commit','-qm','controlled plan')
        return self.git('rev-parse','HEAD')

    def test_cloud_lf_hash_is_accepted_for_same_git_specification_on_windows(self):
        payload=b'{\n  "require_capacity": true\n}\n'
        source=self.commit(payload)
        self.path.write_bytes(payload.replace(b'\n',b'\r\n'))
        recorded=hashlib.sha256(payload).hexdigest()
        result=plan_identity(self.path,dict(plan_sha256=recorded,source_sha=source),self.root)
        self.assertTrue(result['line_endings_equivalent'])
        self.assertEqual(source,result['verified_source_sha'])
        self.assertEqual(recorded,result['recorded_sha256'])
        self.assertNotEqual(recorded,result['current_bytes_sha256'])

    def test_specification_change_is_rejected_even_with_valid_historical_source(self):
        payload=b'{\n  "require_capacity": true\n}\n'
        source=self.commit(payload)
        self.path.write_bytes(payload.replace(b'true',b'false').replace(b'\n',b'\r\n'))
        with self.assertRaises(ValueError):
            plan_identity(self.path,dict(plan_sha256=hashlib.sha256(payload).hexdigest(),source_sha=source),self.root)

    def test_matching_newline_hash_cannot_be_attached_to_another_git_specification(self):
        wrong=self.commit(b'{\n  "require_capacity": false\n}\n')
        payload=b'{\n  "require_capacity": true\n}\n'
        self.commit(payload)
        self.path.write_bytes(payload.replace(b'\n',b'\r\n'))
        with self.assertRaisesRegex(ValueError,'not proven'):
            plan_identity(self.path,dict(plan_sha256=hashlib.sha256(payload).hexdigest(),source_sha=wrong),self.root)

    def test_missing_git_source_does_not_make_cross_platform_evidence_pass(self):
        payload=b'{\n  "require_capacity": true\n}\n'
        self.commit(payload)
        self.path.write_bytes(payload.replace(b'\n',b'\r\n'))
        with self.assertRaisesRegex(ValueError,'not proven'):
            plan_identity(self.path,dict(plan_sha256=hashlib.sha256(payload).hexdigest(),source_sha='0'*40),self.root)


if __name__=='__main__':unittest.main()
