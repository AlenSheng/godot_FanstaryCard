import hashlib,json,os,re,secrets,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='real-pg-tls-framing-r2-20261012';E=B/'evidence'/A;W=B/'work'/A;D=B/'work/real-PG-TLS-framing-r2-inputs';OWNER='pr13-cap-'+A;PG=OWNER+'-pg';RAM=Path('/dev/shm/pr13-'+A)
def cmd(args,check=True,timeout=35):
 r=subprocess.run(args,capture_output=True,timeout=timeout)
 if check and r.returncode:write(E/'command-failure.original.json',{'arguments':args,'exit_code':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')});r.check_returncode()
 return r
def docker(*args,**kw):return cmd(['docker',*map(str,args)],**kw)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
 return h.hexdigest()
def write(p,v):assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def owned(cid,name):
 v=json.loads(docker('inspect',cid).stdout)[0];assert v['Id']==cid and v['Name']=='/'+name and v['Config']['Labels']['codex.owner']==OWNER;return v
meta=json.loads((D/'manifest.json').read_bytes())
def frozen():
 for key,root in (('input_files',meta['source']),('package_files',meta['package_root']),('supplemental_package_files',meta['supplemental_package_root']),('client_files',str(D/'client'))):
  for row in meta[key]:
   p=Path(root)/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 assert sha(D/'inner.original.py')==meta['inner_sha256']
def guard(start=False):
 m=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;s=os.statvfs('/');assert m>=500000000+(1024+384+128)*1024**2*int(start) and s.f_bavail*s.f_frsize>=s.f_blocks*s.f_frsize*.15+(192+128)*1024**2*int(start)
 with urllib.request.urlopen('http://127.0.0.1:8080/health/ready',timeout=10) as h:assert h.status==200
 return {'memory_available_bytes':m,'root_free_ratio':s.f_bavail/s.f_blocks,'production_health_status':200}
state=dict(x.split('=',1) for x in cmd(['systemctl','show',OWNER,'--property=MainPID,ActiveState,InvocationID']).stdout.decode().splitlines());assert int(state['MainPID'])==os.getpid() and state['ActiveState']=='active';frozen();guard(True);assert not RAM.exists();RAM.mkdir(mode=0o777);cmd(['mount','-t','tmpfs','-o','size=134217728,mode=0777,nosuid,nodev',OWNER,str(RAM)]);write(E/'run-started.json',{'MainPID':os.getpid(),'invocation_id':state['InvocationID'],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'at':time.time(),'input_manifest_sha256':sha(D/'manifest.json'),'production_source_sha':meta['production_source_sha'],'native_source_cache_sha':meta['frozen_release_sha'],'guard':guard()})
ids={};secret=B/'secrets'/(A+'.private.env');result={'ok':False,'production_source_sha':meta['production_source_sha'],'native_source_cache_sha':meta['frozen_release_sha'],'MAIN_accepted':False}
try:
 for name in (OWNER,PG):assert docker('inspect',name,check=False).returncode!=0
 assert not secret.exists();password=secrets.token_hex(24);database='ready_stop_'+secrets.token_hex(16);secret.write_text('POSTGRES_USER=fantasycard\nPOSTGRES_DB='+database+'\nPOSTGRES_PASSWORD='+password+'\nFANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database='+database+';Username=fantasycard;Password='+password+';Timeout=10;Command Timeout=30\n');secret.chmod(0o600)
 artifacts=W/'artifacts';artifacts.mkdir(mode=0o777);artifacts.chmod(0o777)
 ids[PG]=docker('run','-d','--name',PG,'--label','codex.owner='+OWNER,'--network','none','--memory','384m','--memory-swap','384m','--cpus','.4','--tmpfs','/var/lib/postgresql:rw,nosuid,nodev,size=268435456','--env-file',str(secret),meta['postgres_image'],'postgres','-c','shared_buffers=16MB','-c','max_connections=25').stdout.decode().strip();owned(ids[PG],PG);until=time.monotonic()+60
 while docker('exec',ids[PG],'pg_isready','-h','127.0.0.1','-U','fantasycard','-d',database,check=False).returncode:assert time.monotonic()<until;time.sleep(1)
 ids[OWNER]=docker('create','--name',OWNER,'--label','codex.owner='+OWNER,'--network','container:'+ids[PG],'--memory','1024m','--memory-swap','1024m','--cpus','1','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--user','1000:1000','--env-file',str(secret),'-e','HOME=/tmp/home','-e','DOTNET_CLI_HOME=/tmp/dotnet','-e','NUGET_PACKAGES=/packages','-v',meta['source']+':/work:ro','-v',meta['package_root']+':/packages:ro','-v',str(D/'client')+':/client:ro','-v',str(D/'manifest.json')+':/meta.json:ro','-v',str(D/'inner.original.py')+':/inner.py:ro','-v',str(artifacts)+':/artifacts','-v',str(RAM)+':/evidence',meta['SDK_image'],'python3','/inner.py').stdout.decode().strip();owned(ids[OWNER],OWNER);docker('start',ids[OWNER]);until=time.monotonic()+1500
 while True:
  info=owned(ids[OWNER],OWNER)
  if not info['State']['Running']:break
  assert time.monotonic()<until;sample=guard();assert sum(p.stat().st_size for p in artifacts.rglob('*') if p.is_file())<=192*1024**2 and sum(p.stat().st_size for p in RAM.rglob('*') if p.is_file())<128*1024**2
  with (E/'resources.jsonl').open('a') as f:f.write(json.dumps(sample)+'\n')
  time.sleep(5)
 logs=docker('logs',ids[OWNER]);(RAM/'container.original.log').write_bytes(logs.stdout+logs.stderr);inner=json.loads((RAM/'inner-result.original.json').read_bytes()) if (RAM/'inner-result.original.json').exists() else {};result.update(exit_code=info['State']['ExitCode'],oom_killed=info['State']['OOMKilled'],inner=inner,ok=info['State']['ExitCode']==0 and not info['State']['OOMKilled'] and inner.get('ok') is True)
 if result['ok']:
  player=inner['actual_player_id'];assert re.fullmatch('[0-9a-f-]{36}',player)
  query="SELECT json_build_object('player_id',p.user_id,'version',p.version,'gold',w.gold,'potions',c.health_potion_count,'purchase_rows',(SELECT count(*) FROM shop_purchases WHERE player_id=p.user_id),'economy_ledger_rows',(SELECT count(*) FROM economy_ledger WHERE player_id=p.user_id),'session_rows',(SELECT count(*) FROM player_sessions WHERE player_id=p.user_id)) FROM players p JOIN player_wallets w ON w.player_id=p.user_id JOIN player_consumables c ON c.player_id=p.user_id WHERE p.user_id='"+player+"'"
  response=docker('exec',ids[PG],'psql','-X','-U','fantasycard','-d',database,'-At','-v','ON_ERROR_STOP=1','-c',query);(RAM/'database-query.original.sql').write_text(query+'\n');(RAM/'database-response.original.json').write_bytes(response.stdout);v=json.loads(response.stdout);assert v['version']==inner['actual_profile_version']==1 and v['gold']==v['potions']==v['purchase_rows']==v['economy_ledger_rows']==0 and v['session_rows']==1;result['original_database_postconditions']=v;result['target_POSTGRES_profiles_verified']=3

except Exception as error:result.update(ok=False,error=type(error).__name__,detail=str(error),failed_originals_retained=True)
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
 try:frozen();result['frozen_source_package_and_client_bytes_unchanged']=True
 except Exception:result['frozen_source_package_and_client_bytes_unchanged']=False
 result['ok']=result['ok'] and result['owned_containers_removed'] and result['frozen_source_package_and_client_bytes_unchanged'];result['all_original_outputs_retained_pending_G_backup']=True;write(E/'run-result.json',result)
print(json.dumps({'ok':result['ok'],'target_PG_profiles':result.get('target_POSTGRES_profiles_verified',0),'G_backup_pending':True}));raise SystemExit(0 if result['ok'] else 1)
