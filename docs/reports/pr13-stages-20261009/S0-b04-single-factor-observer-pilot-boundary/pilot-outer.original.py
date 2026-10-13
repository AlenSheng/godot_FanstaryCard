import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B04-single-factor-pilot-r1-20261013';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;meta=json.loads((E/'inputs.original.json').read_bytes());IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def guard(start=False):
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert m>=500000000+(1088*1024**2 if start else 0) and s.f_bavail*s.f_frsize>=.15*s.f_blocks*s.f_frsize+(256*1024**2 if start else 0);return {'at':time.time(),'memory_available_bytes':m,'root_free_fraction':s.f_bavail/s.f_blocks}
def frozen():
 for r in meta['runtime_files']:
  p=Path(meta['runtime_root'])/r['path'];assert p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 for r in meta['fixture_files']:
  p=W/'fixture'/r['name'];assert p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 assert not run(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','diff','--name-only',meta['compiled_source_sha'],meta['source_sha'],'--','server','protocol']).stdout.strip()
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';write(E/'started.original.json',{'PID':os.getpid(),'state':state,'pilot_only':True});frozen();until=time.monotonic()+3600
while True:
 st=json.loads(run(['python3',B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status']).stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service']
 if st['current'] is None and not others:
  try:guard(True);break
  except AssertionError:pass
 assert time.monotonic()<until,'Admission deadline';time.sleep(5)
out=E/'persistent-native-outputs';out.mkdir(mode=0o777);out.chmod(0o777);art=W/'artifacts';art.mkdir(mode=0o777);art.chmod(0o777);write(E/'admitted.original.json',{'guard':guard(True),'pilot_only':True,'formal_required_encounters':216000});cid=None;result={'ok':False,'pilot_only':True,'source_sha':meta['source_sha'],'MAIN_accepted':False}
def owned():
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER;return v
try:
 assert docker('inspect',OWNER,check=False).returncode!=0;cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-v',meta['runtime_root']+':/runtime:ro','-v',str(B/'work/pg9-r10b-complete-inputs/packages')+':/packages:ro','-v',str(W/'fixture')+':/fixture:ro','-v',str(E/'inner.original.py')+':/inner.py:ro','-v',str(E/'inputs.original.json')+':/meta.json:ro','-v',str(out)+':/evidence','-v',str(art)+':/artifacts',IMAGE,'python3','/inner.py').stdout.decode().strip();owned();docker('start',cid);deadline=time.monotonic()+1500
 while True:
  info=owned()
  if not info['State']['Running']:break
  assert time.monotonic()<deadline;sample=guard();assert sum(p.stat().st_size for root in [out,W] for p in root.rglob('*') if p.is_file())<256*1024**2
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
 try:frozen();result['inputs_unchanged']=True
 except Exception:result['inputs_unchanged']=False
 result['ok']=result['ok'] and removed and result['inputs_unchanged'];write(E/'result.original.json',result)
print(json.dumps({'ok':result['ok'],'pilot_only':True,'formal_acceptance':False}));raise SystemExit(0 if result['ok'] else 1)
