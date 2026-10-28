import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

B = Path('/home/ubuntu/pr13-acceptance-20261009')
R = '/opt/fantasycard-github'
S = 'docs/reports/pr13-stages-20261009/S0-a08-actual-dirty-source-PG'
E = B/'evidence/A08-dirty-source-PG-r1-20261014'
W = B/'work/A08-dirty-source-PG-r1-20261014'

def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,*args])

def blob(path):
    return git('show',HEAD+':'+path)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

HEAD = git('rev-parse','HEAD').decode().strip()
assert not E.exists() and not W.exists()
plan = json.loads(blob(S+'/plan.original.json'))
source = Path(plan['source_root'])
assert set(p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()) == {r['path'] for r in plan['source_files']}
for row in plan['source_files']:
    p = source/row['path']
    assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
    assert hashlib.sha256(blob(row['path'])).hexdigest()==row['sha256']
E.mkdir(mode=0o755);W.mkdir(mode=0o755)
C = W/'control';C.mkdir(mode=0o755)
for name in ['plan.original.json']+[r['path'] for r in plan['work_files']]:
    (C/name).write_bytes(blob(S+'/'+name));(C/name).chmod(0o644)
for row in plan['config_files']:
    p = C/'published'/row['path'];p.parent.mkdir(parents=True,exist_ok=True)
    data = blob(row['path'])
    assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
    p.write_bytes(data);p.chmod(0o644)
subprocess.run(['cp','-al',str(source),str(W/'source')],check=True)
owned = W/'source'
assert not (owned/'.git').exists()
def owned_git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+str(owned),'-C',str(owned),*args])
owned_git('init','--initial-branch=pr13-owned-source-snapshot')
owned_git('add','-f','--',*[r['path'] for r in plan['source_files']])
owned_git('-c','user.name=PR13 Isolated QA','-c','user.email=pr13-isolated-qa@localhost',
          '-c','commit.gpgsign=false','commit','-m','Exact current release source projection; not a release commit')
assert not owned_git('status','--porcelain','--untracked-files=no').strip()
os.environ.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',
                  GIT_CONFIG_VALUE_0=str(owned),GIT_OPTIONAL_LOCKS='0')
spec = importlib.util.spec_from_file_location('actual_provenance',C/'gameplay_load_validation.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
clean = m.provenance(owned,(plan['source_override_path'],'server/config/generated/fantasycard.config.bytes'))
assert clean['git_dirty'] is False and clean['git_commit'] != plan['source_base_sha']
(C/'clean-source-provenance.original.json').write_bytes((json.dumps(clean,indent=2)+'\n').encode())
target = owned/plan['source_override_path']
assert sha(target)==plan['original_test_source_sha256']
target.unlink();target.write_bytes((C/'test-override.original.cs').read_bytes());target.chmod(0o644)
assert sha(target)==plan['modified_test_source_sha256']
assert owned_git('status','--porcelain','--untracked-files=no').decode().splitlines()==[' M '+plan['source_override_path']]
(E/'controller.original.py').write_bytes(blob(S+'/controller.original.py'))
(E/'scheduler.original.py').write_bytes(blob(S+'/scheduler.original.py'))
proof = {'ok':True,'current_release_sha':HEAD,'source_base_sha':plan['source_base_sha'],
    'owned_clean_snapshot_commit':clean['git_commit'],'owned_snapshot_is_release_commit':False,
    'original_source_files':328,'exact_declared_test_source_insertions':1,
    'shared_source_modified':False,'controller_sha256':sha(E/'controller.original.py'),
    'plan_sha256':sha(C/'plan.original.json'),'native_jobs_started':0,'MAIN_accepted':False}
(E/'prepared.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode())
print(json.dumps(proof))
