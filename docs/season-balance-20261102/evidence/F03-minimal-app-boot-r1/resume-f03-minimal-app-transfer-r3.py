from pathlib import Path
import ctypes,hashlib,json,os,subprocess,time

b=Path(__file__).parent;original=(b/'run-f03-minimal-app-cloud-r3.py').read_text('utf-8')
prefix=original.split("prepared=remote(setup,'setup')",1)[0].replace("out=b/'f03-minimal-app-cloud-r3'","out=b/'f03-minimal-app-cloud-resume-r3'")
assert prefix!=original and "launch=f'''" in original
namespace={'__file__':str(Path(__file__)),'__name__':'__main__'};exec(compile(prefix,str(Path(__file__)),'exec'),namespace)
out=namespace['out'];remote=namespace['remote'];upload=namespace['upload'];root=namespace['root'];stream=namespace['stream'];transport=namespace['transport']
code=f'''from pathlib import Path
import hashlib,json,subprocess
u=Path({upload!r});r=Path({root!r});p=u/'stream.bin.part'
assert u.exists() and not r.exists() and not (u/'launch.original.json').exists() and p.is_file() and not p.is_symlink()
assert json.loads((u/'ownership.original.json').read_text())['sha256']=={transport['sha256']!r}
assert not subprocess.check_output(['docker','ps','-a','-q','--filter','label=com.fantasycard.task=season-balance-20261107-f03-minimal-app-r3']).strip()
print(json.dumps(dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),worker_started=False)))
'''
prior=remote(code,'same-upload-preflight');assert 0<prior['bytes']<=transport['bytes'] and hashlib.sha256(stream.read_bytes()[:prior['bytes']]).hexdigest()==prior['sha256']
(out/'prior-transfer-observation.original.json').write_text(json.dumps(dict(prior_observation_timeout_seconds=90,old_local_handles_missing=True,remote_partial_verified_as_exact_prefix=prior,original_stream_sha256=transport['sha256'],same_task_same_upload=True),indent=2)+'\n')
batch=out/'sftp-reput.original.batch';batch.write_text(f'reput "{stream.as_posix()}" "{upload}/stream.bin.part"\nbye\n')
command=['sftp','-R','64','-B','32768','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','-b',str(batch),'ubuntu@43.172.70.182']
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    s=Memory();s.length=ctypes.sizeof(s);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s));return s.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
assert min(samples)>=3*1024**3
(out/'transfer-admission.original.json').write_text(json.dumps(dict(samples=samples,reserve_GiB=2,startup_GiB=1))+'\n')
with (out/'sftp.stdout.original.log').open('wb') as stdout,(out/'sftp.stderr.original.log').open('wb') as stderr:
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    (out/'sftp-handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),command=command,started_at=time.time(),runtime_started=False),indent=2)+'\n')
    started=last=time.monotonic()
    while child.poll() is None:
        if available()<2*1024**3:
            child.kill();child.wait(timeout=10);raise RuntimeError('Owned SFTP reached2GiB reserve; reconcile its child SSH before any next action')
        if time.monotonic()-started>150:raise RuntimeError('Follow recorded still-live same SFTP handle; do not launch a duplicate')
        if time.monotonic()-last>=30:print(json.dumps(dict(stage='same-file reput',pid=child.pid,live=True)),flush=True);last=time.monotonic()
        time.sleep(.25)
assert child.returncode==0,(out/'sftp.stderr.original.log').read_text(errors='replace')[-1000:]
(out/'sftp-terminal.original.json').write_text(json.dumps(dict(exit=child.returncode,same_file_reput=True))+'\n')
tail="launch=f'''"+original.split("launch=f'''",1)[1]
exec(compile(tail,str(Path(__file__)),'exec'),namespace)

