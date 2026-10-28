"""Owned one-time full-original method replay at a B04 physical-part boundary."""
import fcntl,hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B03-full-original-seed-cluster-r1-20261013';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-b03-full-original-seed-cluster-r1-20261013';IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def require(v,m):
 if not v:raise ValueError(m)
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):
 require(not p.exists(),'Immutable original already exists');p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(a,timeout=45,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def state():return dict(x.split('=',1) for x in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,ExecMainStatus,LoadState,InvocationID']).stdout.decode().splitlines())
def guard(start=False):
 m=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/');require(m>=500000000+(1024*1024**2+64*1024**2 if start else 0),'Original 500MB memory admission hold');require((s.f_bavail-.15*s.f_blocks)*s.f_frsize>=32*1024**2,'Original 15 percent disk floor hold')
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:require(h.status==200,'Production ready health failed')
 return {'at':time.time(),'memory_available_bytes':m,'root_free_bytes':s.f_bavail*s.f_frsize,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
def frozen():
 restored=read(E/'restoration.original.json');require(restored['ok'] and restored['restored_original_projection_members']==3433,'Complete original restoration required');manifest=read(W/'restoration-manifest.original.json');require(sha(W/'restoration-manifest.original.json')==restored['manifest_sha256'],'Original source anchor differs')
 for r in manifest['files']:
  p=W/r['path'];require(not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],'Original restored byte changed')
 require(not run(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','diff','--name-only','b0423bfe6fedc3f034ba12c8400df5ebb8713f32','HEAD','--','server/src/FantasyCard.Domain']).stdout.strip(),'Current Domain business code differs');return restored
def launch():
 with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);require(not (E/'dispatch.original.json').exists(),'Existing handle must be inspected, no redispatch');busy=run(['systemctl','list-units','--state=running','--no-legend','pr13-cap-*','pr13-pool-segment-*']).stdout.strip();active=docker('ps','--format','{{.Names}}').stdout.decode().splitlines()
  if busy or any(n.startswith(('pr13-cap-','pr13-pool-segment-')) for n in active):return {'ok':True,'resource_deferred':True,'reason':'Wait for actual B04 physical-part boundary'}
  try:g=guard(True)
  except ValueError as e:return {'ok':True,'resource_deferred':True,'reason':str(e)}
  frozen();unit=Path('/etc/systemd/system')/(OWNER+'.service');require(not unit.exists(),'Existing unit must be inspected');unit.write_text('[Unit]\nDescription=Owned full720000 original seed-cluster method replay\n[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 '+str(E/'controller.original.py')+' run\nRuntimeMaxSec=1900\nRestart=no\n');write(E/'dispatch-intent.original.json',{'owner':OWNER,'guard':g,'unit_file_sha256':sha(unit),'dispatched_once':True,'full_original_encounters':720000});run(['systemctl','daemon-reload']);r=run(['systemctl','start','--no-block',OWNER],check=False);write(E/'dispatch.original.json',{'exit_code':r.returncode,'owner':OWNER,'no_automatic_retry':True});require(r.returncode==0,'Uncertain dispatch, inspect same handle');return {'ok':True,'started':True,'owner':OWNER}
def execute():
 st=state();require(st['MainPID']==str(os.getpid()) and st['ActiveState']=='active','Not original process handle');frozen();write(E/'started.original.json',{'PID':os.getpid(),'state':st,'guard':guard(True)});out=E/'persistent-output';require(not out.exists(),'Immutable original output exists');out.mkdir(mode=0o777);out.chmod(0o777);cid=None;result={'ok':False,'owner':OWNER,'MAIN_accepted':False}
 def owned():
  v=json.loads(docker('inspect',cid).stdout)[0];require(v['Id']==cid and v['Name']=='/'+OWNER and v['Config']['Labels']['codex.owner']==OWNER,'Foreign container identity');return v
 try:
  cid=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','none','--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--user','1000:1000','--tmpfs','/tmp:rw,nosuid,nodev,size=67108864','-e','PR13_CAP_STATISTICS_CLOUD=tencent-readonly-v1','-v',str(W/'projection')+':/inputs:ro','-v',str(W/'work')+':/work:ro','-v',str(out)+':/output',IMAGE,'python3','/work/secondary-analysis.py').stdout.decode().strip();owned();docker('start',cid);until=time.monotonic()+1800
  while True:
   info=owned()
   if not info['State']['Running']:break
   require(time.monotonic()<until,'Original method analysis deadline');g=guard();require(sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<=16*1024**2,'Original output budget exceeded')
   with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(g)+'\n')
   time.sleep(5)
  logs=docker('logs',cid);(E/'container.stdout.original.log').write_bytes(logs.stdout);(E/'container.stderr.original.log').write_bytes(logs.stderr);r=read(out/'full-original-seed-cluster-method.original.json') if (out/'full-original-seed-cluster-method.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and r.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],actual_full_original_encounters=r.get('original_encounters'),actual_original_unique_seed_clusters=r.get('actual_original_unique_seed_clusters'));frozen();result['original_inputs_unchanged']=True
 except Exception as e:result.update(error=type(e).__name__,detail=str(e),original_failure_retained=True)
 finally:
  removed=False
  if cid:
   v=owned()
   if v['State']['Running']:docker('stop','--time','5',cid)
   owned();docker('rm',cid);removed=True
  result['owned_container_removed']=removed;write(E/'result.original.json',result)
 require(result['ok'],'Actual native analysis failure preserved')
if __name__=='__main__':
 action=sys.argv[1]
 if action=='launch':print(json.dumps(launch()))
 elif action=='run':execute()
 elif action=='status':print(json.dumps({'ok':True,'state':state(),'result':read(E/'result.original.json') if (E/'result.original.json').exists() else None,'dispatch_exists':(E/'dispatch.original.json').exists()}))
 else:raise ValueError('Unknown action')
