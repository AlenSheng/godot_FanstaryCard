import hashlib
import http.client
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs

def digest(x):return hashlib.sha256(x).hexdigest()
class Proxy(ThreadingHTTPServer):
 daemon_threads=True;allow_reuse_address=True
 def __init__(self,trust_file):
  super().__init__(('127.0.0.1',0),Handler)
  self.lock=threading.Lock();self.events=[];self.counts={};self.stop=threading.Event()
  self.tls_context=ssl.create_default_context(cafile=str(trust_file))
  assert self.tls_context.check_hostname and self.tls_context.verify_mode==ssl.CERT_REQUIRED
  self.upstream_lock=threading.Lock();self.upstream=None
 def record(self,kind,**kw):
  with self.lock:self.events.append({'event':kind,'monotonic_ns':time.monotonic_ns(),**kw})
 def upstream_request(self,method,path,body,headers,mode,number):
  with self.upstream_lock:
   reused=self.upstream is not None and self.upstream.sock is not None
   if self.upstream is None:self.upstream=http.client.HTTPSConnection('www.relicbound.cn',443,timeout=12,context=self.tls_context)
   connection=self.upstream
   try:
    if connection.sock is None:connection.connect()
    connection.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    self.record('verified_public_TLS',mode=mode,number=number,hostname='www.relicbound.cn',upstream_connection_reused=reused,
      certificate_sha256=digest(connection.sock.getpeercert(binary_form=True)),version=connection.sock.version())
    connection.request(method,path,body if method!='GET' else None,headers)
    response=connection.getresponse();raw=response.read(2*1024*1024+1);assert len(raw)<=2*1024*1024
    return response.status,response.getheader('Content-Type','application/protobuf'),raw
   except Exception:
    connection.close();self.upstream=None;raise
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def do_POST(self):self.forward()
 def do_GET(self):self.forward()
 def forward(self):
  parsed=urlsplit(self.path);mode=parse_qs(parsed.query).get('controlled',['setup'])[0]
  size=int(self.headers.get('Content-Length','0'));assert 0<=size<=65536
  body=self.rfile.read(size)
  headers={k:self.headers[k] for k in ['Content-Type','Accept','Authorization','Idempotency-Key','X-Trace-Id'] if k in self.headers}
  with self.server.lock:
   number=self.server.counts.get(mode,0)+1;self.server.counts[mode]=number
  self.server.record('local_request_received',mode=mode,number=number,path=parsed.path,method=self.command,
   request_body_sha256=digest(body),idempotency_key_sha256=digest(headers.get('Idempotency-Key','').encode()),
   trace_id_sha256=digest(headers.get('X-Trace-Id','').encode()))
  try:
   status,media,raw=self.server.upstream_request(self.command,parsed.path,body,headers,mode,number)
  except Exception as e:
   self.server.record('upstream_error',mode=mode,number=number,error_type=type(e).__name__)
   self.close_connection=True;return
  self.server.record('actual_backend_response',mode=mode,number=number,path=parsed.path,method=self.command,
    status=status,bytes=len(raw),original_response_sha256=digest(raw),request_body_sha256=digest(body),
    idempotency_key_sha256=digest(headers.get('Idempotency-Key','').encode()),trace_id_sha256=digest(headers.get('X-Trace-Id','').encode()))
  if mode=='retry-two' and number<=2:
   self.server.record('original_response_dropped',mode=mode,number=number)
   self.close_connection=True
   try:self.connection.shutdown(socket.SHUT_RDWR)
   except OSError:pass
   return
  if mode=='late-cycle':self.server.stop.wait(1.0)
  if mode=='timeout' and number==1:self.server.stop.wait(12.0)
  delivered=b'\x0f' if mode=='decode-error' else raw
  try:
   self.send_response(status);self.send_header('Content-Type',media)
   self.send_header('Content-Length',str(len(delivered)));self.send_header('Connection','close');self.end_headers()
   self.wfile.write(delivered);self.wfile.flush()
   self.server.record('delivered',mode=mode,number=number,status=status,body_sha256=digest(delivered),bytes=len(delivered),corrupted=mode=='decode-error')
  except (OSError,ConnectionError):self.server.record('client_closed_before_delivery',mode=mode,number=number)
  self.close_connection=True
