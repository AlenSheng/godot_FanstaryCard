from pathlib import Path
import base64,hashlib,importlib.util,io,json,os,shlex,subprocess,tarfile,time

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-fixed-app-cloud-r1';assert not out.exists()
ordinary=json.loads((b/'f03-fixed-ordinary-r1/result.json').read_bytes());probes=json.loads((b/'f03-fixed-probes-r1/result.json').read_bytes())
assert ordinary['ok'] and ordinary['own_job_closed'] and ordinary['own_PG_stopped']
assert probes['public_surface_equal'] and probes['snapshot_canonical_results_equal']
out.mkdir()
input_dir=b/'f03-fixed-app-input-r1';transport=json.loads((input_dir/'transport.original.json').read_bytes());stream=input_dir/'stream.bin';assert stream.stat().st_size==transport['bytes'] and hashlib.sha256(stream.read_bytes()).hexdigest()==transport['sha256']
worker=(b/'f03-fixed-app-worker-r1.py').read_text('utf-8');worker_sha=hashlib.sha256(worker.encode()).hexdigest();(out/'worker.original.py').write_text(worker,encoding='utf-8')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
ssh=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','ubuntu@43.172.70.182']
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
def remote(code,label):
    command='sudo -n python3 -B -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
    r=guard.guarded_run(ssh+[command],env=dict(os.environ),timeout=45,wait_seconds=30)
    (out/(label+'.stdout.original.log')).write_text(r.stdout,encoding='utf-8');(out/(label+'.stderr.original.log')).write_text(r.stderr,encoding='utf-8');assert r.returncode==0,r.stderr[-1500:]
    return json.loads(r.stdout)
