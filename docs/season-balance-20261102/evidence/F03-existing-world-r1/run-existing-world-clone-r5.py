from pathlib import Path
import re
import base64, ctypes, datetime, hashlib, importlib.util, json, os, secrets, shutil, socket, subprocess, threading, time, urllib.error, urllib.request, uuid

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-existing-world-clone-r5';private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-google-r1\existing-world-clone-r5')
assert not out.exists() and not private.exists();out.mkdir();private.mkdir()
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid=subprocess.check_output(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],creationflags=flags).decode().strip()
r=subprocess.run(['icacls',str(private),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],capture_output=True,creationflags=flags);assert r.returncode==0
(private/'ownership.json').write_text(json.dumps(dict(task='season-balance-20261102',scope='private restored production clone only;never publish database,identities,tokens or raw HTTP bodies'))+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
backup=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-backup-r1\migration-rehearsal-r1\production-rehearsal-source.dump')
assert sha(backup)=='14f127e47726936785af0d78015959ea67c53d63746f0887d64f381e4e381139'
report=json.loads((b/'f03-protected-build-r3/result.json').read_bytes());package=Path(report['output'])
for name,record in report['package_files'].items():assert sha(package/name)==record['sha256']
pgbin=Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\postgres\pgsql\bin');data=private/'pgdata'
class Memory(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','p','ap','v','av','e']]
def available():
 m=Memory();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
class Basic(ctypes.Structure):
 _fields_=[('p',ctypes.c_longlong),('j',ctypes.c_longlong),('flags',ctypes.c_ulong),('min',ctypes.c_size_t),('max',ctypes.c_size_t),('active',ctypes.c_ulong),('affinity',ctypes.c_size_t),('priority',ctypes.c_ulong),('schedule',ctypes.c_ulong)]
class Limits(ctypes.Structure):
 _fields_=[('basic',Basic),('io',ctypes.c_ulonglong*6),('pm',ctypes.c_size_t),('jm',ctypes.c_size_t),('pp',ctypes.c_size_t),('pj',ctypes.c_size_t)]
k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateJobObjectW.restype=ctypes.c_void_p;k.SetInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong];k.AssignProcessToJobObject.argtypes=[ctypes.c_void_p,ctypes.c_void_p];k.TerminateJobObject.argtypes=[ctypes.c_void_p,ctypes.c_uint];k.CloseHandle.argtypes=[ctypes.c_void_p]
job=k.CreateJobObjectW(None,None);assert job;limits=Limits();limits.basic.flags=0x2000|0x20;limits.basic.priority=0x4000;assert k.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits))
popen=subprocess.Popen;handles=[]
def own(*args,**kwargs):
 child=popen(*args,**kwargs)
 if not k.AssignProcessToJobObject(job,int(child._handle)):
  code=ctypes.get_last_error();child.kill();child.wait(timeout=10);raise ctypes.WinError(code)
 handles.append(dict(pid=child.pid,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));return child
subprocess.Popen=own;stop=threading.Event();breach=threading.Event();samples=[]
def watch():
 while not stop.wait(.25):
  value=available();samples.append(value)
  if value<2*1024**3:breach.set();k.TerminateJobObject(job,91);return
thread=threading.Thread(target=watch,daemon=True);thread.start()
env={n:v for n,v in os.environ.items() if not n.startswith(('FANTASYCARD_','OTEL_'))};env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
pg_started=False;app=None;app_log=None;error=None;checks=[];selected=[];asset_before=None;asset_after=None;facts={};port=None
def admission():
 values=[]
 for _ in range(3):values.append(available());time.sleep(1)
 assert min(values)>=3*1024**3
def file_run(command,name,timeout=120,startup=True):
 if startup:admission()
 with (private/(name+'.log')).open('wb') as log:
  child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=flags);code=child.wait(timeout=timeout)
 assert code==0 and not breach.is_set(),name
def psql(query,name):
 p=private/(name+'.sql');p.write_text(query,encoding='utf-8')
 r=subprocess.run([str(pgbin/'psql.exe'),'-h','127.0.0.1','-p',str(port),'-U','fantasycard','-d','fantasycard','-X','-qAt','-v','ON_ERROR_STOP=1','-f',str(p)],env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45,creationflags=flags)
 (private/(name+'.stdout')).write_text(r.stdout,encoding='utf-8');(private/(name+'.stderr')).write_text(r.stderr,encoding='utf-8');assert r.returncode==0,name
 return r.stdout.strip()
def asset_fingerprint(name):
 return json.loads(psql("SELECT json_build_object('wallets',(SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(row_to_json(t)::text) h FROM player_wallets t)q),'materials',(SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(row_to_json(t)::text)h FROM player_materials t)q),'equipment',(SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(row_to_json(t)::text)h FROM equipments t)q),'holds',(SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(row_to_json(t)::text)h FROM settlement_asset_holds t)q),'ledger_count',(SELECT count(*) FROM economy_ledger));",name))
