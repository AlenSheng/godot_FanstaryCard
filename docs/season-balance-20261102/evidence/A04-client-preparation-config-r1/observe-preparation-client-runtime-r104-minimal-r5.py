from pathlib import Path
import subprocess,json,base64,shlex
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104'
code='''from pathlib import Path
import subprocess,json
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r104');print(json.dumps({'root_exists':root.exists(),'root_files':[p.name for p in root.iterdir()] if root.exists() else []}),flush=True)
if (root/'runtime-handle.json').exists():print(json.dumps({'handle':json.loads((root/'runtime-handle.json').read_text())}),flush=True)
try:
 r=subprocess.run(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r104','--format','{{json .}}'],capture_output=True,text=True,timeout=8)
 print(json.dumps({'docker_exit':r.returncode,'docker_rows':r.stdout,'docker_error':r.stderr}),flush=True)
except subprocess.TimeoutExpired:print(json.dumps({'docker_observation_timeout_seconds':8}),flush=True)
'''
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=25)
p=o/'minimal-runtime-observation-05.original.log';assert not p.exists();p.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
for line in r.stdout.splitlines():
 d=json.loads(line)
 if 'handle' in d:(o/'runtime-handle.json').write_text(json.dumps(d['handle'],indent=2)+'\n',encoding='utf-8')
