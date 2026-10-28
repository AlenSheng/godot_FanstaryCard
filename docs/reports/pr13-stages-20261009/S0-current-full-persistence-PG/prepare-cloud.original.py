import hashlib,json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');R='/opt/fantasycard-github';S='docs/reports/pr13-stages-20261009/S0-current-full-persistence-PG';E=B/'evidence/Persistence-full-PG-r1-20261014';W=B/'work/Persistence-full-PG-r1-20261014'
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,*args])
HEAD=git('rev-parse','HEAD').decode().strip()
def blob(path):return git('show',HEAD+':'+path)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1048576),b''):h.update(block)
 return h.hexdigest()
assert not E.exists() and not W.exists()
p=json.loads(blob(S+'/plan.original.json'))
for key,root in [('source_files',Path(p['source_root'])),('runtime_files',Path(p['runtime_root']))]:
 for row in p[key]:
  path=root/row['path'];assert not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
  if key=='source_files':assert hashlib.sha256(blob(row['path'])).hexdigest()==row['sha256']
E.mkdir(mode=0o755);W.mkdir(mode=0o755)
for name in ['plan.original.json']+[row['path'] for row in p['work_files']]:
 (W/name).write_bytes(blob(S+'/'+name));(W/name).chmod(0o644)
for name in ['controller.original.py','scheduler.original.py']:(E/name).write_bytes(blob(S+'/'+name))
proof={'ok':True,'current_release_sha':HEAD,'source_members':328,'runtime_members':146,'actual_test_assembly_sha256':p['test_assembly_sha256'],'selector':p['selector'],'source_or_runtime_edited':False,'native_jobs_started':0,'MAIN_accepted':False}
(E/'prepared.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
