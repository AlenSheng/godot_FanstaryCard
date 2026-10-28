"""Actual production Program, opaque byte proxy and production Godot gateway."""
import hashlib,http.client,json,os,re,shutil,subprocess,sys,threading,time,urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
E=Path('/evidence');D=Path('/client');meta=json.loads(Path('/meta.json').read_bytes());project='/work/server/src/FantasyCard.Server/FantasyCard.Server.csproj';phases=[]
def phase(name,args,timeout):
 with (E/(name+'.log')).open('xb') as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,cwd='/work/server')
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(path,value):assert not path.exists();path.write_text(json.dumps(value,indent=2)+'\n')
P=E/'godot';shutil.copytree(D,P);sys.path.insert(0,str(P/'tests'));from http_protobuf_fixture import encode
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def handle_one_request(self):
  try:super().handle_one_request()
  except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError):self.close_connection=True
 def send(self,status,body,media='application/protobuf',headers=None):
  self.send_response(status);self.send_header('Content-Type',media);self.send_header('Content-Length',str(len(body)))
  for k,v in (headers or {}).items():self.send_header(k,str(v))
  self.end_headers()
  try:self.wfile.write(body);self.wfile.flush()
  except (BrokenPipeError,ConnectionResetError,OSError):pass
 def handle_proxy(self):
  from urllib.parse import parse_qs,urlsplit
  url=urlsplit(self.path);mode=parse_qs(url.query).get('mode',[''])[0];length=int(self.headers.get('Content-Length','0'));assert 0<=length<=65536;body=self.rfile.read(length);key=self.headers.get('Idempotency-Key','')
  with self.server.lock:self.server.counts[self.path]+=1;count=self.server.counts[self.path]
  if self.command=='GET' and self.path=='/api/v1/client-info':
   with self.server.lock:stats={'counts':dict(self.server.counts),'fixtureMutations':self.server.committed_then_503,'writeStable':len(self.server.write_ids)==2 and self.server.write_ids[0]==self.server.write_ids[1],'staleCaptured':self.server.stale_captured.is_set()}
   self.send(200,json.dumps(stats).encode(),'application/json');return
  if mode in ('retry-five','stop-retry') and count==1:
   self.send(429,encode('HttpError',{'status':429,'detail':'Declared five-second retry fault','retry_after_seconds':5}),headers={'Retry-After':'5'});return
  headers={k:self.headers[k] for k in ('Content-Type','Accept','Authorization','Idempotency-Key','X-Trace-Id') if k in self.headers};connection=http.client.HTTPConnection('127.0.0.1',self.server.backend_port,timeout=10)
  try:connection.request(self.command,url.path,body=body if self.command!='GET' else None,headers=headers);response=connection.getresponse();raw=response.read(2*1024**2+1);assert len(raw)<=2*1024**2;status=response.status;media=response.getheader('Content-Type','application/protobuf')
  finally:connection.close()
  entry={'method':self.command,'path':self.path,'fault_mode':mode,'backend_status':status,'original_backend_response_sha256':sha(raw),'original_backend_response_bytes':len(raw),'request_body_sha256':sha(body),'request_key_sha256':sha(key.encode()),'trace_id':self.headers.get('X-Trace-Id',''),'client_loopback_peer_port':self.connection.getpeername()[1]}
  with self.server.lock:
   self.server.forwarded.append(entry)
   if mode=='lost-write':self.server.write_ids.append((sha(body),sha(key.encode())));self.server.lost_key=key
   if mode=='overlap-write':self.server.overlap_key=key
  if mode=='lost-write' and count==1:
   assert status==200,'Original purchase must commit before response loss is injected'
   with self.server.lock:self.server.committed_then_503+=1
   self.send(503,encode('HttpError',{'status':503,'detail':'Actual committed response deliberately withheld'}));return
  if mode=='stale-get':
   if count==1:
    assert status==200;self.server.stale_captured.set();assert self.server.new_get_read.wait(8),'Fresh post-write GET never reached backend';time.sleep(.15)
   else:self.server.new_get_read.set()
  elif self.command=='PUT' and url.path=='/api/v1/players/me':assert status==200
  if mode=='decode-error':self.send(200,b'\x00');return
  if mode=='timeout':time.sleep(.4)
  elif mode in ('slow-context','singleflight','separate-players','overlap-a','overlap-b','overlap-write'):time.sleep(.25)
  self.send(status,raw,media)
 def do_GET(self):self.handle_proxy()
 def do_POST(self):self.handle_proxy()
 def do_PUT(self):self.handle_proxy()
