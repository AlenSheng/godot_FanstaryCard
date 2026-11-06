from pathlib import Path
import hashlib,json,base64,shlex,subprocess,time,os
base=Path(__file__).parent;out=base/'d04-currency-r2-reconcile-r1';assert not out.exists();out.mkdir()
src=(base/'start-d04-currency-cloud-r2.py').read_bytes();launch='import base64;exec(base64.b64decode('+repr(base64.b64encode(src).decode())+'))';digest=hashlib.sha256(launch.encode()).hexdigest()
script="""from pathlib import Path
import subprocess,json,hashlib,time,shutil
root=Path('/home/ubuntu/season-balance-20261106-d04-currency-r2');public=root/'public';workers=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  if any(hashlib.sha256(a).hexdigest()==DIGEST for a in p.read_bytes().split(bytes([0]))):workers.append(int(p.parent.name))
 except (OSError,PermissionError):pass
read={}
for name in ['result.json','cleanup.original.json','input-cache-cleanup.original.json','runtime-handle.original.json']:
 p=public/name
 if p.exists():read[name]=json.loads(p.read_text())
archive=root/'public-evidence.tar.gz';disk=shutil.disk_usage('/home/ubuntu')
m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())
print(json.dumps(dict(at=time.time(),read_only=True,root_exists=root.exists(),worker_pids=workers,public_files=[p.name for p in public.iterdir()] if public.exists() else [],records=read,archive_exists=archive.exists(),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest() if archive.exists() else None,active_tagged_containers=subprocess.check_output(['docker','ps','--filter','label=com.fantasycard.task','--format','{{.ID}} {{.Names}}']).decode().splitlines(),available_RAM=int(m['MemAvailable'].split()[0])*1024,free_disk=disk.free,disk_fraction=disk.free/disk.total)))
""".replace('DIGEST',repr(digest))
remote='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))')
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182',remote]
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),read_only=True,started_at=time.time()))+'\n')
stdout,stderr=child.communicate();(out/'stdout.original.log').write_bytes(stdout);(out/'stderr.original.log').write_bytes(stderr);(out/'terminal.original.json').write_text(json.dumps(dict(pid=child.pid,exit=child.returncode))+'\n')
if child.returncode==0:
 r=json.loads(stdout);(out/'result.original.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
else:print(json.dumps(dict(exit=child.returncode,error=stderr.decode(errors='replace'))))
