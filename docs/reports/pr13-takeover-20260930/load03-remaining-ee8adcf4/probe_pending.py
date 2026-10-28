"""Actual frozen Gateway pending telemetry probe over owned loopback HTTP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(os.environ.get('PR13_SOURCE_ROOT','/workspace/godot_FanstaryCard')).resolve()
sys.path.insert(0,str(ROOT/'client/tests'))
sys.path.insert(0,str(ROOT/'tools'))
from fixture_runtime import isolated_environment
from gameplay_load_validation import aggregate_window

SCRIPT='''extends SceneTree
const Gateway = preload("res://network/gateway.gd")
var gateway: Node
var samples: Array = []
var finished := false
func _initialize() -> void: _run.call_deferred()
func _collect(sample: Dictionary) -> void: samples.append(sample.duplicate(true))
func _pending() -> void:
 await gateway.request("/api/v1/client-info?pending=1")
 finished = true
func _run() -> void:
 gateway = Gateway.new()
 gateway.persist_session = false
 root.add_child(gateway)
 gateway.telemetry.connect(_collect)
 gateway.telemetry_context = {"phase":"playing", "cycle_id":"M-cycle", "match_id":"M"}
 var first: Dictionary = await gateway.request("/api/v1/client-info")
 _pending()
 await create_timer(.5).timeout
 var paused := {"first_ok": first.ok, "production_pending_http": gateway._pending_http.size(),
  "production_pending_origins": gateway._http_origin_contexts.size(), "samples": samples.duplicate(true),
  "harness_invocations_started": 2, "harness_invocations_finished": 1}
 gateway.telemetry_context = {"phase":"settlement", "cycle_id":"N-cycle", "match_id":"N"}
 var http := HTTPRequest.new()
 root.add_child(http)
 http.request(OS.get_environment("FANTASYCARD_SERVER_URL") + "/fixture/release")
 await http.request_completed
 http.queue_free()
 var deadline := Time.get_ticks_msec()+3000
 while not finished and Time.get_ticks_msec()<deadline: await process_frame
 var result := {"paused":paused, "finished":finished, "final_samples":samples,
  "pending_after":gateway._pending_http.size(),"source":"f812 Gateway unchanged"}
 var file := FileAccess.open(OS.get_environment("PROBE_RESULT"), FileAccess.WRITE)
 file.store_string(JSON.stringify(result));file.close()
 print(JSON.stringify({"probe_complete":true,"finished":finished}))
 gateway._reusable_http.close()
 gateway.queue_free()
 await process_frame
 quit(0 if finished and first.ok else 1)
'''

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--godot',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
 fixture=out/'fixture';fixture.mkdir(exist_ok=True)
 proof=[]
 for rel in ['network/gateway.gd','network/http_protocol.gd','network/protobuf.gd','network/reusable_http_client.gd','data/http_endpoints.json','data/http_schema.json','data/realtime_schema.json']:
  src=ROOT/'client'/rel;dst=fixture/rel;dst.parent.mkdir(parents=True,exist_ok=True);b=src.read_bytes()
  assert b==subprocess.check_output(['git','show','f812879e:client/'+rel],cwd=ROOT)
  dst.write_bytes(b);proof.append(dict(path='client/'+rel,sha256=hashlib.sha256(b).hexdigest(),matches_f812=True))
 (fixture/'project.godot').write_text('[application]\nconfig/name="Frozen pending telemetry probe"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
 (fixture/'probe.gd').write_text(SCRIPT)
 release=threading.Event();requests=[];lock=threading.Lock()
 class Handler(BaseHTTPRequestHandler):
  protocol_version='HTTP/1.1'
  def log_message(self,*args):pass
  def do_GET(self):
   if self.path=='/fixture/release':release.set()
   else:
    with lock:requests.append(dict(path=self.path,started_monotonic=time.monotonic(),pending='pending=1' in self.path))
    if 'pending=1' in self.path:release.wait(timeout=8)
   body=b'{"configVersion":"probe"}'
   self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);self.wfile.flush()
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 result=out/'gateway-result.json';env=isolated_environment(fixture,FANTASYCARD_SERVER_URL=f'http://127.0.0.1:{server.server_port}',FANTASYCARD_LOAD_RUN_ID='owned-load03-probe',PROBE_RESULT=str(result))
 command=[args.godot,'--headless','--audio-driver','Dummy','--path',str(fixture),'--script','res://probe.gd']
 started=time.time()
 try:
  run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
  (out/'godot.log').write_text(run.stdout+run.stderr)
  assert run.returncode==0 and result.is_file(), 'Godot fixture execution failed; see untouched log'
  actual=json.loads(result.read_text());paused=actual['paused'];window=aggregate_window([{'operations':[r for r in paused['samples'] if r['type']=='http'],'telemetry':paused['samples']}])
  final=aggregate_window([{'operations':[r for r in actual['final_samples'] if r['type']=='http'],'telemetry':actual['final_samples']}])
  report={'runtime_source_sha':'f812879e4518fd09bf22656451cb563d62940298','harness_source_external':True,'aggregate_helper_source_sha':'ee8adcf40be9aebb1330156a3524910c08225ebc','aggregate_helper_sha256':hashlib.sha256((ROOT/'tools/gameplay_load_validation.py').read_bytes()).hexdigest(),'command':command,'exit_code':run.returncode,'elapsed_seconds':time.time()-started,'source_proof':proof,
   'actual_server_requests':requests,'paused_actual':paused,'paused_production_aggregate':window,'final_production_aggregate':final,
   'LOAD03_3_full_criterion':'started=each mutually exclusive terminal+pending; expose success/rejection/timeout/cancelled/decode_error/pending separately',
   'contract_gap_verified':len(requests)==2 and paused['production_pending_http']==1 and window['logical_request_count']==1 and not any(r.get('type') in ['http_started','http.start','http.request.started'] for r in paused['samples']),
   'late_origin_preserved':all(r.get('phase')=='playing' and r.get('cycle_id')=='M-cycle' for r in actual['final_samples']),
   'pending_count_exposed_by_production_aggregate':'pending_count' in window,
   'classification':'Reproduced acceptance accounting gap; not an asset/business failure; production remains unchanged', 'Accepted':False}
  (out/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['contract_gap_verified','late_origin_preserved','pending_count_exposed_by_production_aggregate','exit_code']}))
  return 0
 finally:
  release.set();server.shutdown();server.server_close();worker.join(timeout=5)

if __name__=='__main__':raise SystemExit(main())
