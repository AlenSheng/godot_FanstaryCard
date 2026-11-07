from pathlib import Path
import subprocess,base64,shlex,json
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104';fingerprint=base64.b64encode((o/'start-runtime.py').read_text(encoding='utf-8').encode()).decode()
code='''import subprocess,json,sys
needle=('import base64;exec(base64.b64decode('+repr(sys.argv[1])+'))').encode();rows=subprocess.check_output(['ps','-C','python3','-C','sudo','-o','pid=,ppid=,comm='],text=True).splitlines();matches=[];unreadable=[]
for line in rows:
 pid=int(line.split()[0])
 try:
  r=subprocess.run(['cat','/proc/'+str(pid)+'/cmdline'],capture_output=True,timeout=1)
  if needle in r.stdout.split(bytes([0])):matches.append(pid)
 except subprocess.TimeoutExpired:unreadable.append(pid)
print(json.dumps({'strict_original_pids':matches,'unreadable_candidate_pids':unreadable,'candidates':len(rows)}))
'''
cmd='sudo -n python3 -c '+shlex.quote(code)+' '+shlex.quote(fingerprint)
r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,timeout=30)
p=o/'bounded-process-observation-06.original.log';assert not p.exists();p.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
