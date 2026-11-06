from pathlib import Path
import subprocess,base64,shlex,json,sys
sys.stdout.reconfigure(encoding='utf-8')
b=Path(__file__).parent;output=b/'journey-entitlements-cloud-preflight-r106.original.json';assert not output.exists()
code="""from pathlib import Path
import json,subprocess,shutil
m={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if len(l.split())>1 and l.split()[1].isdigit()};d=shutil.disk_usage('/home/ubuntu')
roots={}
for n in ['r104','r105','r106']:
 p=Path('/home/ubuntu/season-balance-20261102-a03-runtime-'+n);roots[n]={'exists':p.exists(),'input_exists':(p/'input').exists(),'handle_exists':(p/'runtime-handle.json').exists()}
labels={}
for n in ['r105','r106']:
 label='com.fantasycard.task=season-balance-20261102-a03-runtime-'+n
 labels[n]=subprocess.check_output(['docker','ps','-a','--filter','label='+label,'--format','{{.ID}} {{.Status}}']).decode().strip()
pg=json.loads(subprocess.check_output(['docker','inspect','803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a']))[0]
assert pg['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
print(json.dumps(dict(available_ram=m['MemAvailable'],free_disk=d.free,total_disk=d.total,free_ratio=d.free/d.total,owned_roots=roots,owned_runtime_containers=labels,isolated_pg_state=pg['State']['Status'],isolated_pg_oom=pg['State']['OOMKilled'])))
"""
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=40)
output.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
