from pathlib import Path
import subprocess,base64,shlex,json,hashlib
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104';remote=(o/'start-runtime.py').read_bytes();fingerprint=base64.b64encode(remote).decode()
code='''from pathlib import Path
import json,subprocess,sys,shutil
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r104');label='season-balance-20261102-a03-runtime-r104';fingerprint=sys.argv[1]
rows=json.loads(subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task='+label,'--format','json'],text=True).replace('}\\n{','},\\n{').join(['[',']'])) if False else subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task='+label,'--format','{{json .}}'],text=True).splitlines()
processes=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  cmd=(p/'cmdline').read_bytes()
  if ('import base64;exec(base64.b64decode('+repr(fingerprint)+'))').encode() in cmd.split(b'\0'):processes.append(dict(pid=int(p.name),status=(p/'status').read_text().splitlines()[:3],argv_sha256=__import__('hashlib').sha256(cmd).hexdigest()))
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
result=dict(root_exists=root.exists(),root_files=sorted(p.name for p in root.iterdir()) if root.exists() else [],containers=[json.loads(x) for x in rows],original_transport_processes=processes,free_disk=shutil.disk_usage('/home/ubuntu').free)
if (root/'runtime-handle.json').exists():result['handle']=json.loads((root/'runtime-handle.json').read_text())
print(json.dumps(result))
'''
command='sudo -n python3 -c '+shlex.quote(code)+' '+shlex.quote(fingerprint)
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',command],capture_output=True,text=True,timeout=40)
p=o/'recovery-observation-02.original.log';assert not p.exists();p.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
info=json.loads(r.stdout);(o/'strict-recovery.original.json').write_text(json.dumps(dict(transport_timeout_seconds=120,original_start_log_not_written_due_to_timeout=True,remote_outcome=info,duplicate_launch_not_attempted=True),indent=2)+'\n',encoding='utf-8')
if 'handle' in info:
 (o/'runtime-handle.json').write_text(json.dumps(info['handle'],indent=2)+'\n',encoding='utf-8')
