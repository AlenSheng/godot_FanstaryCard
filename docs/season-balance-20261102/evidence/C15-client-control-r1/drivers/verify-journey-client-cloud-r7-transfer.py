from pathlib import Path
import base64,hashlib,json,shlex,subprocess
stage=Path(__file__).parent/'journey-client-cloud-r7';target=stage/'complete-transfer-verification.original.json';assert not target.exists()
expected=json.loads((stage/'manifest.json').read_text('utf-8'))
source='''from pathlib import Path
import hashlib,json,time
p=Path('/home/ubuntu/season-balance-20261102-journey-client-r7-transfer/input.tar.gz.part');samples=[]
for _ in range(2):samples.append({'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});time.sleep(1)
print(json.dumps({'samples':samples,'native_started':False}))
'''
command='python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=35)
record={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr};assert r.returncode==0
data=json.loads(r.stdout);record['complete_and_stable']=all(s['bytes']==expected['payload_bytes'] and s['sha256']==expected['payload_sha256'] for s in data['samples']);assert record['complete_and_stable']
target.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(json.dumps({'complete_and_stable':True,'bytes':expected['payload_bytes']}))
