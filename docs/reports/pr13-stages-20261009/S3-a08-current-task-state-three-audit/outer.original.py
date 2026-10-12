import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence/A08-task-state-audit-r1-20261012');OWNER='pr13-audit-A08-task-state-r1-20261012';I=E/'inputs';O=E/'outputs';IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';manifest=json.loads((I/'input-manifest.original.json').read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,check=True):
 r=subprocess.run(a,capture_output=True,timeout=40)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*map(str,a)],**kw)
def verify():
 R=Path('/opt/fantasycard-github')
 for row in manifest['files']:
  p=I/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];blob=run(['git','-c','safe.directory='+str(R),'-C',str(R),'rev-parse',manifest['source_sha']+':'+row['path']]).stdout.decode().strip();assert blob==row['git_blob_sha1']
 assert sha(E/'fixture.original.py')==manifest['fixture_sha256']
def guard():
 memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert memory>=500000000+160*1024**2 and s.f_bavail/s.f_blocks>=.15
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'memory_available_bytes':memory,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
verify();state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';write(E/'started.original.json',{'PID':os.getpid(),'state':state,'guard':guard(),'at':time.time()});assert not O.exists();O.mkdir(mode=0o777);O.chmod(0o777);cid=None;v={'ok':False,'source_sha':manifest['source_sha'],'MAIN_accepted':False}
def owned():
 c=json.loads(docker('inspect',cid).stdout)[0];assert c['Id']==cid and c['Name']=='/'+OWNER and c['Config']['Labels'].get('codex.owner')==OWNER;return c
try:
 assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','128m','--memory-swap','128m','--cpus','0.2','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=16777216','--user','1000:1000','-v',str(I)+':/inputs:ro','-v',str(O)+':/output','-v',str(E/'fixture.original.py')+':/fixture.py:ro',IMAGE,'python3','/fixture.py').stdout.decode().strip();owned();write(E/'container-created.original.json',{'Id':cid,'owner':OWNER,'memory_mib':128,'network':'none','image':IMAGE});docker('start',cid);deadline=time.monotonic()+180
 while True:
  c=owned()
  if not c['State']['Running']:break
  assert time.monotonic()<deadline;guard();time.sleep(2)
 logs=docker('logs',cid);(O/'container.original.log').write_bytes(logs.stdout+logs.stderr);report=json.loads((O/'report.original.json').read_bytes()) if (O/'report.original.json').exists() else {};v.update(ok=c['State']['ExitCode']==0 and not c['State']['OOMKilled'] and report.get('ok') is True,exit_code=c['State']['ExitCode'],oom_killed=c['State']['OOMKilled'],report=report)
except Exception as error:v.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 removed=False
 if cid:
  try:
   c=owned()
   if c['State']['Running']:docker('stop','--time','10',cid)
   owned();docker('rm',cid);removed=True
  except Exception as error:v['cleanup_error']=str(error)
 v['owned_container_removed']=removed
 try:verify();v['source_inputs_match_git']=True
 except Exception as error:v.update(source_inputs_match_git=False,source_error=str(error))
 v['ok']=v['ok'] and removed and v['source_inputs_match_git'];v['native_clean']=v['ok'];write(E/'result.original.json',v)
print(json.dumps(v));raise SystemExit(0 if v['ok'] else 1)