server=None;server_log=None;out={'ok':False,'MAIN_accepted':False,'production_source_sha':meta['production_source_sha']}
try:
 sdk=subprocess.check_output(['dotnet','--version'],cwd='/work/server',text=True).strip();assert sdk==json.loads(Path('/work/server/global.json').read_bytes())['sdk']['version'];write(E/'sdk.original.json',{'actual_sdk':sdk,'godot_version':subprocess.check_output(['godot','--version'],text=True).strip()})
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 dll=Path('/artifacts/bin/FantasyCard.Server/release/FantasyCard.Server.dll');assert dll.is_file();write(E/'compiled-server.original.json',{'dll_sha256':sha(dll.read_bytes()),'built_from_frozen_sources':True})
 phase('godot-import',['godot','--headless','--path',str(P),'--editor','--import','--quit'],90)
 backend_port=38972;env={**os.environ,'ASPNETCORE_ENVIRONMENT':'Development','ASPNETCORE_URLS':f'http://127.0.0.1:{backend_port}','ConnectionStrings__Postgres':os.environ['FANTASYCARD_TEST_POSTGRES'],'Identity__EnableLocalAuth':'true','ProtobufHttp__AllowLegacyJson':'false','Realtime__AllowLegacyAccessTokenQuery':'false','Matchmaking__BotFillDelaySeconds':'30','Logging__LogLevel__Default':'Warning','Logging__LogLevel__FantasyCard':'Warning'}
 server_log=(E/'server.original.log').open('xb');server=subprocess.Popen(['dotnet',str(dll)],cwd='/work/server',env=env,stdout=server_log,stderr=subprocess.STDOUT);until=time.monotonic()+45
 while True:
  assert server.poll() is None and time.monotonic()<until,'Original isolated backend startup failed'
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{backend_port}/health/ready',timeout=1) as h:
    if h.status==200:break
  except Exception:time.sleep(.25)
 arms=[]
 for arm in ('per-request','reusable'):
  dst=E/arm;dst.mkdir();proxy=ThreadingHTTPServer(('127.0.0.1',0),Handler);proxy.daemon_threads=True;proxy.lock=threading.Lock();proxy.counts=Counter();proxy.forwarded=[];proxy.write_ids=[];proxy.committed_then_503=0;proxy.lost_key='';proxy.overlap_key='';proxy.stale_captured=threading.Event();proxy.new_get_read=threading.Event();proxy.backend_port=backend_port;thread=threading.Thread(target=proxy.serve_forever,daemon=True);thread.start();native_env={**os.environ,'FANTASYCARD_SERVER_URL':f'http://127.0.0.1:{proxy.server_port}','FANTASYCARD_LOAD_HTTP_TRANSPORT':arm,'PR13_HTTP_ARM':arm,'PR13_HTTP_REPORT':str(dst/'native-result.original.json'),'XDG_DATA_HOME':str(dst/'user-data'),'XDG_CONFIG_HOME':str(dst/'user-config'),'XDG_CACHE_HOME':str(dst/'user-cache')}
  try:
   with (dst/'godot.original.log').open('xb') as log:p=subprocess.run(['godot','--headless','--max-fps','60','--path',str(P),'--script','res://tests/pr13_real_pg_http_context.gd'],env=native_env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
  finally:proxy.shutdown();proxy.server_close();thread.join(timeout=5)
  text=(dst/'godot.original.log').read_text(errors='replace');native=json.loads((dst/'native-result.original.json').read_bytes()) if (dst/'native-result.original.json').exists() else {};rows=native.get('cases',[]);assert p.returncode==0 and not any(x in text for x in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use')) and len(rows)==13 and all(r['status']=='Passed' for r in rows),'Actual Godot HTTP assertions failed'
  assert len(native['initial_players'])==2 and len({r['user_id'] for r in native['initial_players']})==2;lost=[r for r in proxy.forwarded if r['fault_mode']=='lost-write'];assert len(lost)==2 and all(r['backend_status']==200 for r in lost) and len({r['request_body_sha256'] for r in lost})==len({r['request_key_sha256'] for r in lost})==1 and proxy.committed_then_503==1
  write(dst/'opaque-proxy.original.json',{'forwarded':proxy.forwarded,'counts':dict(proxy.counts),'controlled_faults':['429 Retry-After=5','response delay','actual committed 200 withheld as 503','truncated decode body'],'bearer_credentials_not_logged':True,'backend_responses_never_reencoded':True,'legacy_JSON_not_used':True})
  evidence={'arm':arm,'native_exit_code':p.returncode,'native_rows':13,'native_case_ids':[r['case_id'] for r in rows],'players':native['initial_players'],'lost_request_id':proxy.lost_key,'overlap_request_id':proxy.overlap_key,'actual_committed_responses_before_503':1,'final_PG_postconditions_still_required':True};write(dst/'database-postconditions-request.original.json',evidence);arms.append(evidence)
 for row in meta['client_files']:
  path=P/row['path'];assert path.stat().st_size==row['bytes'] and sha(path.read_bytes())==row['sha256']
 out.update(ok=True,arms=arms,phases=phases,frozen_executed_client_bytes_unchanged=True,final_PG_postconditions_still_required=True)
except Exception as error:out.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
finally:
 if server is not None:
  if server.poll() is None:server.terminate()
  try:server.wait(timeout=15)
  except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
  out['owned_backend_stopped']=True
 if server_log is not None:server_log.close()
 write(E/'inner-result.original.json',out)
raise SystemExit(0 if out['ok'] else 1)
