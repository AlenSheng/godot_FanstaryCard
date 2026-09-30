import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deployment as d
import remote_deploy as r
import ship
import install_tools as installer

SOURCE, CONTROL, BASELINE = 'a' * 40, 'b' * 40, 'c' * 40
NEW, OLD = 'sha256:' + '1' * 64, 'sha256:' + '2' * 64


def manifest():
    return dict(format=2, repository=d.REPOSITORY, source_sha=SOURCE, pr_number=13,
        controller_sha=CONTROL, run_id=21, run_attempt=1, environment=d.ENVIRONMENT,
        image_id=NEW, archive_sha256='d'*64, health_sha256='e'*64,
        remote_sha256='f'*64, deployment_sha256='0'*64, image_validation_sha256='9'*64,
        approval_mode=d.APPROVAL_MODE, approved_actor_id=d.OWNER_ID,
        confirmed_source_sha=SOURCE, restart_confirmed=True,
        rollback_baseline_sha=BASELINE, rollback_compatibility_confirmed=True)


def pr():
    return {'number':13, 'state':'open', 'head':{'repo':{'full_name':d.REPOSITORY}, 'sha':SOURCE},
            'base':{'repo':{'full_name':d.REPOSITORY}, 'ref':'release'}}


def env_config():
    return {'name':d.ENVIRONMENT, 'protection_rules':[],
            'deployment_branch_policy':{'custom_branch_policies':True, 'protected_branches':False}}


def branches():
    return {'total_count':1, 'branch_policies':[{'name':'release','type':'branch'}]}


