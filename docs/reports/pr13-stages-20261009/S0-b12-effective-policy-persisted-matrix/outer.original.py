import hashlib,json,os,secrets,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='B12-effective-policy-postgres-r1-20261013';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;PG=OWNER+'-pg';meta=json.loads((E/'inputs.original.json').read_bytes());IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';PGIMAGE='postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def owned(cid,name):
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+name and v['Config']['Labels']['codex.owner']==OWNER;return v
def frozen():
 for key,root in [('source_files','source_root'),('runtime_files','runtime_root'),('fixture_files','fixture_root')]:
  for row in meta[key]:
   p=Path(meta[root])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
 assert not run(['git','-c','safe.directory=/opt/fantasycard-github','-C','/opt/fantasycard-github','diff','--name-only',meta['compiled_source_sha'],meta['implementation_source_sha'],'--','server','protocol']).stdout.strip()
def guard(start=False):
 s=os.statvfs('/');m=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;assert m>=500000000+(1024*1024**2 if start else 0) and s.f_bavail*s.f_frsize>=.15*s.f_blocks*s.f_frsize+(256*1024**2 if start else 0)
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'memory_available_bytes':m,'root_free_bytes':s.f_bavail*s.f_frsize,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';write(E/'started.original.json',{'actual_cloud_PID':os.getpid(),'state':state,'at':time.time()});frozen();deadline=time.monotonic()+3600
while True:
 st=json.loads(run(['python3',B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status']).stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service']
 if st['current'] is None and not others:
  try:guard(True);break
  except AssertionError:pass
 assert time.monotonic()<deadline,'Admission deadline; original handles preserved';time.sleep(5)
write(E/'admitted.original.json',{'guard':guard(True),'required_native_rows':72,'native_deadline_seconds':120,'compiled_runtime_reused':True});secret=B/'secrets'/(A+'.private.env');assert not secret.exists();ids={};result={'ok':False,'implementation_source_sha':meta['implementation_source_sha'],'MAIN_accepted':False};out=E/'persistent-native-outputs';art=W/'artifacts';out.mkdir(mode=0o777);out.chmod(0o777);art.mkdir(mode=0o777);art.chmod(0o777)
try:
 for name in [OWNER,PG]:assert docker('inspect',name,check=False).returncode!=0
 database='b12_policy_'+secrets.token_hex(12);secret.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB='+database+'\nPOSTGRES_PASSWORD='+secrets.token_hex(24)+'\n');secret.chmod(0o600)
 password=next(l.split('=',1)[1] for l in secret.read_text().splitlines() if l.startswith('POSTGRES_PASSWORD='));secret.write_text(secret.read_text()+'FANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database='+database+';Username=fantasycard;Password='+password+';Timeout=10;Command Timeout=30\n');secret.chmod(0o600)
 ids[PG]=docker('run','-d','--name',PG,'--label','codex.owner='+OWNER,'--network','none','--memory','256m','--memory-swap','256m','--cpus','.4','--tmpfs','/var/lib/postgresql:rw,nosuid,nodev,size=268435456','--env-file',secret,PGIMAGE,'postgres','-c','shared_buffers=16MB','-c','max_connections=100').stdout.decode().strip();owned(ids[PG],PG);until=time.monotonic()+60
 while docker('exec',ids[PG],'pg_isready','-h','127.0.0.1','-U','fantasycard','-d',database,check=False).returncode:assert time.monotonic()<until;time.sleep(1)
 ids[OWNER]=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','container:'+ids[PG],'--memory','768m','--memory-swap','768m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','--env-file',secret,'-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','-v',meta['runtime_root']+':/runtime:ro','-v',meta['package_root']+':/packages:ro','-v',meta['fixture_root']+':/fixture:ro','-v',str(E/'inner.original.py')+':/inner.py:ro','-v',str(E/'inputs.original.json')+':/meta.json:ro','-v',str(out)+':/evidence','-v',str(art)+':/artifacts',IMAGE,'python3','/inner.py').stdout.decode().strip();owned(ids[OWNER],OWNER);docker('start',ids[OWNER]);until=time.monotonic()+540
 while True:
  info=owned(ids[OWNER],OWNER)
  if not info['State']['Running']:break
  assert time.monotonic()<until;g=guard();assert sum(p.stat().st_size for p in W.rglob('*') if p.is_file())<256*1024**2
  with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(g)+'\n')
  time.sleep(3)
 logs=docker('logs',ids[OWNER]);(out/'container.original.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((out/'inner-result.original.json').read_bytes()) if (out/'inner-result.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and inner.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner)
 check=docker('exec',ids[PG],'psql','-X','-U','fantasycard','-d',database,'-At','-c',"SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'pr13_b12_policy_%'");result['remaining_owned_fixture_schemas']=int(check.stdout.strip());result['ok']=result['ok'] and result['remaining_owned_fixture_schemas']==0
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_originals_retained=True)
finally:
 removed={}
 for name,cid in reversed(list(ids.items())):
  try:
   info=owned(cid,name)
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned(cid,name);docker('rm',cid);removed[name]=True
  except Exception as error:removed[name]=type(error).__name__
 result['owned_containers_removed']=len(removed)==2 and all(v is True for v in removed.values());result['cleanup']=removed
 if secret.exists():secret.unlink();result['owned_secret_removed']=True
 try:frozen();result['source_runtime_and_fixture_unchanged']=True
 except Exception:result['source_runtime_and_fixture_unchanged']=False
 result['ok']=result['ok'] and result['owned_containers_removed'] and result['owned_secret_removed'] and result['source_runtime_and_fixture_unchanged'];write(E/'result.original.json',result)
print(json.dumps({'ok':result['ok'],'executed':result.get('inner',{}).get('executed',0),'owned_containers_removed':result['owned_containers_removed']}));raise SystemExit(0 if result['ok'] else 1)
