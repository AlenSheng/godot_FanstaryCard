from pathlib import Path
import subprocess,json,base64,shlex,hashlib,tarfile
base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');script=(base/'archive-market-expanded-v13.py').read_text(encoding='utf-8')
archive=base/'cloud-build-archives/ended-expanded-inputs-v13.tar.gz';proof=json.loads((base/'ended-expanded-inputs-v13.before-retirement.json').read_text(encoding='utf-8'))
(base/'v13-download.timeout.json').write_text(json.dumps({'observation_timeout_seconds':240,'partial_bytes':archive.stat().st_size,'cloud_expanded_retired':False,'source_archive_unchanged':True,'next':'sftp reget same immutable archive then full SHA and member SHA'},indent=2)+'\n')
key=r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem';host='ubuntu@43.172.70.182';root='/home/ubuntu/season-balance-20261102-a03-storage-r82'
ssh=['ssh','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']
batch=base/'v13-resume.sftp';batch.write_text('reget "'+root+'/ended-expanded-inputs-v13.tar.gz" "'+archive.as_posix()+'"\nquit\n')
print('Resuming same v13 snapshot from byte',archive.stat().st_size,flush=True)
r=subprocess.run(['sftp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-b',str(batch),host],capture_output=True,text=True,timeout=600)
(base/'v13-resume.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr
assert hashlib.sha256(archive.read_bytes()).hexdigest()==proof['archive_sha256']
r=subprocess.run(ssh+[host,'cat '+root+'/ended-expanded-inputs-v13.json'],capture_output=True,text=True,timeout=30);assert r.returncode==0;full=json.loads(r.stdout)
expected=full['files'];seen=set()
with tarfile.open(archive,'r|gz') as tf:
 for m in tf:
  assert m.isfile() or m.isdir()
  if m.isfile():
   assert m.name in expected and m.name not in seen
   assert hashlib.sha256(tf.extractfile(m).read()).hexdigest()==expected[m.name];seen.add(m.name)
assert seen==set(expected)
(base/'v13-local-verification.json').write_text(json.dumps({'sha256':proof['archive_sha256'],'verified_members':len(seen),'bytes':archive.stat().st_size,'local_snapshot':str(archive)},indent=2)+'\n')
print('Full snapshot and all members verified',len(seen),flush=True)
def remote(mode):
 code='import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))'
 r=subprocess.run(ssh+[host,'sudo -n python3 -c '+shlex.quote(code)+' '+mode+' '+proof['archive_sha256']],capture_output=True,text=True,timeout=120)
 (base/('v13-'+mode+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr;print(r.stdout,flush=True)
remote('retire');remote('offload')
r=subprocess.run(ssh+[host,'cat '+root+'/ended-expanded-inputs-v13.json'],capture_output=True,text=True,timeout=30);assert r.returncode==0
(base/'ended-expanded-inputs-v13.json').write_text(r.stdout,encoding='utf-8')
