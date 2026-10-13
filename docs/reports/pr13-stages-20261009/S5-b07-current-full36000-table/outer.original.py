import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B07-current-table-sequences-r1-20261013';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;meta=json.loads((E/'inputs.original.json').read_bytes());IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def frozen():
 for key,base in [('source_files','source_root'),('runtime_files','runtime_root'),('fixture_files','fixture_root')]:
  for row in meta[key]:
   p=Path(meta[base])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
 assert not run(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','diff','--name-only',meta['compiled_source_sha'],meta['implementation_source_sha'],'--','server','protocol']).stdout.strip()
def guard(start=False):
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert m>=500000000+(914*1024**2 if start else 0) and s.f_bavail*s.f_frsize>=.15*s.f_blocks*s.f_frsize+(768*1024**2 if start else 0)
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'at':time.time(),'memory_available_bytes':m,'root_free_bytes':s.f_bavail*s.f_frsize,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';write(E/'started.original.json',{'actual_cloud_PID':os.getpid(),'state':state,'at':time.time()});frozen();until=time.monotonic()+3600
while True:
 st=json.loads(run(['python3',B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status']).stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service']
 if st['current'] is None and not others:
  try:guard(True);break
  except AssertionError:pass
 assert time.monotonic()<until,'Admission deadline; existing handles preserved';time.sleep(5)
write(E/'admitted.original.json',{'guard':guard(True),'required_rows':36000,'logical_native_deadline_seconds':420,'total_native_deadline_seconds':1260,'independent_analysis_deadline_seconds':900});out=E/'persistent-native-outputs';art=W/'artifacts';out.mkdir(mode=0o777);out.chmod(0o777);art.mkdir(mode=0o777);art.chmod(0o777);cid=None;result={'ok':False,'implementation_source_sha':meta['implementation_source_sha'],'MAIN_accepted':False}
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
try:
 assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','850m','--memory-swap','850m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-v',meta['runtime_root']+':/runtime:ro','-v',meta['package_root']+':/packages:ro','-v',meta['fixture_root']+':/fixture:ro','-v',str(E/'inner.original.py')+':/inner.py:ro','-v',str(E/'inputs.original.json')+':/meta.json:ro','-v',str(out)+':/evidence','-v',str(art)+':/artifacts',IMAGE,'python3','/inner.py').stdout.decode().strip();owned();docker('start',cid);deadline=time.monotonic()+2520
 while True:
  info=owned()
  if not info['State']['Running']:break
  assert time.monotonic()<deadline;sample=guard();assert sum(p.stat().st_size for root in [out,W] for p in root.rglob('*') if p.is_file())<768*1024**2
  with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(3)
 logs=docker('logs',cid);(out/'container.original.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((out/'inner-result.original.json').read_bytes()) if (out/'inner-result.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and inner.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner)
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
 try:frozen();result['source_runtime_and_fixture_unchanged']=True
 except Exception:result['source_runtime_and_fixture_unchanged']=False
 result['ok']=result['ok'] and removed and result['source_runtime_and_fixture_unchanged'];write(E/'result.original.json',result)
print(json.dumps({'ok':result['ok'],'native_rows':result.get('inner',{}).get('native_rows',0),'owned_container_removed':removed}));raise SystemExit(0 if result['ok'] else 1)
