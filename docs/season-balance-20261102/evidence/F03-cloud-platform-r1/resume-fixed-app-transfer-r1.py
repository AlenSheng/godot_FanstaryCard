from pathlib import Path
import ctypes, datetime, hashlib, json, os, subprocess, time

b=Path(__file__).parent;out=b/'f03-fixed-app-transfer-resume-r1';assert not out.exists();out.mkdir()
prior=json.loads((b/'f03-fixed-app-reconcile-r1/result.original.json').read_bytes());assert prior['exit']==0 and prior['prefix_exact']
observation=prior['observation'];assert not observation['root_exists'] and not observation['launch_exists']
stream=b/'f03-fixed-app-input-r1/stream.bin';raw=stream.read_bytes();assert hashlib.sha256(raw[:observation['bytes']]).hexdigest()==observation['sha256']
assert hashlib.sha256(raw).hexdigest()==observation['ownership']['sha256']
batch=out/'reput.original.batch';batch.write_text(f'reput "{stream.as_posix()}" "/home/ubuntu/season-balance-20261107-f03-fixed-app-r1-upload/stream.bin.part"\nbye\n')
command=['sftp','-R','4','-B','16384','-l','256','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-b',str(batch),'ubuntu@43.172.70.182']
class M(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','p','ap','v','av','e']]
def available():
 m=M();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
assert min(samples)>=3*1024**3
(out/'admission.original.json').write_text(json.dumps(dict(samples=samples,reserve_bytes=2*1024**3,startup_bytes=1024**3,remaining_bytes=len(raw)-observation['bytes'],same_file=True,no_worker_launch=True),indent=2)+'\n')
with (out/'stdout.original.log').open('wb') as stdout,(out/'stderr.original.log').open('wb') as stderr:
 child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
 (out/'handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=command),indent=2)+'\n')
 started=last=time.monotonic()
 while child.poll() is None:
  if available()<2*1024**3:child.kill();child.wait(timeout=10);raise RuntimeError('Owned transfer reached memory floor; reconcile its own SSH child')
  if time.monotonic()-started>180:raise RuntimeError('Follow same live SFTP handle; do not duplicate')
  if time.monotonic()-last>=30:print(json.dumps(dict(pid=child.pid,live=True,same_file=True)),flush=True);last=time.monotonic()
  time.sleep(.25)
result=dict(exit=child.returncode,same_file_reput=True,transport_profile='4 requests x16KiB;256kbit/s;client session only',no_worker_launch=True)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));assert child.returncode==0
