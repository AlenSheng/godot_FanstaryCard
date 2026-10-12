import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-missing-db-ci-audit-r1-20261012';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode());p.chmod(0o600)
def run(args,timeout=40,check=True):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*args,**kw):return run(['docker',*map(str,args)],**kw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen(meta):
 for key,root in (('input_files','source'),('package_files','package_root'),('supplemental_package_files','supplemental_package_root')):
  for row in meta[key]:
   p=Path(meta[root])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for row in meta['control_files']:
  p=E/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
def guard(start=False):
 available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert available>=500000000+1088*1024**2*int(start);assert s.f_bavail*s.f_frsize>=s.f_blocks*s.f_frsize*.15+256*1024**2*int(start);return {'memory_available_bytes':available,'root_free_bytes':s.f_bavail*s.f_frsize}
meta=json.loads((E/'inputs.original.json').read_bytes());frozen(meta);unit=dict(x.split('=',1) for x in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(unit['MainPID'])==os.getpid() and unit['ActiveState']=='active';write(E/'run-started.json',{'MainPID':os.getpid(),'invocation_id':unit['InvocationID'],'at':time.time(),'guard':guard(True),'input_manifest_sha256':sha(E/'inputs.original.json')});artifacts=W/'artifacts';output=W/'native-output';artifacts.mkdir(mode=0o777);output.mkdir(mode=0o777);artifacts.chmod(0o777);output.chmod(0o777);result={'ok':False,'production_source_sha':meta['production_source_sha'],'MAIN_accepted':False};cid=None
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
try:
 assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','NUGET_PACKAGES=/packages','-v',meta['source']+':/work:ro','-v',meta['package_root']+':/packages:ro','-v',str(E/'inputs.original.json')+':/meta.json:ro','-v',str(E/'inner.original.py')+':/inner.py:ro','-v',str(E/'control')+':/control:ro','-v',str(artifacts)+':/artifacts','-v',str(output)+':/evidence',meta['SDK_image'],'env','-u','FANTASYCARD_TEST_POSTGRES','python3','/inner.py').stdout.decode().strip();owned();docker('start',cid);deadline=time.monotonic()+1500
 while True:
  info=owned()
  if not info['State']['Running']:break
  assert time.monotonic()<deadline;sample=guard();assert sum(p.stat().st_size for p in W.rglob('*') if p.is_file())<256*1024**2
  with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(5)
 logs=docker('logs',cid);(output/'container.original.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((output/'inner-result.original.json').read_bytes()) if (output/'inner-result.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and inner.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner,actual_database_connection_environment_absent=True)
except Exception as error:result.update(ok=False,error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 removed=False
 if cid:
  try:
   info=owned()
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned();docker('rm',cid);removed=True
  except Exception as error:result['cleanup_error']=type(error).__name__
 result['owned_containers_removed']=removed
 try:frozen(meta);result['frozen_source_package_and_control_bytes_unchanged']=True
 except Exception:result['frozen_source_package_and_control_bytes_unchanged']=False
 result['ok']=result['ok'] and removed and result['frozen_source_package_and_control_bytes_unchanged'];write(E/'run-result.json',result)
print(json.dumps({'ok':result['ok'],'actual_skipped_database_cases':result.get('inner',{}).get('actual_db_tests_skipped'),'G_backup_pending':True}));raise SystemExit(0 if result['ok'] else 1)
