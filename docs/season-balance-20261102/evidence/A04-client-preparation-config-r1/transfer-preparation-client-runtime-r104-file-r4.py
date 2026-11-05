from pathlib import Path
import subprocess,json,hashlib,struct,shlex,time
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');o=b/'runtime-r104';mf=(o/'manifest.json').read_bytes();m=json.loads(mf);data=struct.pack('!I',len(mf))+mf+(o/'payload.tar.gz').read_bytes();stream=o/'transport-stream-r3.bin';assert not stream.exists() or stream.read_bytes()==data
if not stream.exists():stream.write_bytes(data);digest=hashlib.sha256(data).hexdigest()
remote_root='/home/ubuntu/season-balance-20261102-a03-runtime-r104-upload'
setup='''from pathlib import Path
import sys,json,shutil,time,subprocess
root=Path(sys.argv[1]);expanded=int(sys.argv[2]);compressed=int(sys.argv[3]);assert not root.exists();assert not Path('/home/ubuntu/season-balance-20261102-a03-runtime-r104').exists()
assert not subprocess.check_output(['sudo','-n','docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r104','--format','{{.ID}}']).strip()
samples=[]
for _ in range(3):
 m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu');v=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,free_fraction=d.free/d.total);samples.append(v)
 assert v['available_ram']>=1800*1024**2 and d.free>=3*1024**3+expanded+compressed+64*1024**2+2*1024**2 and d.free/d.total>=.05
 time.sleep(1)
root.mkdir(mode=0o700);proof=dict(samples=samples,expanded_bytes=expanded,compressed_stream_bytes=compressed,extra_compressed_copy_included_in_guard=True,minimum_disk_bytes=3*1024**3,minimum_free_fraction=.05,only_owned_upload_directory_created=True)
(root/'admission.original.json').write_text(json.dumps(proof)+'\\n');print(json.dumps(proof))
'''
ssh=['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','ubuntu@43.172.70.182']
cmd='python3 -c '+shlex.quote(setup)+' '+shlex.quote(remote_root)+' '+str(m['expanded_bytes'])+' '+str(len(data))
r=subprocess.run(ssh+[cmd],capture_output=True,text=True,timeout=30);(o/'file-transfer-admission-r4.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr,flush=True);assert r.returncode==0
cmd=['scp','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',str(stream),'ubuntu@43.172.70.182:'+remote_root+'/stream-r4.bin.part'];t=time.monotonic()
try:
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=240);v=dict(exit=r.returncode,seconds=time.monotonic()-t,stdout=r.stdout,stderr=r.stderr,expected_bytes=len(data),sha256=digest)
except subprocess.TimeoutExpired as e:
 v=dict(transport_timeout_seconds=240,seconds=time.monotonic()-t,expected_bytes=len(data),sha256=digest,remote_partial_file_must_be_observed_before_any_retry=True)
(o/'file-transfer-r4.original.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8');print(json.dumps(v),flush=True)
assert v.get('exit')==0
