from pathlib import Path
import subprocess,base64,json,hashlib,shlex
b=Path(__file__).parent
v=json.loads((b/'v15-local-verification.json').read_text(encoding='utf-8'));assert v['verified_members']==937 and hashlib.sha256(Path(v['local_snapshot']).read_bytes()).hexdigest()==v['sha256']
script=(b/'archive-market-expanded-v15.py').read_text(encoding='utf-8')
code="from pathlib import Path\nimport json,sys\np=Path('/home/ubuntu/season-balance-20261102-a03-storage-r86/ended-expanded-inputs-v15.json')\n"
code+="proof=json.loads(p.read_text());assert proof['archive_sha256']=="+repr(v['sha256'])+"\n"
code+="for mode,field in [('retire','expanded_retired'),('offload','snapshot_offloaded')]:\n if json.loads(p.read_text())[field]:continue\n sys.argv=['resume',mode,"+repr(v['sha256'])+"];exec("+repr(script)+")\n"
code+="print('FINAL_PROOF='+p.read_text())\n"
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=95)
(b/'v15-resume-r2.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stderr
raw=r.stdout.split('FINAL_PROOF=',1)[1];proof=json.loads(raw);assert proof['expanded_retired'] and proof['snapshot_offloaded'];(b/'ended-expanded-inputs-v15.json').write_text(raw,encoding='utf-8');print(json.dumps({k:v for k,v in proof.items() if k!='files'}))
