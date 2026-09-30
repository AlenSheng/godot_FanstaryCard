"""Reproducible isolated Godot/loopback tests; never launches the real game or contacts production."""
import argparse, importlib.util, json, os, shutil, subprocess, threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from fixture_runtime import isolated_environment

parser = argparse.ArgumentParser()
parser.add_argument('--godot', required=True)
parser.add_argument('--work-dir', default='work/client-fixture')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
work = (repo / args.work_dir).resolve()
for folder in ['network','data','tests']: (work / folder).mkdir(parents=True, exist_ok=True)
for name in ['protobuf.gd','http_protocol.gd','gateway.gd','reusable_http_client.gd']: shutil.copyfile(repo/'client/network'/name, work/'network'/name)
for name in ['http_schema.json','http_endpoints.json','realtime_schema.json']: shutil.copyfile(repo/'client/data'/name, work/'data'/name)
shutil.copyfile(repo/'protocol/golden-vectors.json',work/'data/golden-vectors.json')
for name in ['test_protobuf.gd','test_http_protobuf_client.gd','test_http_protobuf_transport.gd']: shutil.copyfile(repo/'client/tests'/name, work/'tests'/name)
(work/'project.godot').write_text('[application]\nconfig/name="Protobuf isolated fixture"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
env = isolated_environment(work, FANTASYCARD_SERVER_URL='http://127.0.0.1:38971')
records = []
def run(extra, label):
    command = [args.godot,'--headless','--path',str(work)] + extra
    try:
        result = subprocess.run(command,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b'') + (exc.stderr or b'')
        if isinstance(output, bytes): output = output.decode('utf-8', errors='replace')
        (work/(label+'.log')).write_text(output+'\nFIXTURE TIMEOUT',encoding='utf-8')
        records.append({'command':command,'exit_code':None,'timeout':True,'log':label+'.log'})
        print(output,flush=True)
        return False
    output = result.stdout + result.stderr
    (work/(label+'.log')).write_text(output,encoding='utf-8')
    record = {'command':command, 'exit_code':result.returncode,'engine_errors':'ERROR:' in output,'log':label+'.log'}
    records.append(record)
    print(output,flush=True)
    return result.returncode == 0 and 'ERROR:' not in output
ok = run(['--editor','--import','--quit'],'import')
ok = run(['--script','res://tests/test_http_protobuf_client.gd'],'codec') and ok
spec = importlib.util.spec_from_file_location('http_fixture',repo/'client/tests/http_protobuf_fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
server = ThreadingHTTPServer(('127.0.0.1',38971),fixture.Handler)
thread = threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
try:
    ok = run(['--script','res://tests/test_http_protobuf_transport.gd'],'transport') and ok
finally:
    server.shutdown(); server.server_close(); thread.join(timeout=5)
(work/'results.json').write_text(json.dumps({'ok':ok,'runs':records},ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
