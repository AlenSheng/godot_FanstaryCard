from pathlib import Path
import fcntl, hashlib, json, os, re, shutil, subprocess, threading, time, urllib.error, urllib.request, datetime, tarfile

task='season-balance-20261107-f03-cutover-r3';root=Path('/home/ubuntu')/task
assert not root.exists();root.mkdir(mode=0o700);public=root/'public';public.mkdir()
repo=Path('/opt/fantasycard-github');appdir=Path('/opt/fantasycard-app');compose=repo/'server/compose.cloud.yaml';envfile=repo/'server/.env'
new_image='sha256:b6267a7a50f4a2c1971ac0aeabccb2bdcabaf8d048b9b1512d8ad89e421d23f2'
old_image='sha256:b34b01ff381aa920264e3920d7a7a49e6c1056091999dfc6268107d07029b9f4'
runtime='1fe8e4b219714688c0bed061a3162628c5dd1cbe';source='878822c48a65fc5d8f8df8889dc1c9780a37923a';old_runtime='7862513858b94ca6a6cb908f345cf238128e348f'
pg='e140d6f8ab9f';caddy='b6200669e771';before_server='60bab052fd10';override=appdir/'active-season-image.yaml'
lock=(Path('/tmp/fantasycard-update.lock')).open('r');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
recovering=False
def run(args,timeout=30,input=None):
 if args[0]=='git':args=['runuser','-u','ubuntu','--',*args]
 p=subprocess.Popen(args,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 began=time.monotonic();first=True
 while True:
  try:
   out,err=p.communicate(input=input if first else None,timeout=.5)
   if p.returncode:
    (root/'subprocess.stderr.private.log').write_bytes(err)
    raise subprocess.CalledProcessError(p.returncode,args)
   return out
  except subprocess.TimeoutExpired:
   first=False
   if time.monotonic()-began>timeout or ('breach' in globals() and breach.is_set() and not recovering):
    import signal
    os.killpg(p.pid,signal.SIGTERM)
    try:p.communicate(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.communicate()
    raise RuntimeError('Owned subprocess timeout or resource protection: '+args[0])
def inspect(cid):return json.loads(run(['docker','inspect',cid]))[0]
def resource():
 m=dict(s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage(root)
 r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total);r['ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05;return r
def guard():
 r=resource();assert r['ok'] and not breach.is_set(),'Resource protection';return r
def atomic(path,text):
 p=path.with_name(path.name+'.'+task+'.tmp');assert not p.exists()
 with p.open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
 p.replace(path)
def compose_run(*args):return run(['docker','compose','-f',str(compose),'--env-file',str(envfile),'-f',str(override),*args],timeout=180)
def server():return run(['docker','compose','-f',str(compose),'--env-file',str(envfile),'ps','-q','server']).decode().strip()
def response(url):
 try:
  with urllib.request.urlopen(url,timeout=8) as r:return r.status,r.read()
 except urllib.error.HTTPError as r:return r.code,r.read()
def healthy(recovery=False):
 for _ in range(60):
  if not recovery:guard()
  try:
   status,body=response('http://127.0.0.1:8080/health/ready')
   if status==200 and body.strip()==b'Healthy':return True
  except OSError:pass
  time.sleep(1)
 return False
def psql(sql):return run(['docker','exec',pg,'psql','-U','fantasycard','-d','fantasycard','-X','-qAt','-v','ON_ERROR_STOP=1','-c',sql]).decode().strip()
def identity(cid):
 x=inspect(cid);return dict(id=x['Id'],image=x['Image'],started=x['State']['StartedAt'],running=x['State']['Running'])
stop=threading.Event();breach=threading.Event();samples=[]
def watch():
 while not stop.wait(.5):
  r=resource();samples.append(r)
  if not r['ok']:breach.set();return
thread=threading.Thread(target=watch,daemon=True);thread.start()
result=None;maintenance=False;switched=False;app_touched=False;caddy_temp='/config/'+task+'.Caddyfile';old_override=override.read_bytes() if override.exists() else None
original_caddy=(repo/'server/Caddyfile').read_bytes();(root/'original.Caddyfile.private').write_bytes(original_caddy)
old_markers={name:(appdir/name).read_bytes() if (appdir/name).exists() else None for name in ['deployed-git-commit','deployed-runtime-commit']}
try:
 guard();assert not run(['git','-C',str(repo),'status','--porcelain']).strip()
 assert inspect(before_server)['Image']==old_image and server().startswith(before_server)
 unchanged={name:identity(cid) for name,cid in [('postgres',pg),('caddy',caddy)]};(public/'baseline.original.json').write_text(json.dumps(dict(server=identity(before_server),unchanged=unchanged),indent=2)+'\n')
 image=json.loads(run(['docker','image','inspect',new_image]))[0];assert image['Id']==new_image and image['Config']['Labels']['org.opencontainers.image.revision']==runtime
 certificate=json.loads(run(['docker','run','--rm','--network','none','--read-only','--memory','64m','--cpus','0.25','--pids-limit','32','--label','com.fantasycard.task='+task,'--entrypoint','cat',new_image,'/app/protection-verification.json']))
 assert certificate['ok'] and certificate['status']=='AcceptedWithinExplicitUserNamedScope' and certificate['excluded_method_definitions']==79 and certificate['source_runtime']==runtime
 # Fetch commit/tree metadata first. Materialize only formal deployment sources;
 # tracked build caches, tests and historical evidence cannot fit this host.
 before_head=run(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
 run(['git','-C',str(repo),'fetch','--no-tags','--filter=blob:none','origin',source],timeout=180);guard()
 assert run(['git','-C',str(repo),'rev-parse','FETCH_HEAD']).decode().strip()==source
 run(['git','-C',str(repo),'merge-base','--is-ancestor',before_head,source])
 assert not run(['git','-C',str(repo),'diff','--name-only',before_head,source,'--','server/Caddyfile','server/compose.cloud.yaml','server/site','server/monitoring','server/deploy']).strip()
 selected=[]
 for name in run(['git','-C',str(repo),'ls-tree','-r','--name-only',source,'--','server','protocol/http','protocol/realtime','.dockerignore']).decode().splitlines():
  parts=name.split('/')
  if any(x in parts for x in ('bin','obj','.packages','.artifacts')) or name.startswith('server/tests/'):continue
  selected.append(name)
 assert 300<=len(selected)<=1500
 run(['git','-C',str(repo),'sparse-checkout','set','--no-cone','--stdin'],input=('\n'.join('/'+x for x in selected)+'\n').encode(),timeout=120);guard()
 run(['git','-C',str(repo),'merge','--ff-only','--quiet','--no-stat',source],timeout=180);guard()
 assert run(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()==source and not run(['git','-C',str(repo),'status','--porcelain']).strip()
 assert (repo/'server/Caddyfile').read_bytes()==original_caddy
 source_proof=dict(ok=True,before=before_head,after=source,fast_forward=True,sparse_deployment_files=len(selected),excluded=['tracked build caches','tests','historical evidence'],no_cloud_build=True)
 (public/'source-sync.original.json').write_text(json.dumps(source_proof,indent=2)+'\n')
 # The original website and health remain available; only game API/WS admission is briefly blocked.
 text=original_caddy.decode();needle='\t@game_api path /api/* /ws/* /health/*';assert text.count(needle)==1
 barrier='\t@season_rollout path /api/* /ws/*\n\thandle @season_rollout {\n\t\trespond "Game update in progress" 503\n\t}\n\n'
 edited=text.replace(needle,barrier+needle);run(['docker','exec','-i',caddy,'sh','-c','cat > '+caddy_temp],input=edited.encode())
 run(['docker','exec',caddy,'caddy','validate','--config',caddy_temp,'--adapter','caddyfile'])
 run(['docker','exec',caddy,'caddy','reload','--config',caddy_temp,'--adapter','caddyfile']);maintenance=True
 code=run(['curl','--silent','--show-error','--max-time','8','--resolve','www.relicbound.cn:443:127.0.0.1','-o','/dev/null','-w','%{http_code}','https://www.relicbound.cn/api/v1/client-info']).decode();assert code=='503'
 guard();app_touched=True;run(['docker','stop','--time','30',before_server],timeout=45)
 # Quiescent backup: the old application is stopped and the public game path is guarded.
 backup_dir=appdir/'backups';backup_dir.mkdir(mode=0o700,exist_ok=True);backup=backup_dir/(task+'-before-'+runtime+'.dump');assert not backup.exists()
 with backup.open('xb') as f:
  os.chmod(backup,0o600)
  p=subprocess.Popen(['docker','exec',pg,'pg_dump','-U','fantasycard','-d','fantasycard','-Fc','--no-owner','--no-privileges'],stdout=f,stderr=subprocess.PIPE)
  began=time.monotonic()
  while p.poll() is None:
   if breach.is_set() or time.monotonic()-began>120:p.terminate();p.wait(timeout=10);raise RuntimeError('Owned quiescent backup protection')
   time.sleep(.25)
  assert p.returncode==0;f.flush();os.fsync(f.fileno())
 with backup.open('rb') as f:assert f.read(5)==b'PGDMP'
 run(['docker','exec','-i',pg,'pg_restore','--list'],input=backup.read_bytes());backup_proof=dict(path=str(backup),bytes=backup.stat().st_size,sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),quiescent=True)
 (public/'quiescent-backup.original.json').write_text(json.dumps(backup_proof,indent=2)+'\n')
 atomic(override,'services:\n  server:\n    image: '+new_image+'\n')
 guard();compose_run('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','server');switched=True
 assert healthy(),'New application readiness failed'
 cid=server();actual=inspect(cid);assert actual['Image']==new_image and actual['Config']['Labels']['org.opencontainers.image.revision']==runtime
 actual_hashes=run(['docker','exec',cid,'sha256sum',*['/app/'+name for name in sorted(certificate['runtime_files'])]]).decode()
 hashes={line.split('  ',1)[1].removeprefix('/app/'):line.split('  ',1)[0] for line in actual_hashes.splitlines()};assert hashes=={name:r['sha256'] for name,r in certificate['runtime_files'].items()}
 assert run(['docker','exec',cid,'dotnet','--list-sdks']).strip()==b''
 facts=json.loads(psql("SELECT json_build_object('migrations',count(*),'maximum',max(version)) FROM schema_migrations"));assert facts=={'migrations':52,'maximum':55}
 # TLS host validation stays enabled; private admin remains hidden at the public origin.
 ready=run(['curl','--fail','--silent','--show-error','--max-time','10','--resolve','www.relicbound.cn:443:127.0.0.1','https://www.relicbound.cn/health/ready']).decode().strip();assert ready=='Healthy'
 assert {name:identity(cid) for name,cid in [('postgres',pg),('caddy',caddy)]}==unchanged
 # Existing MD5 baseline format is kept consistent with its deployed source.
 manifests=appdir/'version-manifests';manifests.mkdir(exist_ok=True)
 manifest=[]
 for name in selected:
  if name.startswith(('server/src/','server/config/','server/protection/','server/deploy/','server/monitoring/','server/site/','protocol/http/','protocol/realtime/')) or name in ['.dockerignore','server/Directory.Build.props','server/Directory.Packages.props','server/global.json','server/NuGet.Config','server/.dockerignore','server/compose.cloud.yaml','server/Caddyfile']:
   manifest.append(name+'\t'+hashlib.md5((repo/name).read_bytes()).hexdigest())
 for name in ('release.md5','release.version'):
  if (manifests/name).exists():shutil.copy2(manifests/name,root/(name+'.before.private'))
 atomic(manifests/'release.md5','\n'.join(sorted(manifest))+'\n');atomic(manifests/'release.version',source+'\n')
 atomic(appdir/'deployed-git-commit',source+'\n');atomic(appdir/'deployed-runtime-commit',runtime+'\n')
 run(['docker','exec',caddy,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile']);maintenance=False
 for path,expected in [('/health/ready','200'),('/api/v1/client-info','200'),('/admin','404'),('/api/admin/client-settings','404')]:
  status=run(['curl','--silent','--show-error','--max-time','10','--resolve','www.relicbound.cn:443:127.0.0.1','-o','/dev/null','-w','%{http_code}','https://www.relicbound.cn'+path]).decode();assert status==expected,(path,status)
 result=dict(ok=True,new_server=identity(cid),runtime_source=runtime,release_source=source,exact17_runtime_hashes=True,no_SDK=True,migrations=facts,
  quiescent_backup=backup_proof,private_offsite_backup_previously_verified=True,public_TLS_ready=True,public_admin_hidden=True,
  maintenance_removed=True,postgres_caddy_identity_unchanged=True,production_game_restarted=True,source_checkout=source_proof,database_not_restored_or_deleted=True,new_season_not_activated=True,resources=guard())
except BaseException as error:
 recovering=True
 result=dict(ok=False,type=type(error).__name__,error=str(error),switched=switched,rollback_attempted=app_touched,database_restore_attempted=False)
 try:
  if app_touched:
   atomic(override,'services:\n  server:\n    image: '+old_image+'\n');compose_run('up','-d','--no-deps','--no-build','--pull','never','--force-recreate','server')
   result['rollback_ready']=healthy(recovery=True)
   for name,raw in old_markers.items():
    if raw is not None:atomic(appdir/name,raw.decode())
   for name in ('release.md5','release.version'):
    saved=root/(name+'.before.private')
    if saved.exists():atomic(appdir/'version-manifests'/name,saved.read_text())
  if maintenance:run(['docker','exec',caddy,'caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile']);maintenance=False
  result['maintenance_removed']=not maintenance
 except BaseException as rollback:result['rollback_error']=type(rollback).__name__+':'+str(rollback)
finally:
 stop.set();thread.join(timeout=5)
 try:run(['docker','exec',caddy,'rm','-f',caddy_temp])
 except Exception:pass
 (public/'resources.original.json').write_text(json.dumps(dict(samples=samples,breach=breach.is_set()),indent=2)+'\n');(public/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 with tarfile.open(root/'public-evidence.tar.gz','w:gz') as tar:
  for path in sorted(public.iterdir()):tar.add(path,arcname=path.name)
print(json.dumps(result),flush=True)
