from pathlib import Path
import base64,hashlib,json,shlex,subprocess,time
base=Path(__file__).parent;stage=base/'journey-client-cloud-r7';proof=stage/'transfer-setup.original.json';assert not proof.exists()
p=stage/'remote.original.py';old=hashlib.sha256((base/'journey-client-cloud-r6/input.tar.gz').read_bytes()).hexdigest();new=hashlib.sha256((stage/'input.tar.gz').read_bytes()).hexdigest();p.write_text(p.read_text('utf-8').replace(old,new),encoding='utf-8')
source='''from pathlib import Path
import json,shutil,time
root=Path('/home/ubuntu/season-balance-20261102-journey-client-r7-transfer');assert not root.exists()
samples=[]
for _ in range(3):
 m={s.split(':')[0]:int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if len(s.split())>1 and s.split()[1].isdigit()};d=shutil.disk_usage('/home/ubuntu');samples.append({'ram':m['MemAvailable'],'disk':d.free,'ratio':d.free/d.total});time.sleep(1)
assert all(s['ram']>=1800*1024**2 and s['disk']>=3*1024**3+16*1024**2 and s['ratio']>=.05 for s in samples)
root.mkdir();print(json.dumps({'samples':samples,'transfer_directory':str(root),'native_started':False}))
'''
command='python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=35)
proof.write_text(json.dumps({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n',encoding='utf-8');print(proof.read_text('utf-8'));assert r.returncode==0
