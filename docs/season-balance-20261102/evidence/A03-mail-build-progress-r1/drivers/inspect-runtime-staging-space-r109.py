from pathlib import Path
import base64,json,shlex,subprocess
base=Path(__file__).parent;out=base/'runtime-r109-space-readonly-r1.original.json';assert not out.exists()
source='''from pathlib import Path
import json,shutil
home=Path('/home/ubuntu');d=shutil.disk_usage(home);roots={}
for number in range(104,109):
 for suffix in ['', '-upload']:
  root=home/('season-balance-20261102-a03-runtime-r'+str(number)+suffix)
  if root.is_dir():
   files=[]
   for p in root.iterdir():
    if p.is_file() and not any(s in p.name for s in ['private','secret','env']):files.append({'name':p.name,'bytes':p.stat().st_size,'links':p.stat().st_nlink})
   roots[root.name]={'files':files,'expanded_input_exists':(root/'input').is_dir()}
print(json.dumps({'disk_free':d.free,'disk_ratio':d.free/d.total,'roots':roots}))
'''
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=35)
out.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');assert r.returncode==0;print(r.stdout)