class Inputs(unittest.TestCase):
    def test_full_shas_and_integer_types(self):
        for value in ('a'*39, 'A'*40, SOURCE+'\n', None, 1, '$(id)', SOURCE+';true'):
            with self.subTest(value=value), self.assertRaises(ValueError): d.sha(value)
        for value in (True, False, 0, -1, '01', '1\n', '1.0', '1;id', None):
            with self.subTest(value=value), self.assertRaises(ValueError): d.positive_integer(value)
        self.assertEqual(d.positive_integer('19'),19)

    def test_moving_closed_fork_or_wrong_base(self):
        d.validate_pr(pr(),13,SOURCE)
        for change in ('fork','moved','closed','base','missing'):
            row=pr()
            if change=='fork':row['head']['repo']['full_name']='fork/repo'
            if change=='moved':row['head']['sha']=CONTROL
            if change=='closed':row['state']='closed'
            if change=='base':row['base']['ref']='main'
            if change=='missing':row['head']['repo']=None
            with self.subTest(change=change), self.assertRaises(ValueError):d.validate_pr(row,13,SOURCE)

    def test_live_release_policy_no_reviewers_in_authorized_mode(self):
        d.verify_environment(env_config(),branches())
        for kind in ('main','tag','wildcard','extra','pagination','unrestricted','protected'):
            e,b=env_config(),branches()
            if kind in ('main','wildcard'):b['branch_policies'][0]['name']='main' if kind=='main' else '*'
            if kind=='tag':b['branch_policies'][0]['type']='tag'
            if kind=='extra':b['branch_policies'].append({'name':'other','type':'branch'})
            if kind=='pagination':b['total_count']=2
            if kind=='unrestricted':e['deployment_branch_policy']=None
            if kind=='protected':e['deployment_branch_policy']['protected_branches']=True
            with self.subTest(kind=kind), self.assertRaises(ValueError):d.verify_environment(e,b)
        with self.assertRaises(ValueError):d.verify_environment(env_config(),branches(),'implicit_fallback')

    def test_preflight_owner_new_dispatch_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            context=dict(GITHUB_REPOSITORY=d.REPOSITORY,GITHUB_EVENT_NAME='workflow_dispatch',
                GITHUB_REF='refs/heads/release',GITHUB_SHA=CONTROL,GITHUB_ACTOR='AlenSheng',
                GITHUB_TRIGGERING_ACTOR='AlenSheng',GITHUB_ACTOR_ID=str(d.OWNER_ID),
                GITHUB_RUN_ID='21',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(root/'output'),
                TEST_DEPLOY_ENABLED='true',TEST_DEPLOY_APPROVAL_MODE=d.APPROVAL_MODE,
                TEST_DEPLOY_APPROVED_WORKFLOW_SHA=CONTROL,PR_NUMBER='13',COMMIT_SHA=SOURCE,
                CONFIRM_SOURCE_SHA=SOURCE,CONFIRM_RESTART='true',ROLLBACK_BASELINE_SHA=BASELINE,
                CONFIRM_ROLLBACK_COMPATIBILITY='true')
            def api(path):
                if not path:return {'full_name':d.REPOSITORY,'default_branch':'main','owner':{'id':d.OWNER_ID}}
                if path=='/pulls/13':return pr()
                if path.endswith('deployment-branch-policies'):return branches()
                return env_config()
            with patch.dict(os.environ,context,clear=True),patch.object(d,'api',side_effect=api):
                d.preflight(root/'evidence.json')
                evidence=json.loads((root/'evidence.json').read_text())
                self.assertEqual(evidence['approval_mode'],'owner_dispatch')
                for key,bad in [('GITHUB_REF','refs/heads/main'),('GITHUB_ACTOR_ID','1'),
                    ('GITHUB_TRIGGERING_ACTOR','collaborator'),('GITHUB_EVENT_NAME','push'),
                    ('GITHUB_RUN_ATTEMPT','2'),('CONFIRM_RESTART','false'),
                    ('CONFIRM_SOURCE_SHA',CONTROL),('TEST_DEPLOY_ENABLED','false'),
                    ('TEST_DEPLOY_APPROVED_WORKFLOW_SHA',SOURCE),('CONFIRM_ROLLBACK_COMPATIBILITY','false')]:
                    with self.subTest(key=key),patch.dict(os.environ,{key:bad}),self.assertRaises(ValueError):d.preflight(root/'invalid.json')
                with patch.object(d,'api',side_effect=PermissionError('API inaccessible')),self.assertRaises(PermissionError):d.preflight(root/'invalid.json')
            self.assertNotIn('GH_TOKEN',evidence)

    def test_manifest_tampering_and_attempt_identity(self):
        row=manifest();d.validate_manifest(row,SOURCE,21,1,CONTROL)
        for key,value in [('source_sha',CONTROL),('run_id',True),('run_attempt',2),
            ('controller_sha',SOURCE),('archive_sha256','bad'),('image_id','mutable:tag'),
            ('repository','fork/repo'),('approval_mode','reviewers'),('restart_confirmed',False),
            ('rollback_compatibility_confirmed',False),('unexpected','LEAK_SENTINEL')]:
            bad=copy.deepcopy(row);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):d.validate_manifest(bad,SOURCE,21,1,CONTROL)

    def test_api_artifact_provenance(self):
        row=dict(id=5,expired=False,name='tested-image-21-1',size_in_bytes=123,
                 digest='sha256:'+'a'*64,workflow_run={'id':21,'head_sha':CONTROL})
        d.verify_artifact(row,5,21,1,CONTROL)
        for key,value in [('name','tested-image-21-2'),('expired',True),('digest',None),('size_in_bytes',0)]:
            bad=copy.deepcopy(row);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):d.verify_artifact(bad,5,21,1,CONTROL)
        row['workflow_run']['head_sha']=SOURCE
        with self.assertRaises(ValueError):d.verify_artifact(row,5,21,1,CONTROL)

    def test_final_image_proof_required_before_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pre=root/'preflight.json';archive=root/'image.tar.gz'
            source={k:v for k,v in manifest().items() if k not in ('format','image_id','archive_sha256','health_sha256','remote_sha256','deployment_sha256','image_validation_sha256')}
            pre.write_text(json.dumps(source));archive.write_bytes(b'archive');(root/'health.sh').write_text('health')
            with patch.object(d.subprocess,'check_output',side_effect=[NEW,SOURCE]),self.assertRaises(FileNotFoundError):d.manifest(pre,archive,'test:image',root/'manifest.json')
            (root/'image-validation.json').write_text(json.dumps({'ok':False,'image_id':NEW,'source_sha':SOURCE}))
            with patch.object(d.subprocess,'check_output',side_effect=[NEW,SOURCE]),self.assertRaises(ValueError):d.manifest(pre,archive,'test:image',root/'manifest.json')

    def test_skip_or_missing_pg_tests_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'domain.trx').write_text('<TestRun><UnitTestResult outcome="Passed" testName="Domain"/></TestRun>')
            pg=root/'postgres.trx';pg.write_text('<TestRun><UnitTestResult outcome="Passed" testName="PostgresRuntimeIntegrationTests.Real"/></TestRun>')
            self.assertEqual(d.verify_tests(root),{'domain':1,'postgres':1})
            for content in ('<TestRun/>','<TestRun><UnitTestResult outcome="NotExecuted"/></TestRun>', '<TestRun><UnitTestResult outcome="Passed" testName="Other"/></TestRun>'):
                pg.write_text(content)
                with self.assertRaises(ValueError):d.verify_tests(root)


