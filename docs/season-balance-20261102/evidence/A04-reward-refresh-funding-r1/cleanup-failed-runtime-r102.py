from pathlib import Path
import ast,json,hashlib,subprocess,base64,shlex
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r102'
a=json.loads((o/'collection-audit.json').read_text(encoding='utf-8'))
assert a['state']=='exited' and a['exit_code']==1 and a['counts']['failed']=='2'
assert hashlib.sha256((o/'public-evidence.tar.gz').read_bytes()).hexdigest()==a['public_archive_sha256']
for n,h in a['files'].items():assert hashlib.sha256((o/'public'/n).read_bytes()).hexdigest()==h
module=ast.parse((b/'collect-refresh-funding-runtime-r102.py').read_text(encoding='utf-8'))
cleanup=next(ast.literal_eval(x.value) for x in module.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cleanup' for t in x.targets))
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(cleanup.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=45)
(o/'cleanup-failed-batch.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
