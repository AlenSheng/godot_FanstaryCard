from pathlib import Path
import subprocess,base64,shlex,json
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104';fingerprint=base64.b64encode((o/'start-runtime.py').read_text(encoding='utf-8').encode()).decode()
remote='''from pathlib import Path
import subprocess,json,sys,os,hashlib
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r104');label='season-balance-20261102-a03-runtime-r104'
needle=('import base64;exec(base64.b64decode('+repr(sys.argv[1])+'))').encode();processes=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/'cmdline').read_bytes().split(bytes([0]))
  if needle in args:processes.append({'pid':int(p.name),'status':(p/'status').read_text().splitlines()[:3]})
 except (OSError,ProcessLookupError):pass
rows=subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task='+label,'--format','{{json .}}'],text=True).splitlines()
value=dict(root_exists=root.exists(),root_files=sorted(p.name for p in root.iterdir()) if root.exists() else [],containers=[json.loads(x) for x in rows],strict_original_transport_processes=processes)
if (root/'runtime-handle.json').exists():value['handle']=json.loads((root/'runtime-handle.json').read_text())
print(json.dumps(value))
'''
cmd='sudo -n python3 -c '+shlex.quote(remote)+' '+shlex.quote(fingerprint)
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=40)
p=o/'recovery-observation-04.original.log';assert not p.exists();p.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
v=json.loads(r.stdout);(o/'strict-recovery-04.original.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
if 'handle' in v:(o/'runtime-handle.json').write_text(json.dumps(v['handle'],indent=2)+'\n',encoding='utf-8')
