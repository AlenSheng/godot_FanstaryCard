import hashlib,json,os,re,secrets,subprocess,time,urllib.request
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='real-pg-http-context-r1-20261012';E=B/'evidence'/A;W=B/'work'/A;D=B/'work/real-PG-HTTP-context-r1-inputs';OWNER='pr13-cap-'+A;PG=OWNER+'-pg';RAM=Path('/dev/shm/pr13-'+A)
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
  database_proofs=[]
  for arm in inner['arms']:
   player=next(x for x in arm['players'] if x['side']=='A');other=next(x for x in arm['players'] if x['side']=='B');a=player['user_id'];b=other['user_id'];lost=arm['lost_request_id'];overlap=arm['overlap_request_id'];assert all(re.fullmatch('[0-9a-f-]{36}',x) for x in (a,b)) and a!=b and all(re.fullmatch('godot-[0-9A-Za-z-]{1,74}',x) for x in (lost,overlap))
   query="SELECT json_build_object('player_id',p.user_id,'profile_version',p.version,'selected_class',p.selected_class,'gold',w.gold,'potions',c.health_potion_count,'total_shop_rows',(SELECT count(*) FROM shop_purchases WHERE player_id=p.user_id),'total_price',(SELECT sum(price_gold) FROM shop_purchases WHERE player_id=p.user_id),'lost_rows',(SELECT count(*) FROM shop_purchases WHERE player_id=p.user_id AND request_id='"+lost+"'),'lost_quantity',(SELECT sum(quantity) FROM shop_purchases WHERE player_id=p.user_id AND request_id='"+lost+"'),'lost_price',(SELECT sum(price_gold) FROM shop_purchases WHERE player_id=p.user_id AND request_id='"+lost+"'),'lost_ledger_rows',(SELECT count(*) FROM economy_ledger WHERE player_id=p.user_id AND request_id='"+lost+"' AND currency='Gold'),'lost_ledger_delta',(SELECT sum(delta) FROM economy_ledger WHERE player_id=p.user_id AND request_id='"+lost+"' AND currency='Gold'),'overlap_rows',(SELECT count(*) FROM shop_purchases WHERE player_id=p.user_id AND request_id='"+overlap+"'),'other_gold',(SELECT gold FROM player_wallets WHERE player_id='"+b+"'),'other_potions',(SELECT health_potion_count FROM player_consumables WHERE player_id='"+b+"')) FROM players p JOIN player_wallets w ON w.player_id=p.user_id JOIN player_consumables c ON c.player_id=p.user_id WHERE p.user_id='"+a+"'"
   response=docker('exec',ids[PG],'psql','-X','-U','fantasycard','-d',database,'-At','-v','ON_ERROR_STOP=1','-c',query);(RAM/arm['arm']/'database-query.original.sql').write_text(query+'\n');(RAM/arm['arm']/'database-response.original.json').write_bytes(response.stdout);v=json.loads(response.stdout);target=next(r for r in json.loads((RAM/arm['arm']/'native-result.original.json').read_bytes())['cases'] if r['case_id']=='LOAD-08.2-T02')['actual'];assert v['profile_version']==target['committed_version'] and v['selected_class'] is not None and v['lost_rows']==v['lost_quantity']==v['lost_ledger_rows']==v['overlap_rows']==1 and v['total_shop_rows']==v['potions']==2 and v['lost_price']>0 and v['lost_ledger_delta']==-v['lost_price'] and v['gold']==player['initial_gold']-v['total_price'] and v['total_price']==2*v['lost_price'] and v['other_gold']==other['initial_gold'] and v['other_potions']==0;database_proofs.append({'arm':arm['arm'],'actual':v,'all_original_database_postconditions_passed':True})
  result['original_database_postconditions']=database_proofs;result['target_POSTGRES_profiles_verified']=len(meta['plan']['target_POSTGRES_cases'])
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
