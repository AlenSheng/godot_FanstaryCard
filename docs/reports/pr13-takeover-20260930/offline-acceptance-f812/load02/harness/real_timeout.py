"""Owned loopback HTTP stall, actual Godot/Gateway and frozen runner report path."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import subprocess
import threading
import time

BASE=Path(__file__).resolve().parents[1]
out=BASE/'evidence/real-timeout';out.mkdir(parents=True,exist_ok=True)
arrivals=[];stop=threading.Event()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        arrivals.append({'path':self.path,'monotonic_ns':time.monotonic_ns(),'wall_time':time.time()})
        stop.wait(40)
    def log_message(self,*args): pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
godot='/workspace/relicround-env/godot/Godot_v4.7.2-stable_linux.x86_64'
env=dict(os.environ,FANTASYCARD_SERVER_URL=f'http://127.0.0.1:{server.server_port}',FANTASYCARD_LOAD_REPORT=str(out/'client.json'),FANTASYCARD_LOAD_STOP_FILE=str(out/'STOP'),XDG_DATA_HOME=str(out/'owned-userdata'))
commands=[]
try:
    for stage,extra in [('import',['--editor','--import','--quit']),('timeout',['--script','res://tests/load02_timeout_fixture.gd'])]:
        cmd=[godot,'--headless','--audio-driver','Dummy','--max-fps','60','--path',str(BASE/'source/client')]+extra
        started=time.monotonic();r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=90)
        (out/f'{stage}.stdout.log').write_text(r.stdout);(out/f'{stage}.stderr.log').write_text(r.stderr)
        commands.append({'stage':stage,'command':cmd,'exit_code':r.returncode,'real_elapsed_seconds':time.monotonic()-started,'target':env['FANTASYCARD_SERVER_URL']})
finally:
    stop.set();server.shutdown();server.server_close()
(out/'commands.json').write_text(json.dumps(commands,indent=2));(out/'http-arrivals.json').write_text(json.dumps(arrivals,indent=2))
print(json.dumps(commands))
