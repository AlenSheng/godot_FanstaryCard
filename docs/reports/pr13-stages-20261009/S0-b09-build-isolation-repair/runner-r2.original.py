"""One explicitly leased Tencent B09.3 run. Frozen inputs, bounded owned output."""
import hashlib,json,os,re,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='b09-legal-route-r2-20261011';OWNER='pr13-cap-'+A;E=B/'evidence'/A;W=B/'work'/A;SOURCE=W/'source';RAM=Path('/dev/shm/pr13-'+A);IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
FLOOR=500000000;RAM_BUDGET=128*1024**2;MEMORY=1536*1024**2;DEADLINE=2400
def require(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for d in iter(lambda:f.read(65536),b''):h.update(d)
 return h.hexdigest()
def write(p,v):
 require(not p.exists(),'Immutable file exists: '+str(p))
 with p.open('xb') as f:f.write((json.dumps(v,indent=2)+'\n').encode())
def command(args,timeout=30):return subprocess.run(args,capture_output=True,timeout=timeout,check=True)
def docker(*args):return command(['sudo','-n','docker',*map(str,args)])
def health():
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:require(h.status==200,'Production health unavailable')
def guard(start=False):
 mem=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'));s=os.statvfs(B);used=sum(p.stat().st_size for p in RAM.rglob('*') if p.is_file()) if RAM.exists() else 0
 require(mem>=FLOOR+(MEMORY+RAM_BUDGET if start else 0) and s.f_bavail/s.f_blocks>=.15 and used<=RAM_BUDGET,'Cloud resource floor or owned evidence limit exceeded');health();return {'at':time.time(),'memory_available_bytes':mem,'root_free_ratio':s.f_bavail/s.f_blocks,'owned_RAM_bytes':used}
def owned(cid):
 require(re.fullmatch('[0-9a-f]{64}',cid),'Exact full container ID required');v=json.loads(docker('inspect',cid).stdout)[0];require(v['Id']==cid and v['Config']['Labels']['codex.owner']==OWNER,'Container ownership differs');return v
def original_inputs(meta):
 require(all((SOURCE/k).is_file() and not (SOURCE/k).is_symlink() and sha(SOURCE/k)==h for k,h in meta['source_files'].items()),'Frozen source changed')
 require(sha(E/'inner.py')==meta['inner_sha256'] and sha(E/'runner.py')==meta['runner_sha256'],'Frozen driver changed')
 for k,h in meta['packages'].items():require(sha(Path(meta['package_root'])/k)==h,'Restored package changed')
def run():
 require(os.environ.get('PR13_B09_LEGAL_ROUTE_LEASE')==OWNER and os.name=='posix','Explicit owned Linux lease required')
 require(E.resolve()==B/'evidence'/A and W.resolve()==B/'work'/A and not any(p.is_symlink() for p in (E,W,RAM)),'Owned paths changed')
 unit=dict(x.split('=',1) for x in command(['systemctl','show',OWNER,'--property=MainPID,LoadState,ActiveState,InvocationID']).stdout.decode().splitlines());require(unit['LoadState']=='loaded' and unit['ActiveState']=='active' and int(unit['MainPID'])==os.getpid(),'Exact live MainPID lease required')
 meta=json.loads((E/'inputs.json').read_bytes());require(re.fullmatch('[0-9a-f]{40}',meta['release_sha']),'Frozen release SHA');require(command(['git','-C','/opt/fantasycard-github','rev-parse','HEAD']).stdout.decode().strip()==meta['release_sha'],'Cloud release differs')
 require(not RAM.exists() and not (E/'run-started.json').exists(),'Do not restart previous/uncertain native attempt');original_inputs(meta);guard(True)
 write(E/'run-started.json',{'attempt':A,'owner':OWNER,'MainPID':os.getpid(),'invocation_id':unit['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'source_sha':meta['release_sha'],'input_sha256':sha(E/'inputs.json')})
 RAM.mkdir(mode=0o777);command(['sudo','-n','mount','-t','tmpfs','-o','size=134217728,mode=0777,nosuid,nodev',OWNER,str(RAM)])
 cid=None;result={'ok':False,'attempt':A,'source_sha':meta['release_sha'],'MAIN_accepted':False,'LIVE_accepted':False}
 try:
  cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=268435456','--user','1000:1000','-e','HOME=/tmp/test-home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-e','NUGET_PACKAGES=/packages','-e','FANTASYCARD_SERVER_URL=http://127.0.0.1:1','-e','FANTASYCARD_PR13_SOURCE_SHA='+meta['release_sha'],'-v',str(SOURCE)+':/work','-v',str(SOURCE/'client')+':/work/client:ro','-v',str(RAM)+':/evidence','-v',str(E/'inner.py')+':/inner.py:ro','-v',meta['package_root']+':/packages:ro',IMAGE,'python3','/inner.py').stdout.decode().strip();owned(cid);result['owned_container_id']=cid;docker('start',cid);until=time.monotonic()+DEADLINE
  while True:
   info=owned(cid)
   if not info['State']['Running']:break
   require(time.monotonic()<until,'Native sequence deadline exceeded; preserve original output')
   sample=guard()
   with (E/'resources.jsonl').open('ab') as f:f.write((json.dumps(sample)+'\n').encode())
   # The filesystem itself enforces original raw-output quota between samples.
   native_build_bytes=sum(p.stat().st_size for p in (SOURCE/'server').rglob('*') if p.is_file() and ('obj' in p.parts or 'bin' in p.parts))
   require(native_build_bytes<=192*1024**2,'Native build output guard exceeded');time.sleep(3)
  logs=docker('logs',cid);(RAM/'container.log').write_bytes(logs.stdout+logs.stderr);result.update(exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled']);inner=json.loads((RAM/'inner-result.json').read_bytes()) if (RAM/'inner-result.json').exists() else {};result['inner']=inner;result['ok']=result['exit_code']==0 and not result['oom_killed'] and inner.get('ok') is True
 except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
 finally:
  if cid:
   info=owned(cid)
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned(cid);docker('rm',cid);result['owned_container_removed']=True
  try:
   original_inputs(meta);result['source_and_packages_unchanged']=True
  except Exception as error:
   result.update(ok=False,source_and_packages_unchanged=False,input_validation_error=str(error),failed_originals_retained=True)
  health();write(E/'run-result.json',result)
 print(json.dumps(result));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(run())
