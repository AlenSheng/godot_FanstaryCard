from pathlib import Path
import subprocess,json,base64,shlex,os,ctypes,time,hashlib,uuid,datetime
base=Path(__file__).parent;public=base/'f03-readiness-r1';private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-backup-r1')
assert private.is_absolute() and not private.exists();private.mkdir(parents=True)
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid=subprocess.check_output(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],creationflags=flags).decode().strip()
assert sid.startswith('S-1-5-')
acl=subprocess.run(['icacls',str(private),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],capture_output=True,creationflags=flags)
(private/'ACL-setup.private.log').write_bytes(acl.stdout+acl.stderr);assert acl.returncode==0
job='fc-f03-backup-'+uuid.uuid4().hex
(private/'ownership.original.json').write_text(json.dumps({'task':'season-balance-20261102','job':job,'private_database_copy':True,'do_not_publish_or_stage_contents':True})+'\n')
code=r'''from pathlib import Path
import subprocess,json,shutil,threading,time,sys,datetime
cid='e140d6f8ab9f';job=JOB
d=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
assert d['State']['Running'] and d['Config']['Labels']['com.docker.compose.project']=='fantasycard-cloud' and d['Config']['Labels']['com.docker.compose.service']=='postgres'
def sample():
 m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());disk=shutil.disk_usage('/home/ubuntu')
 r={'available_ram':int(m['MemAvailable'].split()[0])*1024,'free_disk':disk.free,'disk_fraction':disk.free/disk.total}
 r['guard_ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05
 return r
first=sample();assert first['guard_ok']
print(json.dumps({'kind':'backup-admission','sample':first,'job':job}),file=sys.stderr,flush=True)
stop=threading.Event();breach=threading.Event()
def watch():
 while not stop.wait(1):
  r=sample();print(json.dumps({'kind':'backup-resource','sample':r}),file=sys.stderr,flush=True)
  if not r['guard_ok']:
   breach.set()
   # Only this uniquely named read-only pg_dump connection may be cancelled.
   sql="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='"+job+"' AND usename='fantasycard' AND datname='fantasycard' AND pid<>pg_backend_pid()"
   subprocess.run(['docker','exec',cid,'psql','-U','fantasycard','-d','fantasycard','-X','-qAt','-c',sql],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12)
   return
thread=threading.Thread(target=watch,daemon=True);thread.start()
try:
 result=subprocess.run(['docker','exec',cid,'pg_dump','--dbname','host=/var/run/postgresql dbname=fantasycard user=fantasycard application_name='+job,'--format=custom','--no-owner','--no-privileges'],stdout=sys.stdout.buffer,stderr=sys.stderr)
finally:
 stop.set();thread.join(timeout=15)
print(json.dumps({'kind':'backup-terminal','exit':result.returncode,'guard_ok':not breach.is_set(),'last_sample':sample(),'app_or_database_rows_written':False}),file=sys.stderr,flush=True)
raise SystemExit(result.returncode if not breach.is_set() else 91)
'''.replace('JOB',repr(job))
(private/'remote-backup-source.original.py').write_text(code,encoding='utf-8')
remote='sudo -n python3 -B -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
ssh=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','ubuntu@43.172.70.182',remote]
class Memory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
def available():
    v=Memory();v.length=ctypes.sizeof(v);assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(v));return v.available
samples=[]
for _ in range(3):samples.append(available());time.sleep(1)
assert min(samples)>=3*1024**3
part=private/'production-before-season.dump.part';final=private/'production-before-season.dump'
assert part.resolve().parent==private.resolve() and final.resolve().parent==private.resolve() and not part.exists() and not final.exists()
with part.open('xb') as output,(private/'backup-stderr.private.log').open('xb') as errors:
    child=subprocess.Popen(ssh,stdin=subprocess.DEVNULL,stdout=output,stderr=errors,creationflags=flags)
    (public/'backup-handle.original.json').write_text(json.dumps({'pid':child.pid,'job':job,'private_destination':str(private),'binary_stdout_never_printed':True,'started_at':time.time()})+'\n')
    guard=None;started=time.monotonic();announced=started
    while child.poll() is None:
        if available()<2*1024**3:guard='Local2GiB';child.terminate();break
        if time.monotonic()-started>600:guard='Observation600s';child.terminate();break
        if time.monotonic()-announced>=30:print(json.dumps({'backup_child_pid':child.pid,'still_live':True,'private_bytes_received':part.stat().st_size}),flush=True);announced=time.monotonic()
        time.sleep(.25)
    child.wait(timeout=20)
assert child.returncode==0 and guard is None
with part.open('rb') as f:assert f.read(5)==b'PGDMP'
digest=hashlib.sha256(part.read_bytes()).hexdigest();size=part.stat().st_size;assert size>0
part.rename(final)
private_lines=(private/'backup-stderr.private.log').read_text(encoding='utf-8',errors='replace').splitlines();resources=[];terminal=None
for line in private_lines:
    if line.startswith('{"kind":'):
        row=json.loads(line)
        if row['kind'] in ['backup-admission','backup-resource']:resources.append(row['sample'])
        if row['kind']=='backup-terminal':terminal=row
assert terminal and terminal['exit']==0 and terminal['guard_ok'] and all(r['guard_ok'] for r in resources)
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job':job,'private_directory':str(private),'backup_filename':final.name,'backup_sha256':digest,'backup_bytes':size,'private_ACL_applied':True,'local_admission_bytes':samples,'cloud_guard_samples':resources,'streamed_without_remote_dump_file':True,'pg_dump_custom_header_valid':True,'pg_restore_list_verified':False,'restore_or_migration_rehearsal_verified':False,'app_or_database_rows_written':False,'SDK_started':False,'new_gameplay_cases':0,'F03_complete':False}
(public/'private-backup-receipt.derived.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'backup_sha256':digest,'backup_bytes':size,'private_ACL_applied':True,'rows_written':False,'new_gameplay_cases':0,'restore_tested':False}))
