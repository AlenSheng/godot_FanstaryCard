from pathlib import Path
import json,hashlib,struct,subprocess,base64,shlex,time,os,tarfile,io,ctypes
base=Path(__file__).parent;repo=Path.cwd();out=base/'d04-room-events-cloud-r2-file';assert not out.exists();out.mkdir()
source=base/'d04-room-events-cloud-input-r2';manifest=json.loads((source/'manifest.json').read_bytes());payload=(source/'payload.tar.gz').read_bytes();assert hashlib.sha256(payload).hexdigest()==manifest['payload_sha256']
header=json.dumps(manifest).encode();stream=struct.pack('!I',len(header))+header+payload;(out/'transport-stream.original.bin').write_bytes(stream);stream_sha=hashlib.sha256(stream).hexdigest();size=len(stream);del payload,stream
worker=(base/'start-d04-room-events-cloud-r2.py').read_text(encoding='utf-8');(out/'worker-source.original.py').write_bytes(worker.encode())
encoded=base64.b64encode(worker.encode()).decode();launch='import base64;exec(base64.b64decode('+repr(encoded)+'))';launch_sha=hashlib.sha256(launch.encode()).hexdigest()
ssh=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','ubuntu@43.172.70.182'];flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
class Memory(ctypes.Structure):
 _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
 m=Memory();m.length=ctypes.sizeof(m);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m));return m.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
(out/'admission.original.json').write_text(json.dumps(dict(samples=samples,reserve=2*1024**3,startup=1024**3))+'\n');assert min(samples)>=3*1024**3
def remote(code,label):
 assert available()>=2*1024**3,'Local resource protection; detached job must be followed by its existing handle.'
 command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
 r=subprocess.run(ssh+[command],capture_output=True,timeout=40,creationflags=flags);(out/(label+'.stdout.original.log')).write_bytes(r.stdout);(out/(label+'.stderr.original.log')).write_bytes(r.stderr)
 (out/(label+'.terminal.original.json')).write_text(json.dumps(dict(exit=r.returncode))+'\n');assert r.returncode==0,r.stderr.decode(errors='replace');return json.loads(r.stdout)
setup="""from pathlib import Path
import os,json,subprocess,hashlib,shutil,pwd
root=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2-upload');runtime=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2')
assert not root.exists() and not runtime.exists()
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261106-d04-room-events-r2','-q']).strip()
disk=shutil.disk_usage('/home/ubuntu');memory=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines())
available=int(memory['MemAvailable'].split()[0])*1024;assert available>=1800*1024**2+SIZE and disk.free>=3*1024**3 and disk.free/disk.total>=.05
root.mkdir(mode=0o700);user=pwd.getpwnam('ubuntu');subprocess.check_call(['mount','-t','tmpfs','-o',f'size=32m,nosuid,nodev,mode=0700,uid={user.pw_uid},gid={user.pw_gid}','fc-d04-room-events-upload',str(root)])
marker=dict(stream_bytes=SIZE,stream_sha256=SHA,runtime=str(runtime),owns_tmpfs=True);(root/'ownership.original.json').write_text(json.dumps(marker)+'\\n')
print(json.dumps(marker))
""".replace('SIZE',str(size)).replace('SHA',repr(stream_sha))
proof=remote(setup,'setup');(out/'setup.original.json').write_text(json.dumps(proof,indent=2)+'\n');print('Owned32MiB tmpfs upload admitted; no runtime worker started.',flush=True)
batch=out/'sftp-put.batch';batch.write_text('put "'+(out/'transport-stream.original.bin').as_posix()+'" "/home/ubuntu/season-balance-20261106-d04-room-events-r2-upload/stream.bin.part"\nbye\n',encoding='utf-8')
cmd=['sftp','-R','4','-B','32768','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','-b',str(batch),'ubuntu@43.172.70.182']
child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=flags);(out/'sftp-handle.original.json').write_text(json.dumps(dict(pid=child.pid,parent_pid=os.getpid(),started_at=time.time(),runtime_started=False))+'\n')
guard=None;announced=time.monotonic()
while True:
 try:stdout,stderr=child.communicate(timeout=.25);break
 except subprocess.TimeoutExpired:
  if available()<2*1024**3:
   guard='Local2GiB';child.terminate();stdout,stderr=child.communicate(timeout=15);break
  if time.monotonic()-announced>=30:print(json.dumps(dict(stage='SFTP transfer',pid=child.pid,still_live=True)),flush=True);announced=time.monotonic()
