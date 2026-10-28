import hashlib,json,os,secrets,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-code-rollback-native-r4-20261012';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;PG=OWNER+'-pg';RAM=Path('/dev/shm/pr13-'+A);meta=json.loads((E/'inputs.original.json').read_bytes());IMAGE='sha256:180f524270f6ac28d2fe0ff29707fb392387d7b766f731e41fda1e45e8230520';PGIMAGE='postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def run(a,timeout=40,check=True):
 r=subprocess.run([str(x) for x in a],capture_output=True,timeout=timeout)
 if check:r.check_returncode()
 return r
def docker(*a,**kw):return run(['docker',*a],**kw)
def owned(cid,name):
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+name and v['Config']['Labels']['codex.owner']==OWNER;return v
def guard(start=False):
 memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert memory>=500000000+(1400+384+64)*1024**2*int(start) and s.f_bavail/s.f_blocks>=.15
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'at':time.time(),'memory_available_bytes':memory,'root_free_fraction':s.f_bavail/s.f_blocks,'health_status':200}
def frozen():
 for key,root in (('source_files','source_root'),('runtime_files','runtime_root'),('previous_runtime_files','previous_runtime_root')):
  for row in meta[key]:
   p=Path(meta[root])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 repo=Path('/opt/fantasycard-github');assert not run(['git','-c','safe.directory='+str(repo),'-C',repo,'diff','--name-only',meta['compiled_source_sha'],meta['implementation_source_sha'],'--','server','protocol']).stdout.strip()
