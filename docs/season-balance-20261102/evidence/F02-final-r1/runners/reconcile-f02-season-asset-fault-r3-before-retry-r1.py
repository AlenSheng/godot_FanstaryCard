from pathlib import Path
import subprocess,base64,shlex,json,time
base=Path(__file__).parent;out=base/'f02-season-asset-fault-r3-pre-retry-r1';assert not out.exists();out.mkdir()
script="""from pathlib import Path
import subprocess,json,shutil
pg='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
image='sha256:b34b01ff381aa920264e3920d7a7a49e6c1056091999dfc6268107d07029b9f4'
m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());disk=shutil.disk_usage('/home/ubuntu')
data=json.loads(subprocess.check_output(['docker','inspect',pg]))[0]
runtime=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]
active=subprocess.check_output(['docker','ps','--filter','label=com.fantasycard.task','--format','{{.ID}} {{.Names}}']).decode().splitlines()
print(json.dumps(dict(read_only=True,available_RAM=int(m['MemAvailable'].split()[0])*1024,free_disk=disk.free,disk_fraction=disk.free/disk.total,owned_PG_running=data['State']['Running'],owned_PG_label=data['Config']['Labels'].get('com.fantasycard.task'),image_id=runtime['Id'],active_tagged_containers=active,new_root_exists=Path('/home/ubuntu/season-balance-20261106-f02-season-asset-fault-r3').exists())))
"""
remote='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(script.encode()).decode())+'))')
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182',remote]
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=__import__('os').getpid(),read_only=True,started_at=time.time()))+'\n')
stdout,stderr=child.communicate();(out/'stdout.original.log').write_bytes(stdout);(out/'stderr.original.log').write_bytes(stderr)
(out/'terminal.original.json').write_text(json.dumps(dict(pid=child.pid,exit=child.returncode))+'\n')
assert child.returncode==0,stderr.decode(errors='replace')
result=json.loads(stdout);(out/'result.original.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
