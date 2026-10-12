import hashlib,http.client,json,os,re,shutil,socket,ssl,subprocess,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
E=Path('/evidence');D=Path('/client');P=E/'godot';meta=json.loads(Path('/meta.json').read_bytes());phases=[];server=None;server_log=None;listeners=[];out={'ok':False,'MAIN_accepted':False,'production_source_sha':meta['production_source_sha']}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(p,v):assert not p.exists();p.write_text(json.dumps(v,indent=2)+'\n')
def phase(name,args,timeout,cwd='/work/server'):
 with (E/(name+'.log')).open('xb') as log:r=subprocess.run(args,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
class TLSFixture(ThreadingHTTPServer):
 daemon_threads=True
 def get_request(self):
  try:return super().get_request()
  except ssl.SSLError as error:
   with self.lock:self.failed_handshakes.append({'type':type(error).__name__,'reason':error.reason})
   raise
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def do_GET(self):self.forward()
 def do_POST(self):self.forward()
 def forward(self):
  from urllib.parse import urlsplit,parse_qs
  parsed=urlsplit(self.path);mode=parse_qs(parsed.query).get('mode',[''])[0];n=int(self.headers.get('Content-Length','0'));assert 0<=n<=65536;body=self.rfile.read(n);headers={k:self.headers[k] for k in ('Content-Type','Accept','Authorization','Idempotency-Key','X-Trace-Id') if k in self.headers};c=http.client.HTTPConnection('127.0.0.1',38972,timeout=10)
  try:c.request(self.command,parsed.path,body=body if self.command!='GET' else None,headers=headers);r=c.getresponse();raw=r.read(2*1024**2+1);status=r.status;media=r.getheader('Content-Type','application/protobuf');assert len(raw)<=2*1024**2
  finally:c.close()
  record={'method':self.command,'path':self.path,'mode':mode,'original_backend_status':status,'original_backend_bytes':len(raw),'original_backend_body_sha256':sha(raw),'client_peer_port':self.connection.getpeername()[1],'token_not_logged':True}
  if status>=400:record['actual_backend_error_hex']=raw[:4096].hex()
  wire=raw;chunked=mode in ('complete-chunk','truncated-chunk');closing=mode in ('close-length','close-body','truncated-length','truncated-chunk')
  if mode in ('truncated-length','truncated-chunk'):wire=raw[:-1];assert status==200 and raw
  if mode=='oversized-optional':
   def varint(v):
    b=bytearray()
    while v>=128:b.append((v&127)|128);v>>=7
    b.append(v);return bytes(b)
   padding=b'\0'*(2*1024**2+1);wire=raw+varint((19000<<3)|2)+varint(len(padding))+padding;record['declared_unknown_optional_padding_bytes']=len(padding)
  self.send_response(status);self.send_header('Content-Type',media)
  if chunked:self.send_header('Transfer-Encoding','chunked')
  elif mode!='close-body':self.send_header('Content-Length',str(len(raw) if mode=='truncated-length' else len(wire)))
  if closing:self.send_header('Connection','close');self.close_connection=True
  self.end_headers();record['TLS_framing_injection']=mode or 'none';record['application_body_bytes_offered']=len(wire)
  with self.server.lock:self.server.records.append(record)
  try:
   if chunked:
    self.wfile.write(format(len(wire),'x').encode()+b'\r\n'+wire+b'\r\n')
    if mode=='complete-chunk':self.wfile.write(b'0\r\n\r\n')
   else:self.wfile.write(wire)
   self.wfile.flush()
   if mode=='close-body':
    # EOF delimits this body. A successful TLS response therefore needs a
    # close_notify; Python's ordinary SSLSocket.close only closes the TCP FD.
    self.connection.settimeout(5)
    transport=self.connection.unwrap()
    transport.close()
    record['clean_TLS_close_notify_sent']=True
  except (BrokenPipeError,ConnectionResetError,ssl.SSLError,OSError) as error:
   record['close_or_body_write_error_type']=type(error).__name__
try:
 shutil.copytree(D,P);tls=E/'private-tls';tls.mkdir();config=tls/'req.cnf';config.write_text('[req]\ndistinguished_name=dn\n[dn]\n');ext=tls/'leaf.ext';ext.write_text('subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
 phase('trusted-ca',['openssl','req','-config',str(config),'-x509','-newkey','rsa:2048','-nodes','-keyout',str(tls/'ca.key'),'-out',str(tls/'ca.pem'),'-days','1','-subj','/CN=PR13 owned fixture CA','-addext','basicConstraints=critical,CA:TRUE'],30,cwd='/tmp')
 phase('trusted-csr',['openssl','req','-config',str(config),'-newkey','rsa:2048','-nodes','-keyout',str(tls/'leaf.key'),'-out',str(tls/'leaf.csr'),'-subj','/CN=localhost'],30,cwd='/tmp')
 phase('trusted-leaf',['openssl','x509','-req','-in',str(tls/'leaf.csr'),'-CA',str(tls/'ca.pem'),'-CAkey',str(tls/'ca.key'),'-CAcreateserial','-out',str(tls/'leaf.pem'),'-days','1','-extfile',str(ext)],30,cwd='/tmp')
 phase('untrusted-cert',['openssl','req','-config',str(config),'-x509','-newkey','rsa:2048','-nodes','-keyout',str(tls/'bad.key'),'-out',str(tls/'bad.pem'),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],30,cwd='/tmp')
 write(E/'certificate-public-provenance.json',{'trusted_CA_sha256':sha((tls/'ca.pem').read_bytes()),'trusted_leaf_sha256':sha((tls/'leaf.pem').read_bytes()),'untrusted_leaf_sha256':sha((tls/'bad.pem').read_bytes()),'only_isolated_project_certificate_bundle_override':True,'system_trust_store_changed':False})
 project='/work/server/src/FantasyCard.Server/FantasyCard.Server.csproj';phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480);phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 dll=Path('/artifacts/bin/FantasyCard.Server/release/FantasyCard.Server.dll');assert dll.is_file();write(E/'compiled-server.original.json',{'dll_sha256':sha(dll.read_bytes()),'actual_frozen_current_equivalent_source':True});phase('godot-import',['godot','--headless','--path',str(P),'--editor','--import','--quit'],90)
 env={**os.environ,'ASPNETCORE_ENVIRONMENT':'Development','ASPNETCORE_URLS':'http://127.0.0.1:38972','ConnectionStrings__Postgres':os.environ['FANTASYCARD_TEST_POSTGRES'],'Identity__EnableLocalAuth':'true','ProtobufHttp__AllowLegacyJson':'false','Realtime__AllowLegacyAccessTokenQuery':'false','Matchmaking__BotFillDelaySeconds':'30','Logging__LogLevel__Default':'Warning','Logging__LogLevel__FantasyCard':'Warning'};server_log=(E/'server.original.log').open('xb');server=subprocess.Popen(['dotnet',str(dll)],cwd='/work/server',env=env,stdout=server_log,stderr=subprocess.STDOUT);until=time.monotonic()+45
 while True:
  assert server.poll() is None and time.monotonic()<until
  try:
   with urllib.request.urlopen('http://127.0.0.1:38972/health/ready',timeout=1) as r:
    if r.status==200:break
  except Exception:time.sleep(.25)
 for label,cert,key in (('trusted','leaf.pem','leaf.key'),('untrusted','bad.pem','bad.key')):
  proxy=TLSFixture(('127.0.0.1',0),Handler);proxy.lock=threading.Lock();proxy.records=[];proxy.failed_handshakes=[];ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(tls/cert,tls/key);proxy.socket=ctx.wrap_socket(proxy.socket,server_side=True);thread=threading.Thread(target=proxy.serve_forever,daemon=True);thread.start();listeners.append((label,proxy,thread))
 native_env={**os.environ,'FANTASYCARD_SERVER_URL':'https://localhost:'+str(listeners[0][1].server_port),'PR13_TLS_UNTRUSTED_ORIGIN':'https://localhost:'+str(listeners[1][1].server_port),'PR13_TLS_REPORT':str(E/'native-result.original.json'),'XDG_DATA_HOME':str(E/'user-data'),'XDG_CONFIG_HOME':str(E/'user-config'),'XDG_CACHE_HOME':str(E/'user-cache')}
 with (E/'godot.original.log').open('xb') as log:native=subprocess.run(['godot','--headless','--max-fps','60','--path',str(P),'--script','res://tests/pr13_real_pg_tls_framing.gd'],env=native_env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
 result=json.loads((E/'native-result.original.json').read_bytes()) if (E/'native-result.original.json').exists() else {};log=(E/'godot.original.log').read_text();errors=[line.strip() for line in log.splitlines() if 'ERROR:' in line];expected=[line for line in errors if re.fullmatch('ERROR: TLS handshake error: -[0-9]+',line)];assert native.returncode==0 and result.get('ok') is True and len(result['cases'])==3 and all(r['status']=='Passed' for r in result['cases']) and len(expected)==1 and errors==expected and not any(x in log for x in ('SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use')),'Original TLS native assertions failed'
 trusted=listeners[0][1];bad=listeners[1][1];assert len(bad.failed_handshakes)==1 and not bad.records;profile_records=[r for r in trusted.records if r['method']=='GET'];assert profile_records and all(r['original_backend_status']==200 for r in profile_records) and len({r['original_backend_body_sha256'] for r in profile_records})==1;same={r['mode']:r for r in profile_records};assert same['close-length']['client_peer_port']!=same['after-close']['client_peer_port'];write(E/'opaque-TLS-source-and-framing-proof.json',{'trusted_original_backend_records':trusted.records,'untrusted_original_backend_records':bad.records,'actual_untrusted_handshake_rejections':bad.failed_handshakes,'expected_TLS_log_lines':expected,'all_success_bodies_from_actual_authenticated_PostgreSQL_profile':True,'original_backend_success_bodies_never_reencoded':True})
 for row in meta['client_files']:
  p=P/row['path'];assert p.stat().st_size==row['bytes'] and sha(p.read_bytes())==row['sha256']
 out.update(ok=True,native_exit_code=0,native_rows_passed=3,expected_TLS_errors=expected,actual_player_id=result['actual_player_id'],actual_profile_version=result['original_profile_version'],all_TLS_body_framing_assertions_passed=True,untrusted_TLS_never_reached_backend=True,frozen_executed_client_bytes_unchanged=True,final_PG_postconditions_still_required=True,phases=phases)
except Exception as error:out.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
finally:
 for label,proxy,thread in listeners:
  proxy.shutdown();proxy.server_close();thread.join(timeout=5);path=E/(label+'-TLS-original-requests.json')
  if not path.exists():write(path,{'records':proxy.records,'handshake_rejections':proxy.failed_handshakes})
 if server is not None:
  if server.poll() is None:server.terminate()
  try:server.wait(timeout=15)
  except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
  out['owned_backend_stopped']=True
 if server_log is not None:server_log.close()
 write(E/'inner-result.original.json',out)
raise SystemExit(0 if out['ok'] else 1)
