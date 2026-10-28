"""Actual owned HTTP bytes, retries and immutable context canonical cases."""
import argparse
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import shutil
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client/tests'))
from fixture_runtime import isolated_environment
from http_protobuf_fixture import encode

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def handle_one_request(self):
        try:super().handle_one_request()
        except (ConnectionResetError,ConnectionAbortedError):self.close_connection=True
    def send(self,code,body,media='application/protobuf',extra=None):
        self.send_response(code);self.send_header('Content-Type',media);self.send_header('Content-Length',str(len(body)))
        for k,v in (extra or {}).items():self.send_header(k,str(v))
        self.end_headers()
        try:self.wfile.write(body);self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,OSError):pass
    def do_GET(self):
        mode=parse_qs(urlsplit(self.path).query).get('mode',[''])[0]
        with self.server.lock:
            self.server.counts[self.path]+=1;count=self.server.counts[self.path]
        if self.path=='/api/v1/client-info':
            with self.server.lock:
                stats={'counts':dict(self.server.counts),'fixtureMutations':self.server.mutations,'writeStable':len(self.server.writes)==2 and self.server.writes[0]==self.server.writes[1],'retryWriteTwoAttempts':list(self.server.retry_write_two)}
            self.send(200,json.dumps(stats).encode(),'application/json');return
        if mode in ('retry-five','stop-retry') and count==1:
            self.send(429,encode('HttpError',{'status':429,'detail':'controlled wait','retry_after_seconds':5}),extra={'Retry-After':5});return
        if mode=='timeout':time.sleep(.4)
        elif mode in ('slow-context','singleflight','separate-players','overlap-a','overlap-b'):time.sleep(.25)
        if mode=='decode-error':self.send(200,b'\x00');return
        account=self.headers.get('Authorization','').removeprefix('Bearer ')
        self.send(200,encode('PlayerProfileResponse',{'user_id':account,'display_name':mode,'version':count}))
    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        identity=(hashlib.sha256(body).hexdigest(),hashlib.sha256(self.headers.get('Idempotency-Key','').encode()).hexdigest())
        mode=parse_qs(urlsplit(self.path).query).get('mode',[''])[0]
        with self.server.lock:
            self.server.counts[self.path]+=1;count=self.server.counts[self.path]
            if mode=='retry-write-two':
                self.server.retry_write_two.append({'body_sha256':identity[0],'key_sha256':identity[1],'trace_sha256':hashlib.sha256(self.headers.get('X-Trace-Id','').encode()).hexdigest()})
            if mode=='lost-write':
                self.server.writes.append(identity)
                if identity not in self.server.applied:self.server.applied.add(identity);self.server.mutations+=1
        if self.headers.get('Content-Type')!='application/protobuf':self.send(415,b'');return
        if mode=='retry-write-two' and count<=2:self.send(503,encode('HttpError',{'status':503,'detail':'controlled two-retry write'}));return
        if mode=='lost-write' and count==1:self.send(503,encode('HttpError',{'status':503,'detail':'controlled lost acknowledgement'}));return
        if mode=='overlap-write':time.sleep(.25)
        self.send(200,encode('ShopPurchaseResponse',{'product_id':'controlled-fixture','gold_after':7}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--godot',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--transport',choices=('reusable','per-request'),default='reusable');args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']}
    paths=['tools/pr13_http_cases.py','client/tests/pr13_http_context_cases.gd','client/tests/fixture_runtime.py','client/tests/http_protobuf_fixture.py']
    paths+=subprocess.check_output(['git','ls-files','client/network','client/data/http_schema.json','client/data/http_endpoints.json','client/data/realtime_schema.json'],cwd=ROOT,text=True).splitlines()
    inputs={path:sha(ROOT/path) for path in sorted(set(paths))};head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    # HTTP component cases need Gateway only; application autoloads own separate
    # lobby sockets and must not contact the loopback HTTP fixture.
    project=out/'runtime'/'project';project.mkdir(parents=True)
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="HTTPComponentCases"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
    for relative in inputs:
        if relative.startswith('client/network/') or relative in ('client/data/http_schema.json','client/data/http_endpoints.json','client/data/realtime_schema.json','client/tests/pr13_http_context_cases.gd'):
            target=project/Path(relative).relative_to('client');target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,target)
            if sha(target)!=inputs[relative]:raise ValueError('Copied native source differs')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    server.lock=threading.Lock();server.counts=Counter();server.mutations=0;server.applied=set();server.writes=[];server.retry_write_two=[]
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    env=isolated_environment(out,FANTASYCARD_SERVER_URL=f'http://127.0.0.1:{server.server_port}',FANTASYCARD_LOAD_RUN_ID='http-context-contract',FANTASYCARD_LOAD_HTTP_TRANSPORT=args.transport,PR13_HTTP_REPORT=str(out/'native-result.json'))
    command=[args.godot,'--headless','--path',str(project),'--script','res://tests/pr13_http_context_cases.gd'];start=time.monotonic();code=None
    try:
        with (out/'engine.log').open('wb') as log:
            child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:code=child.wait(timeout=90)
            except subprocess.TimeoutExpired:pass
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)
    finally:server.shutdown();server.server_close();worker.join(timeout=5)
    log=(out/'engine.log').read_text(encoding='utf8',errors='replace');clean=code is not None and not any(marker in log for marker in ('ERROR:','SCRIPT ERROR','Parse Error','Failed to load script','ObjectDB instances were leaked','resources still in use'))
    if any(sha(ROOT/path)!=value for path,value in inputs.items()):raise ValueError('Native runtime inputs changed during execution')
    rows=json.loads((out/'native-result.json').read_text(encoding='utf8'))['cases'] if (out/'native-result.json').is_file() else []
    for row in rows:
        row.update(setup=contracts[row['case_id']]['setup_and_injection'],expected=contracts[row['case_id']]['expected'])
        if not clean:row.update(status='Failed',native_execution_invalid=True)
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows).encode())
    write(out/'report.json',{'source_sha':head,'plan_sha256':sha(plan_path),'source':{'scope':'actual Godot binary loopback HTTP; fixture mutation is not PG asset proof','input_hashes':inputs},'executed':len(rows),'passed':sum(row['status']=='Passed' for row in rows),'transport':args.transport,'exit_code':code,'native_execution_clean':clean,'owned_service_closed':not worker.is_alive(),'elapsed_seconds':time.monotonic()-start,'accepted':False})
    write(out/'commands.json',{'command':command,'exit_code':code,'timeout_seconds':90,'engine_version':subprocess.check_output([args.godot,'--version'],text=True).strip()})
    write(out/'manifest.json',{'files':[{'path':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(out.glob('*')) if f.is_file()]})
    print(json.dumps({'executed':len(rows),'passed':sum(row['status']=='Passed' for row in rows),'failed':[r['case_id'] for r in rows if r['status']!='Passed'],'native_clean':clean}));return 0 if code==0 and clean and len(rows)==12 and all(row['status']=='Passed' for row in rows) else 1
if __name__=='__main__':raise SystemExit(main())
