from pathlib import Path
import subprocess,base64,json,hashlib,shlex
b=Path(__file__).parent
ssh=['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3'];host='ubuntu@43.172.70.182'
verification=json.loads((b/'v15-local-verification.json').read_text(encoding='utf-8'));assert verification['verified_members']==937 and hashlib.sha256(Path(verification['local_snapshot']).read_bytes()).hexdigest()==verification['sha256']
root='/home/ubuntu/season-balance-20261102-a03-storage-r86'
r=subprocess.run(ssh+[host,'cat '+root+'/ended-expanded-inputs-v15.json'],capture_output=True,text=True,timeout=35);(b/'v15-resume-state.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
proof=json.loads(r.stdout);assert proof['archive_sha256']==verification['sha256'];script=(b/'archive-market-expanded-v15.py').read_text(encoding='utf-8')
for mode,field in [('retire','expanded_retired'),('offload','snapshot_offloaded')]:
 if proof[field]:continue
 code='import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))'
 r=subprocess.run(ssh+[host,'sudo -n python3 -c '+shlex.quote(code)+' '+shlex.join([mode,verification['sha256']])],capture_output=True,text=True,timeout=90);(b/('v15-resume-'+mode+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr,flush=True);assert r.returncode==0
r=subprocess.run(ssh+[host,'cat '+root+'/ended-expanded-inputs-v15.json'],capture_output=True,text=True,timeout=35);assert r.returncode==0;(b/'ended-expanded-inputs-v15.json').write_text(r.stdout,encoding='utf-8')
