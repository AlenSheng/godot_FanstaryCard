"""One cloud lease for the B09.4 natural-route development pilot."""
import fcntl,hashlib,json,os,re,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='b09-continuity-formal-smoke-r2-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;RAM=Path('/dev/shm/pr13-'+A)
IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';MEMORY=1024*1024**2;OUTPUT=256*1024**2;FLOOR=500000000
def require(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
 require(not p.exists(),'Preserve original evidence: '+str(p))
 with p.open('xb') as f:f.write((json.dumps(v,indent=2)+'\n').encode());f.flush();os.fsync(f.fileno())
def command(args,timeout=30):return subprocess.run(args,capture_output=True,timeout=timeout,check=True)
def docker(*a):return command(['sudo','-n','docker',*map(str,a)])
def health():
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:require(h.status==200,'Production health unavailable')
def guard(start=False):
 mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));s=os.statvfs(B);used=sum(p.stat().st_size for p in RAM.rglob('*') if p.is_file()) if RAM.exists() else 0
 require(mem>=FLOOR+(MEMORY+OUTPUT if start else 0) and s.f_bavail/s.f_blocks>=.15 and used<=OUTPUT,'Cloud resource floor exceeded');health();return {'at':time.time(),'memory_available_bytes':mem,'root_free_ratio':s.f_bavail/s.f_blocks,'owned_RAM_bytes':used}
def verify(meta):
 for prefix in ('source','runtime'):
  require(all((W/prefix/k).is_file() and not (W/prefix/k).is_symlink() and sha(W/prefix/k)==h for k,h in meta[prefix].items()),'Frozen '+prefix+' changed')
 require(sha(E/'inner.py')==meta['inner_sha256'] and sha(E/'runner.py')==meta['runner_sha256'],'Frozen driver changed')
def owned(cid):
 require(re.fullmatch('[0-9a-f]{64}',cid),'Exact container ID required');v=json.loads(docker('inspect',cid).stdout)[0];require(v['Id']==cid and v['Config']['Labels']['codex.owner']==OWNER,'Container ownership differs');return v
def run():
 require(os.environ.get('PR13_CONTINUITY_LEASE')==OWNER and os.name=='posix','Explicit Linux lease required')
 state=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());require(state['ActiveState']=='active' and int(state['MainPID'])==os.getpid(),'Exact live MainPID required')
 require(not RAM.exists() and not (E/'run-started.json').exists(),'Never restart previous/uncertain native attempt');meta=json.loads((E/'inputs.json').read_bytes());verify(meta);wait_until=time.monotonic()+3600
 while True:
  require(time.monotonic()<wait_until,'Resource admission observation deadline exceeded')
  try:
   with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    lines=command(['systemctl','list-units','--state=active','--plain','--no-legend','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[line for line in lines if line.split()[0]!=OWNER+'.service'];require(not others,'Observe other original native lease before starting')
    guard(True);verify(meta);write(E/'run-started.json',{'owner':OWNER,'source_sha':meta['release_sha'],'compiled_domain_source_sha':meta['compiled_domain_source_sha'],'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'input_sha256':sha(E/'inputs.json')})
    RAM.mkdir(mode=0o777);command(['sudo','-n','mount','-t','tmpfs','-o','size=268435456,mode=0777,nosuid,nodev',OWNER,str(RAM)]);break
  except (BlockingIOError,ValueError):time.sleep(5)
 cid=None;result={'ok':False,'attempt':A,'source_sha':meta['release_sha'],'compiled_domain_source_sha':meta['compiled_domain_source_sha'],'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False}
 try:
  cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=67108864','--user','1000:1000','-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-e','PR13_CONTINUITY_MODE=development-smoke','-e','PR13_CONTINUITY_SOURCE_SHA='+meta['release_sha'],'-v',str(W/'source')+':/work:ro','-v',str(W/'runtime')+':/runtime:ro','-v',str(E/'inner.py')+':/inner.py:ro','-v',str(RAM)+':/evidence',IMAGE,'python3','/inner.py').stdout.decode().strip();owned(cid);result['owned_container_id']=cid;docker('start',cid);until=time.monotonic()+1800
  while True:
   info=owned(cid)
   if not info['State']['Running']:break
   require(time.monotonic()<until,'Native pilot observation deadline exceeded');sample=guard()
   with (E/'resources.jsonl').open('ab') as f:f.write((json.dumps(sample)+'\n').encode())
   time.sleep(3)
  logs=docker('logs',cid);(RAM/'container.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((RAM/'inner-result.json').read_bytes()) if (RAM/'inner-result.json').exists() else {};result.update(exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner);result['ok']=result['exit_code']==0 and not result['oom_killed'] and inner.get('ok') is True
 except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
 finally:
  if cid:
   info=owned(cid)
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned(cid);docker('rm',cid);result['owned_container_removed']=True
  try:verify(meta);result['source_and_runtime_unchanged']=True
  except Exception as error:result.update(ok=False,source_and_runtime_unchanged=False,input_validation_error=str(error))
  health();write(E/'run-result.json',result)
 print(json.dumps(result));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(run())
