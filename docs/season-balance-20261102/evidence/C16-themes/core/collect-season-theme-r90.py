from pathlib import Path
import subprocess,json,base64,shlex,tarfile,hashlib,os
base=Path(__file__).parent;stage=base/'storage-r90';host='ubuntu@43.172.70.182';root='/home/ubuntu/season-balance-20261102-a03-storage-r90';key=r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem'
ssh=['ssh','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']
def remote(code,label):
 command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
 r=subprocess.run(ssh+[host,command],capture_output=True,text=True,timeout=90);(stage/(label+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr;return r.stdout
assert not (stage/'public-evidence.tar.gz').exists()
raw=remote("import runpy,sys;sys.argv=['collect','storage-r90'];runpy.run_path('"+root+"/collect-config-evidence.py',run_name='__main__')",'collect')
audit=json.loads(raw);(stage/'collection-audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps({'state':audit['state'],'exit_code':audit['exit_code'],'counters':audit['counters']}),flush=True)
r=subprocess.run(['scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15',host+':'+root+'/public-evidence.tar.gz',str(stage/'public-evidence.tar.gz')],capture_output=True,text=True,timeout=120);(stage/'download.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
assert hashlib.sha256((stage/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
dest=stage/'public';assert not dest.exists();dest.mkdir()
with tarfile.open(stage/'public-evidence.tar.gz','r:gz') as tf:
 for member in tf:
  assert member.isfile() and member.name in audit['files'] or member.name=='audit.json'
  data=tf.extractfile(member).read()
  if member.name in audit['files']:assert hashlib.sha256(data).hexdigest()==audit['files'][member.name]
  p=(dest/member.name).resolve();assert p.is_relative_to(dest.resolve());p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
assert audit['exit_code']==0 and not audit['oom_killed']
assert all(c['failed']=='0' and c['notExecuted']=='0' for c in audit['counters'].values())
print(remote("import runpy,sys;sys.argv=['cleanup','storage-r90'];runpy.run_path('"+root+"/cleanup-storage-sdk.py',run_name='__main__')",'cleanup'),flush=True)
print('Public archive and all member hashes verified; exact exited r80 SDK and its private env removed',flush=True)
