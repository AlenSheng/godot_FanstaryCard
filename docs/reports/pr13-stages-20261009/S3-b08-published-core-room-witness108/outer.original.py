import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B08-core-room-witness-r2-20261012';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;meta=json.loads((E/'inputs.original.json').read_bytes())
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(args,timeout=40,check=True):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*args,**kw):return run(['docker',*map(str,args)],**kw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen():
 for key,root in (('input_files','source'),('package_files','package_root')):
  for row in meta[key]:
   p=Path(meta[root])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 assert sha(E/'inner.original.py')==meta['inner_sha256']
 for row in meta['fixture_files']:
  p=W/'fixture'/row['path'];assert sha(p)==row['sha256'] and p.stat().st_size==row['bytes']
def guard(start=False):
 available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert available>=500000000+1088*1024**2*int(start) and s.f_bavail*s.f_frsize>=s.f_blocks*s.f_frsize*.15+256*1024**2*int(start);return {'available_memory_bytes':available,'available_root_bytes':s.f_bavail*s.f_frsize}
frozen();until=time.monotonic()+3600
while True:
 controller=B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py';st=json.loads(run(['python3',str(controller),'status']).stdout);busy=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in busy if l.split()[0]!=OWNER+'.service'];ready=st['current'] is None and not others
 if ready:
  try:guard(True);break
  except AssertionError:pass
 assert time.monotonic()<until,'Admission deadline; preserve current native handles';time.sleep(5)
unit=dict(x.split('=',1) for x in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert unit['MainPID']==str(os.getpid()) and unit['ActiveState']=='active';write(E/'started.original.json',{'actual_cloud_PID':os.getpid(),'systemd_unit':OWNER,'invocation_id':unit['InvocationID'],'guard':guard(True),'input_manifest_sha256':sha(E/'inputs.original.json'),'at':time.time()});artifacts=W/'artifacts';output=W/'native-output';artifacts.mkdir(mode=0o777);output.mkdir(mode=0o777);artifacts.chmod(0o777);output.chmod(0o777);cid=None;result={'ok':False,'implementation_source_sha':meta['implementation_source_sha'],'MAIN_accepted':False}
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
try:
 assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','NUGET_PACKAGES=/packages','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-v',meta['source']+':/work:ro','-v',meta['package_root']+':/packages:ro','-v',str(E/'inner.original.py')+':/inner.py:ro','-v',str(E/'inputs.original.json')+':/meta.json:ro','-v',str(W/'fixture')+':/fixture:ro','-v',str(artifacts)+':/artifacts','-v',str(output)+':/evidence',meta['SDK_image'],'env','-u','FANTASYCARD_TEST_POSTGRES','python3','/inner.py').stdout.decode().strip();owned();docker('start',cid);deadline=time.monotonic()+1500
 while True:
  info=owned()
  if not info['State']['Running']:break
  assert time.monotonic()<deadline;sample=guard();assert sum(p.stat().st_size for p in W.rglob('*') if p.is_file())<256*1024**2
  with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(5)
 logs=docker('logs',cid);(output/'container.original.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((output/'inner-result.original.json').read_bytes()) if (output/'inner-result.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and inner.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 removed=False
 if cid:
  try:
   info=owned()
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned();docker('rm',cid);removed=True
  except Exception as error:result['cleanup_error']=type(error).__name__
 result['owned_container_removed']=removed
 try:frozen();result['source_and_packages_unchanged']=True
 except Exception:result['source_and_packages_unchanged']=False
 result['ok']=result['ok'] and removed and result['source_and_packages_unchanged'];write(E/'result.original.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
