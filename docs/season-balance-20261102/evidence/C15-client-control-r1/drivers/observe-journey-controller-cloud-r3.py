from pathlib import Path
import base64,json,shlex,subprocess,sys
base=Path(__file__).parent;stage=base/'journey-controller-cloud-r3';name=sys.argv[1];target=stage/('observation-'+name+'.original.json');assert not target.exists()
source='''from pathlib import Path
import json,subprocess
root=Path('/home/ubuntu/season-balance-20261102-journey-controller-r3');out=root/'output';data={'root_exists':root.exists(),'output_exists':out.exists(),'files':sorted(p.name for p in out.iterdir()) if out.exists() else []}
for name in ['handle.json','terminal.original.json','cleanup.original.json','case-results.json','engine.json']:
 p=out/name
 if p.exists():data[name]=json.loads(p.read_text())
if 'handle.json' in data:
 r=subprocess.run(['docker','inspect',data['handle.json']['container_id']],capture_output=True,text=True)
 if r.returncode==0:data['live_state']=json.loads(r.stdout)[0]['State']
print(json.dumps(data))
'''
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=35)
target.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(target.read_text('utf-8'))