label='season-balance-20261107-f03-fixed-app-r1';upload='/home/ubuntu/'+label+'-upload';root='/home/ubuntu/'+label
setup=f'''from pathlib import Path
import json,os,pwd,shutil,subprocess
upload=Path({upload!r});root=Path({root!r});assert not upload.exists() and not root.exists()
assert not subprocess.check_output(['docker','ps','-a','-q','--filter','label=com.fantasycard.task={label}']).strip()
d=shutil.disk_usage('/home/ubuntu');m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())
assert d.free>=3*1024**3+64*1024**2 and d.free/d.total>=.05 and int(m['MemAvailable'].split()[0])*1024>=700*1024**2
upload.mkdir(mode=0o700);owner=pwd.getpwnam('ubuntu');subprocess.check_call(['mount','-t','tmpfs','-o',f'size=16m,nosuid,nodev,noexec,mode=0700,uid={{owner.pw_uid}},gid={{owner.pw_gid}}','fc-f03-minimal-upload',str(upload)])
(upload/'ownership.original.json').write_text(json.dumps(dict(task={label!r},bytes={transport['bytes']},sha256={transport['sha256']!r})))
print(json.dumps(dict(upload=str(upload),tmpfs=True,production_changed=False)))
'''
prepared=remote(setup,'setup');(out/'setup.original.json').write_text(json.dumps(prepared,indent=2)+'\n')
batch=out/'sftp-put.original.batch';batch.write_text(f'put "{stream.as_posix()}" "{upload}/stream.bin.part"\nbye\n')
command=['sftp','-R','64','-B','32768','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','-b',str(batch),'ubuntu@43.172.70.182']
import ctypes
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    m=Memory();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
assert min(samples)>=3*1024**3
with (out/'sftp.stdout.original.log').open('wb') as stdout,(out/'sftp.stderr.original.log').open('wb') as stderr:
    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=flags)
    (out/'sftp-handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),command=command,started_at=time.time(),observation_seconds=180),indent=2)+'\n')
    began=last=time.monotonic()
    while child.poll() is None:
        if available()<2*1024**3:child.kill();child.wait(timeout=10);raise RuntimeError('Owned transfer reached memory reserve; reconcile child SSH')
        if time.monotonic()-began>180:raise RuntimeError('Follow recorded same live SFTP handle before resuming; no duplicate worker')
        if time.monotonic()-last>=30:print(json.dumps(dict(stage='same complete-file SFTP',pid=child.pid,live=True)),flush=True);last=time.monotonic()
        time.sleep(.25)
assert child.returncode==0

launch=f'''from pathlib import Path
import hashlib,json,subprocess
upload=Path({upload!r});root=Path({root!r});p=upload/'stream.bin.part'
assert p.is_file() and not p.is_symlink() and p.stat().st_size=={transport['bytes']} and hashlib.sha256(p.read_bytes()).hexdigest()=={transport['sha256']!r}
assert not root.exists() and not (upload/'launch.original.json').exists();p.rename(upload/'stream.bin')
with (upload/'worker.stdout.original.log').open('xb') as log:
    child=subprocess.Popen(['python3','-u','-c',{worker!r}],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
proof=dict(pid=child.pid,worker_sha256={worker_sha!r},verified_input=True,root=str(root));(upload/'launch.original.json').write_text(json.dumps(proof));print(json.dumps(proof))
'''
handle=remote(launch,'launch');(out/'handle.original.json').write_text(json.dumps(handle,indent=2)+'\n');print(json.dumps(dict(stage='owned image verification running',pid=handle['pid'],new_gameplay_starts=0)),flush=True)
poll=f'''from pathlib import Path
import hashlib,json
p=Path('/proc/{handle['pid']}');root=Path({root!r});live=False
if p.exists():
    try:live=(p/'stat').read_text().split()[2]!='Z' and any(hashlib.sha256(v).hexdigest()=={worker_sha!r} for v in (p/'cmdline').read_bytes().split(bytes([0])))
    except OSError:pass
a=root/'public-evidence.tar.gz';print(json.dumps(dict(worker_live=live,archive_exists=a.exists(),archive_sha256=hashlib.sha256(a.read_bytes()).hexdigest() if a.exists() else None,result=json.loads((root/'public/result.json').read_text()) if (root/'public/result.json').exists() else None)))
'''
for attempt in range(40):
    state=remote(poll,'poll-'+str(attempt))
    if state['archive_exists'] and not state['worker_live']:break
    if not state['worker_live'] and not state['archive_exists']:raise RuntimeError('Same worker is terminal without archive; inspect its own log, do not duplicate launch')
    if attempt%3==0:print(json.dumps(dict(stage='same owned worker',pid=handle['pid'],live=state['worker_live'])),flush=True)
    time.sleep(5)
else:raise RuntimeError('Follow the same existing worker handle; observation ended without terminal proof')
r=subprocess.run(ssh+['sudo -n cat '+shlex.quote(root+'/public-evidence.tar.gz')],capture_output=True,timeout=45,creationflags=flags);assert r.returncode==0 and hashlib.sha256(r.stdout).hexdigest()==state['archive_sha256'];(out/'public-evidence.original.tar.gz').write_bytes(r.stdout)
public=out/'public';public.mkdir()
with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:gz') as tar:
    for member in tar.getmembers():
        assert member.isfile() and '/' not in member.name and '..' not in member.name
        (public/member.name).write_bytes(tar.extractfile(member).read())
result=json.loads((public/'result.json').read_bytes());cleanup=json.loads((public/'cleanup.original.json').read_bytes())
assert cleanup['production_state_unchanged']
finish=f'''from pathlib import Path
import hashlib,json,subprocess
upload=Path({upload!r});assert upload.resolve()==upload and not upload.is_symlink()
assert hashlib.sha256((upload/'stream.bin').read_bytes()).hexdigest()=={transport['sha256']!r}
subprocess.check_call(['umount',str(upload)]);assert not list(upload.iterdir());print(json.dumps(dict(owned_upload_tmpfs_unmounted=True,local_original_retained=True,production_changed=False)))
'''
finished=remote(finish,'upload-cleanup');(out/'upload-cleanup.original.json').write_text(json.dumps(finished,indent=2)+'\n')
(out/'result.json').write_text(json.dumps(dict(**result,archive_sha256=state['archive_sha256'],upload_tmpfs_unmounted=True),indent=2)+'\n')
print(json.dumps(result));assert result['ok']
