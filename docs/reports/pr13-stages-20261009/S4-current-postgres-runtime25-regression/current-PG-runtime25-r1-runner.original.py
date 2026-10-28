import hashlib,json,os,secrets,subprocess,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-pg-runtime-twentyfive-r1-20261012';E=B/'evidence'/A;W=B/'work'/A;OWNER='pr13-cap-'+A;PG=OWNER+'-pg';RAM=Path('/dev/shm/pr13-'+A)
def cmd(args,check=True,timeout=35):
 r=subprocess.run(args,capture_output=True,check=False,timeout=timeout)
 if check and r.returncode:
  write(E/'command-failure.original.json',{'arguments':args,'exit_code':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')})
  r.check_returncode()
 return r
def docker(*args,**kw):return cmd(['sudo','-n','docker',*map(str,args)],**kw)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(65536),b''):h.update(block)
 return h.hexdigest()
def write(p,v):
 assert not p.exists()
 p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def owned(cid,name):
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+name and v['Config']['Labels']['codex.owner']==OWNER;return v
def frozen(meta):
 for row in meta['input_files']:
  p=Path(meta['source'])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for row in meta['package_files']:
  p=Path(meta['package_root'])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 for row in meta['supplemental_package_files']:
  p=Path(meta['supplemental_package_root'])/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']

def guard(start=False):
 available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
 st=os.statvfs('/');assert available>=500000000+(1024+384+64)*1024**2*int(start) and st.f_bavail*st.f_frsize>=int(st.f_blocks*st.f_frsize*.15)+(192+64)*1024**2*int(start)
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'memory_available_bytes':available,'root_free_bytes':st.f_bavail*st.f_frsize,'production_health_status':200}
meta=json.loads((E/'inputs.json').read_bytes());assert meta['required_native_method_count']==23
assert os.environ.get('PR13_PG_NUMERICAL_LEASE')==OWNER and os.name=='posix'
unit=dict(x.split('=',1) for x in cmd(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(unit['MainPID'])==os.getpid() and unit['ActiveState']=='active'
assert not (E/'run-started.json').exists() and not RAM.exists();frozen(meta);sample=guard(True)
for name in (OWNER,PG):assert docker('inspect',name,check=False).returncode!=0
write(E/'run-started.json',{'MainPID':os.getpid(),'invocation_id':unit['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'frozen_release_sha':meta['frozen_release_sha'],'inputs_sha256':sha(E/'inputs.json'),'guard':sample})
RAM.mkdir(mode=0o777);cmd(['sudo','-n','mount','-t','tmpfs','-o','size=67108864,mode=0777,nosuid,nodev',OWNER,str(RAM)])
artifacts=W/'artifacts';artifacts.mkdir(mode=0o777);artifacts.chmod(0o777);assert (artifacts.stat().st_mode&0o777)==0o777
inner=r'''
import json,os,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
E=Path('/evidence');meta=json.loads(Path('/meta.json').read_bytes());project='/work/server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj';phases=[]
def phase(name,args,timeout):
 with (E/(name+'.log')).open('xb') as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,cwd='/work/server')
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
try:
 sdk=subprocess.check_output(['dotnet','--version'],cwd='/work/server',text=True).strip();assert sdk==json.loads(Path('/work/server/global.json').read_bytes())['sdk']['version'];(E/'sdk.original.json').write_text(json.dumps({'actual_sdk':sdk})+'\n')
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 phase('native',['dotnet','test',project,'-c','Release','--no-build','--no-restore','--artifacts-path','/artifacts','--filter','FullyQualifiedName~PostgresRuntimeIntegrationTests','--results-directory','/evidence/results','--logger','trx;LogFileName=native-twentyfive.trx'],480)
 root=ET.parse(E/'results/native-twentyfive.trx');counts=root.find('.//{*}Counters').attrib;assert int(counts['total'])==int(counts['executed'])==int(counts['passed'])==25 and all(int(counts.get(k,0))==0 for k in ('failed','notExecuted','error','timeout','aborted'))
 rows=root.findall('.//{*}UnitTestResult');assert len(rows)==25 and all(row.attrib['outcome']=='Passed' for row in rows)
 names={r.attrib['testName'].split('.')[-1].split('(')[0] for r in rows};assert names==set(meta['required_native_methods'])
 receipts=[]
 for cid in meta['required_numerical_case_ids']:
  p=E/'native-receipts'/(cid+'.json');v=json.loads(p.read_bytes());assert v['caseId']==cid and v['status']=='Passed' and v['actual'];receipts.append(cid)
 result={'ok':True,'frozen_release_sha':meta['frozen_release_sha'],'native_rows_passed':25,'native_distinct_methods':23,'native_skipped':0,'actual_database_receipts':receipts,'phases':phases,'MAIN_accepted':False}
except Exception as error:result={'ok':False,'error':type(error).__name__,'detail':str(error),'phases':phases,'failed_raw_retained':True,'MAIN_accepted':False}
(E/'inner-result.json').write_text(json.dumps(result,indent=2)+'\n');raise SystemExit(0 if result['ok'] else 1)
'''
(E/'inner.py').write_text(inner);ids={};secret=B/'secrets'/(A+'.private.env');assert not secret.exists();result={'ok':False,'frozen_release_sha':meta['frozen_release_sha'],'MAIN_accepted':False}
try:
 password=secrets.token_hex(24);database='ready_stop_'+secrets.token_hex(16);secret.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB='+database+'\nPOSTGRES_PASSWORD='+password+'\nFANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database='+database+';Username=fantasycard;Password='+password+';Timeout=10;Command Timeout=30\n');secret.chmod(0o600)
 ids[PG]=docker('run','-d','--name',PG,'--label','codex.owner='+OWNER,'--network','none','--memory','384m','--memory-swap','384m','--cpus','.4','--tmpfs','/var/lib/postgresql:rw,nosuid,nodev,size=268435456','--env-file',str(secret),meta['postgres_image'],'postgres','-c','shared_buffers=16MB','-c','max_connections=25').stdout.decode().strip();owned(ids[PG],PG)
 deadline=time.monotonic()+60
 while docker('exec',ids[PG],'pg_isready','-h','127.0.0.1','-U','fantasycard','-d',database,check=False).returncode:
  assert time.monotonic()<deadline;time.sleep(1)
 ids[OWNER]=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','container:'+ids[PG],'--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','--env-file',str(secret),'-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','NUGET_PACKAGES=/packages','-v',meta['source']+':/work:ro','-v',meta['package_root']+':/packages:ro','-v',str(E/'inputs.json')+':/meta.json:ro','-v',str(E/'inner.py')+':/inner.py:ro','-v',str(artifacts)+':/artifacts','-v',str(RAM)+':/evidence',meta['SDK_image'],'python3','/inner.py').stdout.decode().strip();owned(ids[OWNER],OWNER);docker('start',ids[OWNER]);deadline=time.monotonic()+1600
 while True:
  info=owned(ids[OWNER],OWNER)
  if not info['State']['Running']:break
  assert time.monotonic()<deadline;sample=guard();assert sum(p.stat().st_size for p in artifacts.rglob('*') if p.is_file())<=192*1024**2
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(5)
 logs=docker('logs',ids[OWNER]);(RAM/'container.original.log').write_bytes(logs.stdout+logs.stderr);v=json.loads((RAM/'inner-result.json').read_bytes()) if (RAM/'inner-result.json').exists() else {};result.update(exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=v,ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and v.get('ok') is True)
 query=docker('exec',ids[PG],'psql','-X','-U','fantasycard','-d',database,'-At','-c',"SELECT count(*) FROM information_schema.schemata WHERE schema_name LIKE 'fc_runtime_test_%'");result['remaining_owned_fixture_schemas']=int(query.stdout.strip());result['ok']=result['ok'] and result['remaining_owned_fixture_schemas']==0
except Exception as error:result.update(error=type(error).__name__,detail=str(error),failed_raw_retained=True)
finally:
 cleanup={}
 for name,cid in reversed(list(ids.items())):
  try:
   info=owned(cid,name)
   if info['State']['Running']:docker('stop','--time','10',cid)
   if name==PG:
    logs=docker('logs',cid,check=False);(E/'postgres.original.log').write_bytes(logs.stdout+logs.stderr)
   owned(cid,name);docker('rm',cid);cleanup[name]=True
  except Exception as error:cleanup[name]=type(error).__name__
 result['owned_containers_removed']=len(cleanup)==2 and all(v is True for v in cleanup.values());result['cleanup']=cleanup
 try:frozen(meta);result['frozen_source_and_package_bytes_unchanged']=True
 except Exception:result['frozen_source_and_package_bytes_unchanged']=False
 result['ok']=result['ok'] and result['owned_containers_removed'] and result['frozen_source_and_package_bytes_unchanged'];result['all_original_outputs_retained_pending_G_backup']=True
 write(E/'run-result.json',result)
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