(out/'sftp.stdout.original.log').write_bytes(stdout);(out/'sftp.stderr.original.log').write_bytes(stderr);(out/'sftp-terminal.original.json').write_text(json.dumps(dict(pid=child.pid,exit=child.returncode,guard=guard))+'\n');assert child.returncode==0 and guard is None,stderr.decode(errors='replace')
start="""from pathlib import Path
import os,json,subprocess,hashlib,sys
root=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2-upload');runtime=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2');p=root/'stream.bin.part'
assert root.resolve()==root and not p.is_symlink() and p.stat().st_size==__BYTES__ and hashlib.sha256(p.read_bytes()).hexdigest()==__STREAM_SHA__
assert not runtime.exists() and not (root/'launch.original.json').exists()
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261106-d04-room-events-r2','-q']).strip()
assert subprocess.check_output(['findmnt','-n','-o','FSTYPE','--target',str(root)]).decode().strip()=='tmpfs'
with p.open('rb') as input_file,(root/'worker.stdout.original.log').open('xb') as log:
 child=subprocess.Popen(['python3','-u','-c',__LAUNCH_CODE__],stdin=input_file,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
proof=dict(pid=child.pid,stream_bytes=__BYTES__,stream_sha256=__STREAM_SHA__,launcher_sha256=__LAUNCH_SHA__,detached=True,stdin_is_verified_local_regular_file=True)
(root/'launch.original.json').write_text(json.dumps(proof)+'\\n');print(json.dumps(proof))
""".replace('__BYTES__',str(size)).replace('__STREAM_SHA__',repr(stream_sha)).replace('__LAUNCH_SHA__',repr(launch_sha)).replace('__LAUNCH_CODE__',repr(launch))
handle=remote(start,'launch');(out/'runtime-handle.original.json').write_text(json.dumps(handle,indent=2)+'\n');print('Verified complete stream, detached worker launched: '+str(handle['pid']),flush=True)
poll="""from pathlib import Path
import json,hashlib
root=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2');upload=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2-upload');a=root/'public-evidence.tar.gz';p=Path('/proc',str(PID));live=False
if p.exists():
 try:live=any(hashlib.sha256(x).hexdigest()==DIGEST for x in (p/'cmdline').read_bytes().split(bytes([0]))) and (p/'stat').read_text().split()[2]!='Z'
 except OSError:pass
print(json.dumps(dict(worker_live=live,archive_exists=a.exists(),archive_sha256=hashlib.sha256(a.read_bytes()).hexdigest() if a.exists() else None,result=json.loads((root/'public/result.json').read_text()) if (root/'public/result.json').exists() else None)))
""".replace('PID',str(handle['pid'])).replace('DIGEST',repr(launch_sha))
for i in range(60):
 status=remote(poll,'poll-'+str(i));print(json.dumps(status),flush=True)
 if status['archive_exists'] and not status['worker_live']:break
 if not status['worker_live'] and not status['archive_exists']:raise RuntimeError('Owned worker is terminal without an archive; reconcile this exact root before retry.')
 time.sleep(10)
else:raise RuntimeError('Observation window ended; follow the same detached PID/root, never duplicate launch.')
r=subprocess.run(ssh+['sudo -n cat /home/ubuntu/season-balance-20261106-d04-room-events-r2/public-evidence.tar.gz'],capture_output=True,timeout=60,creationflags=flags);assert r.returncode==0 and hashlib.sha256(r.stdout).hexdigest()==status['archive_sha256'];(out/'public-evidence.tar.gz').write_bytes(r.stdout)
public=out/'public';public.mkdir()
with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:gz') as archive:
 for member in archive.getmembers():
  assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
  p=public/member.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(member).read())
result=json.loads((public/'result.json').read_bytes());result['collected_raw_archive_sha256']=status['archive_sha256'];result['input_received_from_verified_SFTP_file']=True
binary=base/'d04-room-events-build-r3/build/bin/FantasyCard.Server.Tests/debug';result['local_binary_inputs_unchanged']=all(hashlib.sha256(((binary/Path(n).relative_to('bin')) if n.startswith('bin/') else repo/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
cleanup="""from pathlib import Path
import subprocess,json,hashlib,base64
root=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2-upload');runtime=Path('/home/ubuntu/season-balance-20261106-d04-room-events-r2')
assert root.resolve()==root and not root.is_symlink() and hashlib.sha256((root/'stream.bin.part').read_bytes()).hexdigest()==SHA
assert (runtime/'public/cleanup.original.json').exists() and not (runtime/'runtime.private.env').exists()
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261106-d04-room-events-r2','-q']).strip()
log=(root/'worker.stdout.original.log').read_bytes();subprocess.check_call(['umount',str(root)]);assert not list(root.iterdir())
print(json.dumps(dict(upload_tmpfs_unmounted=True,source_stream_local_original_retained=True,worker_stdout_base64=base64.b64encode(log).decode(),other_projects_modified=False)))
""".replace('SHA',repr(stream_sha))
clean=remote(cleanup,'upload-cleanup');(out/'worker.stdout.original.log').write_bytes(base64.b64decode(clean.pop('worker_stdout_base64')));(out/'upload-cleanup.original.json').write_text(json.dumps(clean,indent=2)+'\n')
print((public/'test.original.log').read_text(encoding='utf-8')[-6000:]);print(json.dumps(result));assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['schemas_still_present']==[]
