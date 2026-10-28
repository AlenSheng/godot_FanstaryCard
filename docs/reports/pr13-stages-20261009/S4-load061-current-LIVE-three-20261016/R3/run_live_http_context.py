import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from live_http_context_proxy import Proxy

B=pathlib.Path(__file__).resolve().parent;D=B/(sys.argv[1] if len(sys.argv)>1 else 'live-http-context-r1')
R=pathlib.Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard')
G=r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (D/'execution-intent.json').exists(),'No blind gameplay/network rerun'
sources=json.loads((D/'source-manifest.json').read_bytes())
assert all(sha(R/r['path'])==r['sha256']==sha(pathlib.Path(r['copy'])) for r in sources)
(D/'execution-intent.json').write_text(json.dumps({'started_ns':time.time_ns(),'no_source_upload':True})+'\n')
proxy=Proxy(D/'task-only-Windows-TLS-CA.pem');thread=threading.Thread(target=proxy.serve_forever,daemon=True);thread.start()
env={**os.environ,'FANTASYCARD_LOAD_RUN_ID':'pr13-http-context-01a14470-r1',
     'FANTASYCARD_SERVER_URL':'http://127.0.0.1:'+str(proxy.server_port),
     'PR13_HTTP_CONTEXT_REPORT':str(D/'native.original.json')}
try:
 result=subprocess.run([G,'--headless','--path',str(D/'project'),'--script','res://probe.gd'],
   env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=160)
 (D/'native.original.log').write_bytes(result.stdout)
finally:
 proxy.stop.set();proxy.shutdown();proxy.server_close();thread.join(3)
 if proxy.upstream is not None:proxy.upstream.close()
(D/'proxy.original.json').write_text(json.dumps(proxy.events,indent=2)+'\n')
unchanged=all(sha(R/r['path'])==r['sha256']==sha(pathlib.Path(r['copy'])) for r in sources)
(D/'process-result.json').write_text(json.dumps({'exit_code':result.returncode,'source_unchanged':unchanged,
 'proxy_shutdown':not thread.is_alive(),'no_cloud_files_written':True},indent=2)+'\n')
print(result.stdout.decode(errors='replace')[-4200:])
assert result.returncode==0 and unchanged and not thread.is_alive()
print((D/'native.original.json').read_text()[:1500])
