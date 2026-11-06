import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import subprocess,base64,shlex,sys
base=Path(__file__).parent;stage=base/'runtime-r106';index=sys.argv[1];path=stage/('observation-'+index+'.original.log');assert not path.exists()
code="""from pathlib import Path
import json,subprocess,shutil,hashlib
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106');handle=json.loads((root/'runtime-handle.json').read_text());row=json.loads(subprocess.check_output(['docker','inspect',handle['container_id']]))[0]
assert row['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-runtime-r106'
logs=subprocess.check_output(['docker','logs',handle['container_id']],stderr=subprocess.STDOUT);password=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())['password'].encode();assert password not in logs
m={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if len(l.split())>1 and l.split()[1].isdigit()};d=shutil.disk_usage(root)
p={'state':row['State']['Status'],'exit_code':row['State']['ExitCode'],'oom_killed':row['State']['OOMKilled'],'available_ram':m['MemAvailable'],'free_disk':d.free,'free_ratio':d.free/d.total,'log_tail':logs.decode('utf-8',errors='replace')[-5500:]}
if p['state']=='exited':
 manifest=json.loads((root/'manifest.json').read_text());p['binary_payload_unchanged']=all(hashlib.sha256((root/'input'/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items());assert p['binary_payload_unchanged']
print(json.dumps(p))
"""
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=40);path.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