class Rollback(unittest.TestCase):
    def exercise(self,fail=None,external=True):
        images=[];statuses=[];markers=[];commit=[];state=[];finished=[]
        def apply(image):
            images.append(image)
            if fail=='partial' and image==NEW:raise RuntimeError('partial')
            if fail=='rollback' and image==OLD:raise RuntimeError('failed restore')
        def healthy():return not (fail=='health' and images[-1]==NEW)
        def record(status):
            statuses.append(status)
            if fail=='evidence' and status in ('accepted','rolling_back'):raise OSError('disk')
        def finalize(image):
            markers.append(image)
            if fail=='marker' and image==NEW:raise OSError('marker')
        def committed():
            commit.append(True)
            if fail=='commit':raise OSError('last accepted')
        def decision():
            if fail=='interrupt':raise RuntimeError('interrupted')
            return external and fail!='rollback'
        call=lambda:r.rollout(NEW,OLD,apply,healthy,record,finalize,decision,committed,
                              lambda:state.append(True),lambda:finished.append(True))
        if fail or not external:
            with self.assertRaises((RuntimeError,OSError)):call()
        else:call()
        return images,statuses,markers,commit,state,finished

    def test_acceptance_includes_external_boundary(self):
        result=self.exercise();self.assertEqual(result[0],[NEW]);self.assertEqual(result[1][-1],'accepted');self.assertEqual(result[3],[True])

    def test_every_failure_compensates_including_persistence(self):
        for fail in ('partial','health','marker','evidence','commit','interrupt'):
            with self.subTest(fail=fail):
                images,statuses,markers,commit,state,finished=self.exercise(fail)
                self.assertEqual(images,[NEW,OLD]);self.assertEqual(statuses[-1],'rolled_back');self.assertEqual(markers[-1],OLD);self.assertEqual(finished,[True])
        self.assertEqual(self.exercise(external=False)[0],[NEW,OLD])

    def test_failed_rollback_retains_pending(self):
        images,statuses,markers,commit,state,finished=self.exercise('rollback')
        self.assertEqual(statuses[-1],'rollback_failed');self.assertFalse(finished)

    def test_external_eof_timeout_and_partial_input_reject(self):
        for value in (b'',b'accept',b'rollback\n',b'bad\n'):
            read,write=os.pipe()
            with os.fdopen(read,'r') as stream:
                if value:os.write(write,value)
                os.close(write)
                self.assertFalse(r.external_decision(stream,0.1))
        read,write=os.pipe()
        with os.fdopen(read,'r') as stream:
            self.assertFalse(r.external_decision(stream,0.01));os.write(write,b'accept\n');self.assertTrue(r.external_decision(stream,0.1));os.close(write)

    def test_shared_lock_rejects_concurrent_controller(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(r,'LOCK',Path(folder)/'update.lock'):
            with r.deployment_lock():
                code='import sys;sys.path.insert(0,sys.argv[1]);import remote_deploy as r;from pathlib import Path;r.LOCK=Path(sys.argv[2]);\nwith r.deployment_lock():pass'
                result=subprocess.run([sys.executable,'-c',code,str(Path(r.__file__).parent),str(r.LOCK)],capture_output=True)
                self.assertNotEqual(result.returncode,0)
            with r.deployment_lock():pass

    def test_atomic_private_files_and_symlink_attack(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'marker';r.atomic_write(path,'new')
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            path.with_name('marker.tmp').symlink_to(path)
            with self.assertRaises(OSError):r.atomic_write(path,'bad')
            self.assertEqual(path.read_text(),'new')

    def test_final_evidence_strictly_rejects_secret_fields(self):
        row={**manifest(),'baseline_revision':BASELINE,'baseline_image_id':OLD,'checkout_sha':BASELINE,
             'events':[{'status':'rolled_back','utc_epoch':1}],'status':'rolled_back',
             'backup':{'name':f'actions-21-1-before-{SOURCE}.dump','sha256':'d'*64,'bytes':10}}
        ship.safe_result(row,manifest())
        row['env']='LEAK_SENTINEL'
        with self.assertRaises(ValueError):ship.safe_result(row,manifest())

    def test_real_transport_handshake_and_eof_compensation(self):
        for passed in (True,False):
            code='import sys;print("deployment_status=awaiting_external",flush=True);decision=sys.stdin.readline();print("deployment_status="+("accepted" if decision=="accept\\n" else "rolled_back"),flush=True);sys.exit(0 if decision=="accept\\n" else 1)'
            command=[sys.executable,'-c',code]
            with patch('sys.stdout',new=io.StringIO()):
                if passed:self.assertEqual(ship.supervise(command,lambda:(True,[{'passed':True}]),3),[{'passed':True}])
                else:
                    with self.assertRaises(RuntimeError):ship.supervise(command,lambda:(False,[]),3)
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'compensated'
            code='import sys;from pathlib import Path;print("deployment_status=awaiting_external",flush=True);sys.stdin.readline();Path(sys.argv[1]).write_text("rolled_back")'
            with patch('sys.stdout',new=io.StringIO()),self.assertRaises(RuntimeError):
                ship.supervise([sys.executable,'-c',code,str(marker)],lambda:(_ for _ in ()).throw(RuntimeError('cancel')),3)
            self.assertEqual(marker.read_text(),'rolled_back')

    def test_ssh_never_relaxes_host_validation_or_forwards_agent(self):
        options=ship.ssh_options(Path('/fake/key'),Path('/fake/known'))
        for required in ('StrictHostKeyChecking=yes','IdentitiesOnly=yes','ForwardAgent=no','GlobalKnownHostsFile=/dev/null','PasswordAuthentication=no'):
            self.assertIn(required,options)


class Installer(unittest.TestCase):
    def test_corrupt_download_never_installs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cached=root/'cache';cached.mkdir();(cached/'file').write_bytes(b'bad')
            response=io.BytesIO(b'wrong')
            with patch.dict(os.environ,{'FANTASYCARD_CLOUD_DOWNLOAD_CACHE':str(cached)}),patch.object(installer.urllib.request,'urlopen',return_value=response),self.assertRaises(ValueError):
                installer.download({'url':'https://example.invalid/file','algorithm':'sha256','digest':'0'*64},root/'file')
            self.assertFalse((root/'file').exists());self.assertFalse((root/'file.download').exists())

    def test_zip_traversal_or_unexpected_layout_rejected(self):
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside','bad')
            with self.assertRaises(ValueError):installer.extract_zip(archive,root/'out')
            self.assertFalse((root/'outside').exists())

    def test_failed_staged_install_keeps_previous_tool(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'downloads').mkdir();(base/'dotnet').mkdir();(base/'dotnet'/'original').write_text('keep')
            def failed(*args):raise RuntimeError('extract interrupted')
            with patch.object(installer,'download'),self.assertRaises(RuntimeError):
                installer.install(base,'dotnet',[{'url':'https://example.invalid/file','digest':'d'*64}],failed,'binary','1.0')
            self.assertEqual((base/'dotnet'/'original').read_text(),'keep')



class ImageProofAndCancellation(unittest.TestCase):
    def test_incomplete_final_runtime_proof_rejected(self):
        proof=dict(ok=True,source_sha=SOURCE,image_id=NEW,
          assemblies={name:'a'*64 for name in ('FantasyCard.Contracts.dll','FantasyCard.Domain.dll','FantasyCard.Server.dll')},
          tests=dict(total=20,passed=20,failed=0,notExecuted=0),runtime_uid='1000',
          restart_test_passed=True,database_outage=dict(ready=503,live=200,recovered=200),
          production_local_auth_status=404,cleanup_ok=True)
        d.validate_image_proof(proof,NEW,SOURCE)
        for field,bad in [('runtime_uid','0'),('restart_test_passed',False),('database_outage',{}),
                          ('production_local_auth_status',200),('cleanup_ok',False),('assemblies',{})]:
            row=copy.deepcopy(proof);row[field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):d.validate_image_proof(row,NEW,SOURCE)
        proof['tests']['notExecuted']=1
        with self.assertRaises(ValueError):d.validate_image_proof(proof,NEW,SOURCE)

    def test_sigterm_rolls_back_and_repeated_signal_does_not_interrupt_restore(self):
        images=[];status=[]
        def interrupted(sig,frame):raise RuntimeError('SIGTERM')
        previous=signal.signal(signal.SIGTERM,interrupted)
        def apply(image):
            images.append(image)
            if image==OLD:os.kill(os.getpid(),signal.SIGTERM)
        try:
            with self.assertRaises(RuntimeError):
                r.rollout(NEW,OLD,apply,lambda:True,status.append,lambda image:None,
                    lambda:os.kill(os.getpid(),signal.SIGTERM),lambda:None,lambda:None,lambda:None)
            self.assertEqual(images,[NEW,OLD]);self.assertEqual(status[-1],'rolled_back')
            self.assertIs(signal.getsignal(signal.SIGTERM),interrupted)
        finally:signal.signal(signal.SIGTERM,previous)

    def test_runner_deadline_requests_eof_and_waits_for_compensation(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'rollback'
            code='import sys;from pathlib import Path;print("deployment_status=preflight",flush=True);sys.stdin.readline();Path(sys.argv[1]).write_text("rolled_back")'
            with patch('sys.stdout',new=io.StringIO()),self.assertRaises(TimeoutError):
                ship.supervise([sys.executable,'-c',code,str(marker)],lambda:(True,[]),0.05)
            self.assertEqual(marker.read_text(),'rolled_back')

if __name__=='__main__':unittest.main()
