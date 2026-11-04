from pathlib import Path
import subprocess,base64,json,hashlib,tarfile,shlex
base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');script=(base/'archive-market-expanded-v9.py').read_text(encoding='utf-8').replace('storage-r76','storage-r86').replace('v9','v15')
path=base/'archive-market-expanded-v15.py';assert not path.exists();path.write_text(script,encoding='utf-8')
ssh=['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3'];host='ubuntu@43.172.70.182'
def remote(mode,*args):
 code='import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))'
 r=subprocess.run(ssh+[host,'sudo -n python3 -c '+shlex.quote(code)+' '+shlex.join([mode,*args])],capture_output=True,text=True,timeout=120)
 (base/('v15-'+mode+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr;return json.loads(r.stdout)
proof=remote('prepare');(base/'ended-expanded-inputs-v15.before-retirement.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof),flush=True)
root='/home/ubuntu/season-balance-20261102-a03-storage-r86';archive=base/'cloud-build-archives/ended-expanded-inputs-v15.tar.gz'
assert not archive.exists()
cmd=['scp','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',host+':'+root+'/ended-expanded-inputs-v15.tar.gz',str(archive)]
r=subprocess.run(cmd,capture_output=True,text=True,timeout=240);(base/'v15-download.original.log').write_text(r.stdout+r.stderr);assert r.returncode==0
assert hashlib.sha256(archive.read_bytes()).hexdigest()==proof['archive_sha256']
r=subprocess.run(ssh+[host,'cat '+root+'/ended-expanded-inputs-v15.json'],capture_output=True,text=True,timeout=30);assert r.returncode==0;full=json.loads(r.stdout)
expected=full['files'];seen=set()
with tarfile.open(archive,'r|gz') as tf:
 for m in tf:
  assert m.isfile() or m.isdir()
  if m.isfile():
   assert m.name in expected and m.name not in seen
   assert hashlib.sha256(tf.extractfile(m).read()).hexdigest()==expected[m.name];seen.add(m.name)
assert seen==set(expected)
(base/'v15-local-verification.json').write_text(json.dumps({'sha256':proof['archive_sha256'],'verified_members':len(seen),'bytes':archive.stat().st_size,'local_snapshot':str(archive)},indent=2)+'\n')
print('Local full archive and all members verified',len(seen),flush=True)
print(remote('retire',proof['archive_sha256']),flush=True);print(remote('offload',proof['archive_sha256']),flush=True)
r=subprocess.run(ssh+[host,'cat '+root+'/ended-expanded-inputs-v15.json'],capture_output=True,text=True,timeout=30);assert r.returncode==0
(base/'ended-expanded-inputs-v15.json').write_text(r.stdout,encoding='utf-8')
