"""Real Git object provenance for optional policy code; no game or network run."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.pr13_distributed_capacity import SOURCE_FILES, load_git_reference, main
from tools.pr13_authority_transitions import POLICY_SOURCE_FILES
from tools.pr13_distributed_load import GLOBAL50_SURPLUS_PROFILE


class PolicySourceFreezeTests(unittest.TestCase):
    def make_repo(self, policy=False):
        d=tempfile.TemporaryDirectory(prefix='pr13-policy-git-');self.addCleanup(d.cleanup)
        root=Path(d.name)
        def git(*args):
            p=subprocess.run(['git','-c','core.autocrlf=false',*args],cwd=root,capture_output=True,check=True)
            return p.stdout.decode().strip()
        git('init','-q')
        paths=SOURCE_FILES+('client/project.godot',)+(POLICY_SOURCE_FILES if policy else ())
        for name in paths:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((name+'\n').encode())
        git('add','-A')
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=NUL','commit','-qm','fixture')
        return root,git('rev-parse','HEAD')

    def test_legacy_commit_retains_original_control_set(self):
        root,head=self.make_repo()
        self.assertEqual(set(SOURCE_FILES),set(load_git_reference(root,head)['controls']))

    def test_policy_commit_freezes_all_new_imports_even_for_strict_default(self):
        root,head=self.make_repo(policy=True)
        self.assertEqual(set(SOURCE_FILES+POLICY_SOURCE_FILES),set(load_git_reference(root,head)['controls']))

    def test_new_profile_cannot_use_commit_without_policy_sources(self):
        root,head=self.make_repo()
        with self.assertRaisesRegex(ValueError,'incomplete_frozen_source'):
            load_git_reference(root,head,workload_profile=GLOBAL50_SURPLUS_PROFILE)

    def test_worktree_edits_cannot_rewrite_immutable_reference(self):
        root,head=self.make_repo(policy=True)
        before=load_git_reference(root,head)['controls']
        (root/POLICY_SOURCE_FILES[0]).write_text('changed\n',encoding='utf-8')
        self.assertEqual(before,load_git_reference(root,head)['controls'])

    def test_malformed_cli_input_returns_unaccepted_evidence_without_crashing(self):
        d=tempfile.TemporaryDirectory(prefix='pr13-policy-cli-');self.addCleanup(d.cleanup);root=Path(d.name)
        for i,payload in enumerate(['{','[]',json.dumps({'spec':True})]):
            p=root/(str(i)+'.input');out=root/(str(i)+'.json');p.write_text(payload,encoding='utf-8')
            self.assertEqual(3,main(['--input',str(p),'--source-repository',str(root),'--output',str(out)]))
            self.assertFalse(json.loads(out.read_text())['capacity_accepted'])


if __name__=='__main__':unittest.main()
