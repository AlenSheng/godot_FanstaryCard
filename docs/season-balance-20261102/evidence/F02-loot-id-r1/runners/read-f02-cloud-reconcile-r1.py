from pathlib import Path
import subprocess,base64,shlex,json,os,time
base=Path(__file__).parent;out=base/'f02-cloud-reconcile-r1';assert not out.exists();out.mkdir()
script="""from pathlib import Path
import subprocess,json,hashlib,shutil
root=Path('/home/ubuntu/season-balance-20261106-d03-maintenance-r3');p=root/'public/input-cache-cleanup.original.json';active=[]
for q in Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=q.read_bytes().split(bytes([0]));active.extend([int(q.parent.name)] if any(hashlib.sha256(a).hexdigest()=='c65e395088c759208bc26c3cce1ce5b44fde25cbbf9047c8bf8931a5802d19c0' for a in args) else [])
 except (OSError,PermissionError):pass
m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu')
r=dict(input_exists=(root/'input').exists(),cleanup_record=json.loads(p.read_text()) if p.exists() else None,exact_old_cleanup_pids=active,free_RAM=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total)
print(json.dumps(r))
"""
remote='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))')
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182',remote]
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),started_at=time.time(),read_only=True))+'\n')
stdout,stderr=child.communicate();(out/'stdout.original.log').write_bytes(stdout);(out/'stderr.original.log').write_bytes(stderr)
(out/'terminal.original.json').write_text(json.dumps(dict(pid=child.pid,exit=child.returncode))+'\n')
if child.returncode==0:
 r=json.loads(stdout);(out/'result.original.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
 if not r['input_exists'] and r['cleanup_record'] and not r['exact_old_cleanup_pids']:
  proof=dict(own_runtime_caches=[r['cleanup_record']],read_only_reconciliation=True,resources=dict(free_RAM=r['free_RAM'],free_disk=r['free_disk'],disk_fraction=r['disk_fraction']))
  p=base/'d03-maintenance-owned-input-cache-cleanup-r3.original.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n')
else:print(json.dumps(dict(exit=child.returncode,error=stderr.decode(errors='replace'))))
