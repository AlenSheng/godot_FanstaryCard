"""Server transaction fault injection with real files and simulated child commands."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import deployment as d
import remote_deploy as r
from test_controls import manifest, SOURCE, CONTROL, BASELINE, OLD, NEW


class RemoteTransaction(unittest.TestCase):
    def run_case(self, fault=None, decision=True, recover_after=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);app=root/'app';repo=root/'repo';state=app/'test-deploy';bundle=state/'incoming/21-1'
            bundle.mkdir(parents=True);(repo/'server').mkdir(parents=True)
            compose=repo/'server/compose.cloud.yaml';compose.write_text('fixture compose')
            env=repo/'server/.env';env.write_text('NEVER_READ_ENV_SENTINEL')
            (app/'deployed-git-commit').write_text(BASELINE+'\n');marker=app/'deployed-runtime-commit';marker.write_text(BASELINE+'\n')
            for name,content in [('image.tar.gz',b'image'),('health.sh',b'health'),('remote_deploy.py',b'remote'),('deployment.py',b'controller'),('image-validation.json',b'proof')]:
                (bundle/name).write_bytes(content)
            row=manifest()
            for name,field in [('image.tar.gz','archive_sha256'),('health.sh','health_sha256'),('remote_deploy.py','remote_sha256'),('deployment.py','deployment_sha256'),('image-validation.json','image_validation_sha256')]:
                row[field]=d.file_hash(bundle/name)
            if fault=='archive':(bundle/'image.tar.gz').write_bytes(b'tampered')
            if fault=='baseline':row['rollback_baseline_sha']='d'*40
            (bundle/'manifest.json').write_text(json.dumps(row))
            current=[OLD];mutations=[];backups=[];restores=[];records=[]
            if fault=='pending':(state/'pending.json').write_text('{}')
            original_atomic=r.atomic_write
            def atomic(path,value):
                records.append(path.name)
                if fault=='marker' and path==marker and value.strip()==SOURCE:raise OSError('marker failure')
                if fault=='accepted' and path.name=='last-accepted.json':raise OSError('evidence failure')
                return original_atomic(path,value)
            def capture(*args):
                args=list(map(str,args))
                if args[0]=='git':
                    if args[-3:]==['remote','get-url','origin']:return 'https://github.com/'+d.REPOSITORY+'.git'
                    if args[-1]=='FETCH_HEAD':return SOURCE
                    if args[-1]=='HEAD':return BASELINE
                if args[-1] in ('9'*64,OLD,NEW):
                    if args[-2]=='{{.Id}}':return args[-1]
                    if args[-2]=='{{.Image}}':return current[0]
                    if 'revision' in args[-2]:return SOURCE if (args[-1]==NEW or args[-1]=='9'*64 and current[0]==NEW) else BASELINE
                raise AssertionError(args)
            def run(*args,**kwargs):
                args=list(map(str,args))
                if args[0]=='git':
                    if fault=='compatibility' and 'diff' in args and BASELINE in args:raise subprocess.CalledProcessError(1,args)
                    return subprocess.CompletedProcess(args,0)
                if 'ps' in args:return subprocess.CompletedProcess(args,0,stdout='9'*64+'\n')
                if 'pg_dump' in args:
                    if fault=='backup':raise subprocess.CalledProcessError(1,args)
                    if fault!='empty_backup':kwargs['stdout'].write(b'PGDMP_fixture')
                    backups.append(kwargs['stdout'].name);return subprocess.CompletedProcess(args,0)
                if 'pg_restore' in args:
                    restores.append(args)
                    if fault=='backup_list':raise subprocess.CalledProcessError(1,args)
                    return subprocess.CompletedProcess(args,0)
                if 'up' in args:
                    chosen=(state/'active-image.yaml').read_text().split('image: ')[1].strip()
                    current[0]=chosen;mutations.append(chosen)
                    if fault=='partial' and chosen==NEW:raise subprocess.CalledProcessError(1,args)
                    if fault=='rollback' and chosen==OLD:raise subprocess.CalledProcessError(1,args)
                return subprocess.CompletedProcess(args,0)
            def child(*args,**kwargs):
                if fault=='health' and current[0]==NEW:return subprocess.CompletedProcess(args,1)
                return subprocess.CompletedProcess(args,0)
            clock=iter(range(0,10000,200))
            def guarded_read(path,*args,**kwargs):
                if path==env:raise AssertionError('Server .env must never be read')
                return original_read(path,*args,**kwargs)
            original_read=Path.read_text
            with contextlib.ExitStack() as stack:
                for name,value in [('APP',app),('REPO',repo),('COMPOSE',compose),('ENV_FILE',env),('LOCK',root/'lock')]:stack.enter_context(patch.object(r,name,value))
                stack.enter_context(patch('pwd.getpwuid',return_value=types.SimpleNamespace(pw_name='ubuntu')))
                stack.enter_context(patch.object(r,'capture',side_effect=capture));stack.enter_context(patch.object(r,'run',side_effect=run))
                stack.enter_context(patch.object(r,'atomic_write',side_effect=atomic));stack.enter_context(patch.object(r,'external_decision',return_value=decision))
                stack.enter_context(patch.object(r.subprocess,'run',side_effect=child));stack.enter_context(patch.object(r.time,'sleep'))
                stack.enter_context(patch.object(r.time,'monotonic',side_effect=lambda:next(clock)))
                stack.enter_context(patch.object(Path,'read_text',guarded_read));stack.enter_context(patch('sys.stdout',new=io.StringIO()))
                if fault or not decision:
                    with self.assertRaises((ValueError,RuntimeError,OSError,subprocess.CalledProcessError)):
                        with r.deployment_lock():r.deploy(bundle,SOURCE,21,1,CONTROL)
                else:
                    with r.deployment_lock():r.deploy(bundle,SOURCE,21,1,CONTROL)
                evidence=json.loads((bundle/'result.json').read_text()) if (bundle/'result.json').exists() else None
                pending=(state/'pending.json').exists()
                if recover_after and pending:
                    # Clear injected failure, but reuse the same pinned bundle.
                    fault=None
                    with self.assertRaises(RuntimeError):
                        with r.deployment_lock():r.deploy(bundle,SOURCE,21,1,CONTROL,recover=True)
                    self.assertFalse((state/'pending.json').exists());self.assertEqual(current[0],OLD)
                for backup in (app/'backups').glob('*.dump'):
                    self.assertEqual(backup.stat().st_mode & 0o777,0o600)
                    self.assertIn('21-1-before-',backup.name)
                self.assertTrue(all('--list' in row for row in restores),'Database restore is forbidden')
                if evidence:self.assertNotIn('NEVER_READ_ENV_SENTINEL',json.dumps(evidence))
                return current[0],mutations,marker.read_text().strip(),evidence,pending

    def test_complete_acceptance(self):
        current,mutations,marker,evidence,pending=self.run_case()
        self.assertEqual(current,NEW);self.assertEqual(marker,SOURCE);self.assertEqual(evidence['status'],'accepted');self.assertFalse(pending)

    def test_preflight_failures_never_activate_application(self):
        for fault in ('archive','baseline','pending','compatibility','backup','empty_backup','backup_list'):
            with self.subTest(fault=fault):self.assertEqual(self.run_case(fault)[1],[])

    def test_failed_health_partial_activation_and_marker_revert(self):
        for fault in ('health','partial','marker','accepted'):
            with self.subTest(fault=fault):
                current,mutations,marker,evidence,pending=self.run_case(fault)
                self.assertEqual(current,OLD);self.assertEqual(marker,BASELINE);self.assertEqual(evidence['status'],'rolled_back');self.assertFalse(pending)

    def test_external_rejection_reverts_before_acceptance(self):
        self.assertEqual(self.run_case(decision=False)[3]['status'],'rolled_back')

    def test_failed_rollback_blocks_next_deploy_and_can_recover(self):
        self.assertTrue(self.run_case('rollback',decision=False,recover_after=True)[4])

    def test_known_persistence_paths_are_blocked(self):
        for path in ('server/src/FantasyCard.Server/Rooms','server/src/FantasyCard.Domain',
                     'server/src/FantasyCard.Contracts','server/src/FantasyCard.Server/FantasyCard.Server.csproj'):
            self.assertIn(path,r.BLOCKED_PATHS)


if __name__=='__main__':unittest.main()
