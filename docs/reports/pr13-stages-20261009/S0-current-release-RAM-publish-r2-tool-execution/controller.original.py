import fcntl,hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/release-current-RAM-build-r2-20261014'
OWNER='pr13-cap-release-current-RAM-build-r2';SDK='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,check=True,timeout=45):return subprocess.run(a,capture_output=True,check=check,timeout=timeout)
def guard(start=False):
 mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs('/')
 assert mem>=500000000+(1536*1024**2 if start else 0),'Current RAM build memory admission'
 assert s.f_bavail*s.f_frsize>=.15*s.f_blocks*s.f_frsize+(48*1024**2 if start else 0),'Current RAM build disk admission'
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as r:assert r.status==200
 return {'memory_available_bytes':mem,'root_free_bytes':s.f_bavail*s.f_frsize,'root_free_fraction':s.f_bavail/s.f_blocks,'production_health_status':200}
def frozen():
 p=read(E/'plan.original.json')
 for row in p['source_files']:
  s=Path(p['source_root'])/row['path'];assert s.stat().st_size==row['bytes'] and sha(s)==row['sha256']
  raw=run(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','show',p['source_sha']+':'+row['path']]).stdout
  assert hashlib.sha256(raw).hexdigest()==row['sha256']
 assert sha(E/'inner.original.py')==p['inner_sha256'] and sha(E/'obfuscar.xml')==p['obfuscar_xml_sha256']
 return p
def state():return dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,ExecMainStatus,InvocationID']).stdout.decode().splitlines())
def launch():
 with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);assert not (E/'dispatch.original.json').exists()
  busy=run(['systemctl','list-units','--state=running','--no-legend','pr13-cap-*','pr13-pool-segment-*']).stdout.strip()
  if busy:return {'ok':True,'resource_deferred':True,'reason':'Existing native test job running'}
  p=frozen();g=guard(True);u=Path('/etc/systemd/system')/(OWNER+'.service');assert not u.exists()
  u.write_text('[Unit]\nDescription=PR13 current release protected publish in bounded RAM\n[Service]\nType=exec\nUser=root\nExecStart=/usr/bin/python3 '+str(E/'controller.original.py')+' run\nRuntimeMaxSec=2000\nRestart=no\n')
  write(E/'dispatch-intent.original.json',{'guard':g,'unit_sha256':sha(u),'source_sha':p['source_sha'],'production_changed':False,'native_retry':False})
  run(['systemctl','daemon-reload']);r=run(['systemctl','start','--no-block',OWNER],False);write(E/'dispatch.original.json',{'exit_code':r.returncode});assert r.returncode==0
  return {'ok':True,'started':True,'state':state()}
def execute():
 actual=state();assert actual['MainPID']==str(os.getpid()) and actual['ActiveState']=='active'
 p=frozen();write(E/'started.original.json',{'state':actual,'guard':guard(True),'source_sha':p['source_sha']})
 output=E/'persistent-output';assert not output.exists();output.mkdir(mode=0o777);output.chmod(0o777)
 cid=None;result={'ok':False,'owner':OWNER,'source_sha':p['source_sha'],'production_changed':False,'MAIN_accepted':False}
 def owned():
  c=json.loads(run(['docker','inspect',cid]).stdout)[0];assert c['Id']==cid and c['Name']=='/'+OWNER and c['Config']['Labels']['codex.owner']==OWNER;return c
 try:
  args=['docker','create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','bridge','--memory','1536m','--memory-swap','1536m','--cpus','1','--read-only','--user','1000:1000',
   '--tmpfs','/work:rw,exec,nosuid,nodev,size=536870912,uid=1000,gid=1000','--tmpfs','/input:rw,nosuid,nodev,size=134217728,uid=1000,gid=1000',
   '--tmpfs','/framework:rw,nosuid,nodev,size=134217728,uid=1000,gid=1000','--tmpfs','/output:rw,nosuid,nodev,size=33554432,uid=1000,gid=1000',
   '--tmpfs','/private:rw,nosuid,nodev,size=16777216,uid=1000,gid=1000','--tmpfs','/tmp:rw,nosuid,nodev,size=67108864,uid=1000,gid=1000',
   '-e','HOME=/work/home','-e','DOTNET_CLI_HOME=/work/dotnet-home','-v',p['source_root']+':/source:ro','-v',p['package_root']+':/packages:ro',
   '-v',str(E)+':/controls:ro','-v',str(output)+':/publish-output',SDK,'python3','/controls/inner.original.py']
  cid=run(args).stdout.decode().strip();owned();run(['docker','start',cid]);deadline=time.monotonic()+1850
  while True:
   c=owned()
   if not c['State']['Running']:break
   assert time.monotonic()<deadline,'RAM build deadline';sample=guard();assert sum(x.stat().st_size for x in output.rglob('*') if x.is_file())<=48*1024**2
   with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
   time.sleep(5)
  logs=run(['docker','logs',cid]);(E/'native.stdout.original.log').write_bytes(logs.stdout);(E/'native.stderr.original.log').write_bytes(logs.stderr)
  q=output/'actual-protected-current-publish.original.json';r=read(q) if q.exists() else {}
  result.update(exit_code=c['State']['ExitCode'],oom_killed=c['State']['OOMKilled'],actual_protected_publish_ok=r.get('ok'),publish_report_sha256=sha(q) if q.exists() else None)
  assert c['State']['ExitCode']==0 and not c['State']['OOMKilled'] and r.get('ok')
  frozen();result['ok']=True
 except Exception as error:result.update(error=type(error).__name__,detail=str(error),original_failure_retained=True)
 finally:
  if cid:
   c=owned()
   if c['State']['Running']:run(['docker','stop','--time','10',cid])
   owned();run(['docker','rm',cid]);result['owned_container_removed']=True
  write(E/'result.original.json',result)
 assert result['ok'],'Preserve original RAM publish failure'
if __name__=='__main__':
 if sys.argv[1]=='launch':print(json.dumps(launch()))
 elif sys.argv[1]=='run':execute()
 else:raise ValueError('Unknown action')
