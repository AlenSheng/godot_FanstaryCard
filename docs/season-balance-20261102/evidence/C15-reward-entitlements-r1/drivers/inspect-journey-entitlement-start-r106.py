from pathlib import Path
import subprocess,base64,shlex,json,sys
sys.stdout.reconfigure(encoding='utf-8')
b=Path(__file__).parent;index=sys.argv[1];out=b/'runtime-r106'/('start-inspection-'+index+'.original.log');assert not out.exists()
marker=base64.b64encode((b/'runtime-r106/start-delta-runtime.py').read_text('utf-8').encode()).decode()
code="""from pathlib import Path
import json,subprocess,shutil
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106');label='season-balance-20261102-a03-runtime-r106'
rows=subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task='+label,'--format','{{.ID}} {{.Status}}']).decode().strip()
expected=MARKER;workers=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  args=(proc/'cmdline').read_bytes().split(b'\\0')
  if len(args)>2 and args[1]==b'-c' and expected.encode() in args[2] and args[0].split(b'/')[-1] in [b'python',b'python3']:
   workers.append(int(proc.name))
 except (OSError,PermissionError):pass
data=dict(root_exists=root.exists(),runtime_containers=rows,matching_start_workers=workers)
if (root/'runtime-handle.json').exists():data['handle']=json.loads((root/'runtime-handle.json').read_text())
d=shutil.disk_usage('/home/ubuntu');data.update(free_disk=d.free,free_ratio=d.free/d.total)
print(json.dumps(data))
""".replace('MARKER',repr(marker))
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=40)
out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
