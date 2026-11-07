from pathlib import Path
import subprocess,base64,shlex,json,hashlib,sys,re
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r107';index=sys.argv[1];assert re.fullmatch(r'r[1-9][0-9]*',index);out=o/('file-prefix-'+index+'.original.json');assert not out.exists();local=(o/'transport-stream-file-r1.bin').read_bytes()
code=r"""from pathlib import Path
import json,hashlib,subprocess
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107-upload');p=root/'stream-r1.bin.part';assert root.resolve().parent==Path('/home/ubuntu') and not root.is_symlink()
result={'exists':p.exists(),'runtime_root_exists':Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107').exists(),'runtime_containers':subprocess.check_output(['sudo','-n','docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r107','--format','{{.ID}}'],timeout=5).decode().strip()}
if p.exists():
 assert not p.is_symlink() and p.resolve().parent==root.resolve();raw=p.read_bytes();result.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
else:result.update(bytes=0,sha256=hashlib.sha256(b'').hexdigest())
writers=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  if (proc/'comm').read_text().strip() not in ['sftp-server','sshd','sshd-session']:continue
  for fd in (proc/'fd').iterdir():
   if str(fd.readlink())!=str(p):continue
   info={k:v.strip() for k,v in (line.split(':',1) for line in (proc/'fdinfo'/fd.name).read_text().splitlines())}
   if int(info['flags'],8)&3==0:continue
   raw=(proc/'stat').read_text();tail=raw[raw.rindex(')')+2:].split()
   writers.append(dict(pid=int(proc.name),state=tail[0],start_ticks=int(tail[19]),fd=fd.name,position=int(info['pos']),argv_sha256=hashlib.sha256((proc/'cmdline').read_bytes()).hexdigest()))
 except (OSError,PermissionError,ValueError):pass
result['open_transfer_writers']=writers
print(json.dumps(result))
"""
cmd='sudo -n python3 -c '+shlex.quote(code)
r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=40)
log=o/('file-prefix-'+index+'.transport.original.log');log.write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stderr;proof=json.loads(r.stdout);assert 0<=proof['bytes']<=len(local)
proof['local_prefix_identical']=hashlib.sha256(local[:proof['bytes']]).hexdigest()==proof['sha256'];proof['complete']=proof['bytes']==len(local) and proof['local_prefix_identical'];out.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof));assert proof['local_prefix_identical']