state=dict(l.split('=',1) for l in run(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert state['MainPID']==str(os.getpid()) and state['ActiveState']=='active';write(E/'started.original.json',{'PID':os.getpid(),'state':state,'at':time.time(),'no_native_duplicate':True});ids={};bridge=None;secret=B/'secrets'/(A+'.private.env');assert not secret.exists();result={'ok':False,'implementation_source_sha':meta['implementation_source_sha'],'previous_source_sha':meta['previous_source_sha'],'MAIN_accepted':False};frozen();deadline=time.monotonic()+3600
while True:
 current=json.loads(run(['python3',B/'evidence/T03-conditioned-full-r2-20261012/controller.original.py','status']).stdout);units=run(['systemctl','list-units','--state=running','--no-legend','--plain','--no-pager','pr13-cap-*','pr13-pool-segment-*']).stdout.decode().splitlines();others=[l for l in units if l.split()[0]!=OWNER+'.service'];ready=current['current'] is None and not others
 if ready:
  try:guard(True);break
  except AssertionError:pass
 assert time.monotonic()<deadline,'Admission timeout; original handles preserved';time.sleep(5)
RAM=E/'persistent-native-outputs';assert not RAM.exists();RAM.mkdir(mode=0o777);RAM.chmod(0o777);write(E/'native-admitted.original.json',{'guard':guard(),'compiled_runtime_reused_without_rebuild':True,'original_test_deadline_seconds':180,'original_method':'Actual_code_rollback_and_native_backup_restore_preserve_once_only_assets'})
try:
 for name in (OWNER,PG):assert docker('inspect',name,check=False).returncode!=0
 password=secrets.token_hex(24);database='ready_stop_'+secrets.token_hex(16);secret.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB='+database+'\nPOSTGRES_PASSWORD='+password+'\nFANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database='+database+';Username=fantasycard;Password='+password+';Timeout=10;Command Timeout=30\n');secret.chmod(0o600)
 ids[PG]=docker('run','-d','--name',PG,'--label','codex.owner='+OWNER,'--label','codex.scope=disposable-local','--label','codex.task=pr13-stages-20261008','--network','none','--memory','384m','--memory-swap','384m','--cpus','.4','--tmpfs','/var/lib/postgresql:rw,nosuid,nodev,size=268435456','--env-file',secret,PGIMAGE,'postgres','-c','shared_buffers=16MB','-c','max_connections=100').stdout.decode().strip();owned(ids[PG],PG);until=time.monotonic()+60
 while docker('exec',ids[PG],'pg_isready','-h','127.0.0.1','-U','fantasycard','-d',database,check=False).returncode:assert time.monotonic()<until;time.sleep(1)
 bridge_root=Path('/run/pr13-rollback-r4');assert not bridge_root.exists();bridge_root.mkdir();bridge_root.chmod(0o755);binroot=W/'bridge-bin';binroot.mkdir();client=binroot/'docker';client.write_bytes((E/'bridge-client.original.py').read_bytes());client.chmod(0o755);bridge_log=(E/'bridge-service.original.log').open('xb');bridge=subprocess.Popen(['python3',str(E/'bridge-server.original.py'),str(bridge_root),OWNER,ids[PG],PG,database],stdout=bridge_log,stderr=subprocess.STDOUT);until=time.monotonic()+20
 while not (bridge_root/'owned-postgres.sock').exists():assert bridge.poll() is None and time.monotonic()<until;time.sleep(.2)
 runtime=Path(meta['runtime_root']);previous=Path(meta['previous_runtime_root']);ids[OWNER]=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','container:'+ids[PG],'--memory','1400m','--memory-swap','1400m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','--env-file',secret,'-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','PATH=/bridge-bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','-e','FANTASYCARD_PROCESS_EVIDENCE=/artifacts/outputs/pr13-local-20261008/rollback-audit/process-evidence','-e','FANTASYCARD_PROCESS_SOURCE_SHA='+meta['implementation_source_sha'],'-e','FANTASYCARD_PROCESS_SERVER_DLL=/artifacts/bin/FantasyCard.Server.Tests/release/FantasyCard.Server.dll','-e','FANTASYCARD_PROCESS_PREVIOUS_SERVER_DLL=/artifacts/outputs/pr13-local-20261008/previous0cf/FantasyCard.Server.dll','-e','FANTASYCARD_PROCESS_PREVIOUS_SERVER_SHA256='+meta['previous_server_sha256'],'-e','FANTASYCARD_TEST_DOCKER_CONTAINER='+PG,'-v',str(runtime)+':/artifacts/bin/FantasyCard.Server.Tests/release:ro','-v',str(previous)+':/artifacts/outputs/pr13-local-20261008/previous0cf:ro','-v',meta['client_root']+':/artifacts/client:ro','-v',str(RAM)+':/artifacts/outputs/pr13-local-20261008/rollback-audit','-v',str(bridge_root)+':/bridge:ro','-v',str(binroot)+':/bridge-bin:ro','-v',str(E/'inner.original.py')+':/inner.py:ro',IMAGE,'python3','/inner.py').stdout.decode().strip();owned(ids[OWNER],OWNER);docker('start',ids[OWNER]);until=time.monotonic()+300
 while True:
  info=owned(ids[OWNER],OWNER)
  if not info['State']['Running']:break
  assert time.monotonic()<until;sample=guard()
  with (E/'resources.original.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(3)
 logs=docker('logs',ids[OWNER]);(RAM/'container.original.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((RAM/'inner-result.original.json').read_bytes()) if (RAM/'inner-result.original.json').exists() else {};result.update(ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and inner.get('ok') is True,exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner)
 check=docker('exec',ids[PG],'psql','-X','-U','fantasycard','-d',database,'-At','-c',"SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'fc_runtime_test_%'");result['remaining_owned_fixture_schemas']=int(check.stdout.strip());result['ok']=result['ok'] and result['remaining_owned_fixture_schemas']==0
except Exception as error:result.update(error=type(error).__name__,detail=str(error),traceback=__import__('traceback').format_exc(),failed_originals_retained=True)
finally:
 try:
  saved=E/'retained-native-outputs';saved.mkdir();files=[]
  for p in sorted(RAM.rglob('*')):
   assert not p.is_symlink()
   if p.is_file():
    target=saved/p.relative_to(RAM);target.parent.mkdir(parents=True,exist_ok=True);data=p.read_bytes();target.write_bytes(data);assert target.read_bytes()==data;files.append({'path':target.relative_to(E).as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
  write(E/'retained-output-manifest.original.json',{'files':files,'copied_before_container_teardown':True});result['original_native_outputs_retained_before_teardown']=True
 except Exception as error:result['original_output_retention_error']=str(error)
 removed={}
 for name,cid in reversed(list(ids.items())):
  try:
   info=owned(cid,name)
   if info['State']['Running']:docker('stop','--time','10',cid)
   owned(cid,name);docker('rm',cid);removed[name]=True
  except Exception as error:removed[name]=type(error).__name__
 if bridge is not None:
  bridge.terminate();bridge.wait(timeout=10);bridge_log.close()
 result['owned_containers_removed']=len(removed)==len(ids) and all(v is True for v in removed.values());result['cleanup']=removed
 try:frozen();result['source_and_runtime_unchanged']=True
 except Exception as error:result.update(source_and_runtime_unchanged=False,source_error=str(error))
 if secret.exists():secret.unlink();result['owned_secret_removed']=True
 result['ok']=result['ok'] and result.get('original_native_outputs_retained_before_teardown') is True and result['owned_containers_removed'] and result.get('source_and_runtime_unchanged') is True;write(E/'result.original.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