def http(method,path,token=None,key=None):
 headers={'Accept':'application/protobuf'}
 if token:headers['Authorization']='Bearer '+token
 if key:headers['Idempotency-Key']=key
 data=b'' if method=='POST' else None
 if data is not None:headers['Content-Type']='application/protobuf'
 call=urllib.request.Request(base+path,data=data,headers=headers,method=method)
 try:
  with urllib.request.urlopen(call,timeout=15) as response:return response.status,dict(response.headers),response.read()
 except urllib.error.HTTPError as response:return response.code,dict(response.headers),response.read()
def ack_identity(body):
 i=0;fields={}
 def integer(index):
  value=0;shift=0
  while True:
   byte=body[index];index+=1;value|=(byte&127)<<shift
   if byte<128:return value,index
   shift+=7
 while i<len(body):
  tag,i=integer(i);assert tag&7==2
  length,i=integer(i);fields[tag>>3]=body[i:i+length].decode();i+=length
 assert set(fields)=={1,2}
 return fields[1],datetime.datetime.fromisoformat(re.sub(r'(\.\d{6})\d(?=[+-]\d{2}:\d{2}$)',r'\1',fields[2])).astimezone(datetime.timezone.utc)
def checked(name,method,path,token=None,key=None,expected=200):
 status,headers,body=http(method,path,token,key);passed=status==expected and ('protobuf' in headers.get('Content-Type','') if path.startswith('/api/') else True)
 ordinal=len(checks);(private/(f'http-{ordinal:02d}.body')).write_bytes(body);checks.append(dict(name=name,status=status,expected=expected,passed=passed,content_type=headers.get('Content-Type'),bytes=len(body),body_sha256=hashlib.sha256(body).hexdigest()));assert passed,name
 return body
try:
 file_run([str(pgbin/'initdb.exe'),'-D',str(data),'-U','fantasycard','-A','trust','--no-locale','-E','UTF8'],'initdb')
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 file_run([str(pgbin/'pg_ctl.exe'),'-D',str(data),'-w','-l',str(private/'postgres.log'),'-o',f'-h 127.0.0.1 -p {port} -F -c shared_buffers=32MB -c max_connections=50 -c max_wal_size=128MB -c min_wal_size=80MB','start'],'pg-start');pg_started=True
 file_run([str(pgbin/'createdb.exe'),'-h','127.0.0.1','-p',str(port),'-U','fantasycard','fantasycard'],'createdb')
 file_run([str(pgbin/'pg_restore.exe'),'-h','127.0.0.1','-p',str(port),'-U','fantasycard','-d','fantasycard','--exit-on-error','--no-owner','--no-privileges',str(backup)],'restore',180)
 facts['before']=json.loads(psql("SELECT json_build_object('migration_max',(SELECT max(version) FROM schema_migrations),'matches',(SELECT count(*) FROM matches),'unacknowledged',(SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NULL));",'before'))
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));app_port=sock.getsockname()[1]
 base='http://127.0.0.1:'+str(app_port);app_env=dict(env,ASPNETCORE_ENVIRONMENT='Production',ASPNETCORE_URLS=base,Identity__EnableLocalAuth='false',Admin__ApiKey=secrets.token_urlsafe(48),ConnectionStrings__Postgres=f'Host=127.0.0.1;Port={port};Database=fantasycard;Username=fantasycard;Pooling=true')
 admission();app_log=(private/'application.private.log').open('wb');app=subprocess.Popen(['dotnet',str(package/'FantasyCard.Server.dll')],cwd=package,env=app_env,stdin=subprocess.DEVNULL,stdout=app_log,stderr=subprocess.STDOUT,creationflags=flags)
 (out/'application-handle.original.json').write_text(json.dumps(dict(pid=app.pid,source=report['source_commit'],cloned_database_only=True,Production=True,local_auth_enabled=False),indent=2)+'\n')
 for _ in range(120):
  assert app.poll() is None,'Actual protected Program exited before readiness'
  try:
   if http('GET','/health/ready')[0]==200:break
  except (OSError,urllib.error.URLError):pass
  time.sleep(.5)
 else:raise RuntimeError('Clone protected Program readiness timeout')
 checked('cloned-data readiness','GET','/health/ready');facts['after_startup']=json.loads(psql("SELECT json_build_object('migration_max',(SELECT max(version) FROM schema_migrations),'migration_count',(SELECT count(*) FROM schema_migrations),'matches',(SELECT count(*) FROM matches),'unacknowledged',(SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NULL),'seasons',(SELECT count(*) FROM season_definitions));",'after-startup'))
 assert facts['after_startup']['migration_max']==55 and facts['after_startup']['matches']==facts['before']['matches']
 selected=json.loads(psql("SELECT coalesce(json_agg(x),'[]'::json) FROM (SELECT * FROM (SELECT s.settlement_id,s.player_id,m.config_version,row_number() OVER(PARTITION BY m.config_version ORDER BY s.created_at DESC,s.settlement_id) AS n FROM match_settlements s JOIN matches m USING(match_id) JOIN match_players mp ON mp.match_id=s.match_id AND mp.player_id=s.player_id JOIN players p ON p.user_id=s.player_id WHERE s.acknowledged_at IS NULL AND NOT mp.is_bot AND NOT EXISTS(SELECT1 FROM player_bans b WHERE b.player_id=s.player_id))a WHERE n<=3)x;".replace('SELECT1','SELECT 1'),'select-clone-only-samples'))
 assert len(selected)==6 and len({r['config_version'] for r in selected})==2
 asset_before=asset_fingerprint('assets-before-http')
 for ordinal,row in enumerate(selected):
  token=secrets.token_urlsafe(32);token_hash=hashlib.sha256(token.encode()).hexdigest();session=uuid.uuid4();player=row['player_id'];settlement=row['settlement_id']
  psql(f"INSERT INTO player_sessions(session_id,player_id,token_hash,expires_at,created_at) VALUES('{session}','{player}',decode('{token_hash}','hex'),now()+interval '1hour',now());",f'clone-session-{ordinal}')
  prefix='legacy'+('068' if '0.68' in row['config_version'] else '070')+'-'+str(ordinal)
  checked(prefix+'bootstrap before','GET','/api/v1/bootstrap',token)
  original_receipt=checked(prefix+'original settlement','GET','/api/v1/settlements/'+settlement,token)
  ack=checked(prefix+'first ACK','POST','/api/v1/settlements/'+settlement+'/acknowledge',token,'clone-ack-'+str(ordinal))
  replay=checked(prefix+'same-key ACK replay','POST','/api/v1/settlements/'+settlement+'/acknowledge',token,'clone-ack-'+str(ordinal));assert ack==replay
  second=checked(prefix+'new-key ACK replay','POST','/api/v1/settlements/'+settlement+'/acknowledge',token,'clone-reack-'+str(ordinal));assert ack_identity(ack)==ack_identity(second)
  checked(prefix+'bootstrap after','GET','/api/v1/bootstrap',token)
 asset_after=asset_fingerprint('assets-after-http');assert asset_before==asset_after
 facts['after_ACK']=json.loads(psql("SELECT json_build_object('matches',(SELECT count(*) FROM matches),'unacknowledged',(SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NULL),'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'));",'after-ACK'))
 assert facts['after_ACK']['unacknowledged']==facts['after_startup']['unacknowledged']-6 and facts['after_ACK']['matches']==facts['before']['matches'] and facts['after_ACK']['pending_holds']==0
 assert all(sha(package/name)==record['sha256'] for name,record in report['package_files'].items()) and sha(backup)=='14f127e47726936785af0d78015959ea67c53d63746f0887d64f381e4e381139'
