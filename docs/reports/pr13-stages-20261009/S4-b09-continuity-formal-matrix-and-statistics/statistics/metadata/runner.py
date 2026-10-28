import fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='b09-continuity-formal-statistics-r2-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;RAM=Path('/dev/shm/pr13-'+A)
IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';SOURCE='0d56ceccf526f6ae8973f57da152d67faf93a5d5'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(65536),b''):h.update(x)
 return h.hexdigest()
def command(args,timeout=30):return subprocess.run(args,check=True,capture_output=True,timeout=timeout)
def docker(*args):return command(['sudo','-n','docker',*map(str,args)])
def save(p,v):
 assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
def health():
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
def guard(start=False):
 mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));s=os.statvfs(B)
 assert mem>=500000000+(1280*1024**2 if start else 0) and s.f_bavail/s.f_blocks>=.15
 health();return {'at':time.time(),'memory_available_bytes':mem,'root_free_ratio':s.f_bavail/s.f_blocks}
def owned(cid):
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Config']['Labels']['codex.owner']==OWNER;return v
state=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(state['MainPID'])==os.getpid() and state['ActiveState']=='active' and os.environ.get('PR13_CONTINUITY_LEASE')==OWNER
meta=json.loads((E/'inputs.json').read_bytes());assert not RAM.exists() and not (E/'run-started.json').exists()
def verify():
 for row in meta['files']:assert sha(Path(row['source']))==row['sha256'] and Path(row['source']).stat().st_size==row['bytes']
verify();deadline=time.monotonic()+3600
while True:
 assert time.monotonic()<deadline,'Resource admission deadline; originals retained'
 try:
  with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   active=command(['systemctl','list-units','--state=active','--plain','--no-legend','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();assert not [x for x in active if x.split()[0]!=OWNER+'.service']
   guard(True);verify();save(E/'run-started.json',{'owner':OWNER,'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'input_sha256':sha(E/'inputs.json'),'frozen_native_source_sha':SOURCE})
   RAM.mkdir(mode=0o777);command(['sudo','-n','mount','-t','tmpfs','-o','size=268435456,mode=0777,nosuid,nodev',OWNER,str(RAM)]);break
 except (AssertionError,BlockingIOError):time.sleep(5)
cid=None;result={'ok':False,'attempt':A,'source_sha':SOURCE,'statistics_sha256':meta['statistics_sha256'],'MAIN_accepted':False,'formal_EXPERIMENT_accepted':False,'current_Godot_RENDER_pending':True}
try:
 args=['create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=67108864','--user','1000:1000','-e','HOME=/tmp/home','-v',str(W/'statistics.py')+':/frozen_analysis.py:ro','-v',str(W/'inner.py')+':/inner.py:ro','-v',str(RAM)+':/evidence','-v','/dev/shm/pr13-b09-continuity-formal-smoke-r3-20261011/native/Mage:/smoke:ro']
 for row in meta['units']:args+=['-v',row['directory']+':/inputs/'+row['hero']+'-'+str(row['start'])+':ro']
 cid=docker(*args,IMAGE,'python3','/inner.py').stdout.decode().strip();owned(cid);result['owned_container_id']=cid;docker('start',cid);until=time.monotonic()+1800
 while True:
  info=owned(cid)
  if not info['State']['Running']:break
  assert time.monotonic()<until,'Analysis budget exceeded';sample=guard()
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(3)
 logs=docker('logs',cid);(RAM/'container.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((RAM/'inner-result.json').read_bytes()) if (RAM/'inner-result.json').exists() else {}
 result.update(exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner);result['ok']=result['exit_code']==0 and not result['oom_killed'] and inner.get('ok') is True
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 if cid:
  info=owned(cid)
  if info['State']['Running']:docker('stop','--time','10',cid)
  owned(cid);docker('rm',cid);result['owned_container_removed']=True
 try:verify();result['source_inputs_unchanged']=True
 except Exception as e:result.update(ok=False,input_validation_error=str(e))
 health();save(E/'run-result.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
