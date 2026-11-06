import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import subprocess,json,base64,shlex,struct,hashlib
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r106';manifest=(o/'manifest.json').read_bytes();delta=json.loads((o/'delta-manifest.json').read_text(encoding='utf-8'));raw=(o/'delta.tar.gz').read_bytes();assert hashlib.sha256(raw).hexdigest()==delta['delta_sha256'];assert not (o/'runtime-handle.json').exists()
control=json.dumps(dict(target_manifest_base64=base64.b64encode(manifest).decode(),delta=delta)).encode();remote=(o/'start-delta-runtime.py').read_text(encoding='utf-8');cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(remote.encode()).decode())+'))')
try:
 r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','ubuntu@43.172.70.182',cmd],input=struct.pack('!I',len(control))+control+raw,capture_output=True,timeout=300)
 text=(r.stdout+r.stderr).decode('utf-8',errors='replace');(o/'start-delta.original.log').write_text(text,encoding='utf-8');print(text);assert r.returncode==0
 h=json.loads(r.stdout);(o/'runtime-handle.json').write_text(json.dumps(h,indent=2)+'\n',encoding='utf-8')
except subprocess.TimeoutExpired as e:
 (o/'start-delta-timeout.original.json').write_text(json.dumps(dict(timeout_seconds=300,follow_same_stage=True,stdout=(e.stdout or b'').decode(errors='replace'),stderr=(e.stderr or b'').decode(errors='replace')),indent=2)+'\n',encoding='utf-8');raise SystemExit('Delta observation timed out; follow same stage, do not duplicate.')