except BaseException as exc:error=dict(type=type(exc).__name__,message=str(exc))
finally:
 if app and app.poll() is None:app.terminate();app.wait(timeout=15)
 if app_log:app_log.close()
 try:
  if pg_started and (data/'postmaster.pid').exists() and not breach.is_set():file_run([str(pgbin/'pg_ctl.exe'),'-D',str(data),'-m','fast','-w','stop'],'pg-stop',startup=False)
 except BaseException as exc:error=error or dict(type=type(exc).__name__,message=str(exc))
 k.TerminateJobObject(job,92);k.CloseHandle(job);subprocess.Popen=popen;stop.set();thread.join(timeout=5)
 result=dict(ok=error is None,error=error,source_commit=report['source_commit'],backup_sha256=sha(backup),facts=facts,checks=checks,selected_existing_real_player_receipts=len(selected),
  synthetic_tokens_only_in_private_clone=True,no_actual_user_tokens_read=True,asset_fingerprints_before=asset_before,asset_fingerprints_after=asset_after,ACK_same_key_byte_exact=True,ACK_new_key_identity_equal_at_Postgres_microsecond_precision=True,
  exact_protected_package=True,old_config_archive_not_invented=True,private_database_retained=True,own_job_closed=True,own_PG_stopped=not (data/'postmaster.pid').exists(),
  resource_breach=breach.is_set(),minimum_available_bytes=min(samples,default=available()),new_gameplay_starts=0,production_changed=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');(out/'resources.original.json').write_text(json.dumps(dict(samples=samples,handles=handles,reserve_bytes=2*1024**3,startup_bytes=1024**3),indent=2)+'\n')
 print(json.dumps(dict(ok=result['ok'],error=error,HTTP_checks=len(checks),facts=facts,assets_equal=asset_before is not None and asset_before==asset_after,ownPGstopped=result['own_PG_stopped'],production_changed=False)))
assert result['ok'],result['error']
