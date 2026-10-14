import hashlib,json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');R='/opt/fantasycard-github';HEAD=subprocess.check_output(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','rev-parse','HEAD']).decode().strip();S='docs/reports/pr13-stages-20261009/S0-a07-actual-numerical-baseline-gates-PG';E=B/'evidence/A07-gate-faults-PG-r1-20261014';W=B/'work/A07-gate-faults-PG-r1-20261014'
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,*args])
def blob(p):return git('show',HEAD+':'+p)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(65536),b''):h.update(data)
 return h.hexdigest()
assert git('rev-parse','HEAD').decode().strip()==HEAD and not E.exists() and not W.exists()
plan=json.loads(blob(S+'/plan.original.json'));source=Path(plan['source_root']);actual=[p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()];assert set(actual)=={r['path'] for r in plan['source_files']}
for row in plan['source_files']:
 p=source/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
E.mkdir();W.mkdir();E.chmod(0o755);W.chmod(0o755);C=W/'control';C.mkdir();C.chmod(0o755)
for name in ['plan.original.json']+[row['path'] for row in plan['work_files']]:
 (C/name).parent.mkdir(parents=True,exist_ok=True);(C/name).write_bytes(blob(S+'/'+name));(C/name).chmod(0o644)
for row in plan['config_files']:
 p=C/'published'/row['path'];p.parent.mkdir(parents=True,exist_ok=True);data=blob(row['path']);assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'];p.write_bytes(data);p.chmod(0o644)
subprocess.run(['cp','-al',str(source),str(W/'source')],check=True)
target=W/'source'/plan['source_override_path'];assert sha(target)==plan['original_test_source_sha256'];target.unlink();target.write_bytes((C/'test-override.original.cs').read_bytes());target.chmod(0o644);assert sha(target)==plan['modified_test_source_sha256']
(E/'controller.original.py').write_bytes(blob(S+'/controller.original.py'));(E/'controller.original.py').chmod(0o644)
(E/'scheduler.original.py').write_bytes(blob(S+'/scheduler.original.py'))
proof={'ok':True,'current_release_sha':HEAD,'original_source_files':328,'exact_declared_test_source_insertions':1,'shared_source_modified':False,'current_config_files':8,'controller_sha256':sha(E/'controller.original.py'),'plan_sha256':sha(C/'plan.original.json'),'native_jobs_started':0,'MAIN_accepted':False};(E/'prepared.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
