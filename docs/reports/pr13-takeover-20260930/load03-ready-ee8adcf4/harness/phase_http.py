from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
B=Path(__file__).resolve().parents[1];E=B/'evidence/phase';E.mkdir(exist_ok=True)
sys.path.insert(0,str(B/'source/tools'));from gameplay_load_validation import aggregate_window
godot='/workspace/relicround-env/godot/Godot_v4.7.2-stable_linux.x86_64';commands=[]
def run(stage,extra,env=None):
 cmd=[godot,'--headless','--audio-driver','Dummy','--path',str(B/'fixture')]+extra;start=time.monotonic();r=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=20);(E/(stage+'.stdout.log')).write_text(r.stdout);(E/(stage+'.stderr.log')).write_text(r.stderr);commands.append({'stage':stage,'command':cmd,'exit_code':r.returncode,'elapsed_real_seconds':time.monotonic()-start});assert r.returncode==0
run('encode',['--script','res://encode_fixture.gd'])
receipts=[]
for mode in ['playing','settlement','legacy','login','initial','matchmaking','cleanup']:
 release=threading.Event();arrivals=[]
 class Handler(BaseHTTPRequestHandler):
  protocol_version='HTTP/1.1'
  def do_GET(self):
   arrivals.append({'path':self.path,'at_monotonic_ns':time.monotonic_ns()})
   if self.path=='/fixture/release':release.set();payload=b'{}';media='application/json'
   else:
    if not release.wait(5):self.send_error(504);return
    payload=(B/'fixture'/('settlement.pb' if mode=='settlement' else 'bootstrap.pb')).read_bytes();media='application/protobuf'
   self.send_response(200);self.send_header('Content-Type',media);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
  def log_message(self,*args):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 path=E/(mode+'.json');env=dict(os.environ,FANTASYCARD_SERVER_URL=f'http://127.0.0.1:{server.server_port}',PHASE_MODE=mode,PHASE_RESULT=str(path),XDG_DATA_HOME=str(E/'owned-userdata'))
 try:run(mode,['--script','res://phase_probe.gd'],env)
 finally:release.set();server.shutdown();server.server_close()
 raw=json.loads(path.read_text());events=raw['events'];logical=[r for r in events if r['type']=='http'];aggregate=aggregate_window([{'operations':logical,'telemetry':events}]);phase='unknown/legacy' if mode=='legacy' else mode
 ok=raw['result']['ok'] and raw['pending_before_release']==1 and len(logical)==1 and logical[0]['cycle_id']=='M-cycle' and aggregate['phase_http'][phase]['count']==1 and aggregate['steady_sample_count']==(1 if mode=='settlement' else 0) and raw['requested_monotonic_ms']<raw['context_changed_monotonic_ms']<=raw['logical_received_monotonic_ms']
 if mode!='legacy':ok=ok and logical[0]['phase']==mode
 receipts.append({'case_id':'LOAD-03.2-T0'+str(len(receipts)+1) if len(receipts)<3 else 'LOAD-03.2-ADDITIONAL-'+mode,'passed':ok,'actual_gateway':raw,'actual_aggregate':aggregate,'actual_http_arrivals':arrivals,'legacy_auth_excluded_separate':True,'no_PG_or_capacity_claim':True})
assert all(r['passed'] for r in receipts)
(E/'receipts.json').write_text(json.dumps(receipts,indent=2));(E/'commands.json').write_text(json.dumps(commands,indent=2));print(json.dumps({'canonical_passed':3,'additional_phase_strata':len(receipts)-3,'actual_Gateway':True,'actual_HTTP_SCHEMA_protobuf':True}))
