from pathlib import Path
import sys,struct,json,hashlib,io,tarfile,subprocess,shutil,time,os
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r103');label='season-balance-20261102-a03-runtime-r103'
assert not root.exists(),'Follow any existing owned runtime handle; do not duplicate'
header=sys.stdin.buffer.read(4);assert len(header)==4;length=struct.unpack('!I',header)[0];assert length<1024**2
mfraw=sys.stdin.buffer.read(length);mf=json.loads(mfraw)
assert mf['image']=='sha256:b34b01ff381aa920264e3920d7a7a49e6c1056091999dfc6268107d07029b9f4'
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task='+label,'--format','{{.ID}}']).strip()
pg='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
p=json.loads(subprocess.check_output(['docker','inspect',pg]))[0]
assert p['State']['Status']=='running' and p['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
def resource():
 m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu')
 return dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total)
samples=[]
for _ in range(3):
 r=resource();samples.append(r)
 assert r['available_ram']>=1800*1024**2 and r['free_disk']>=3*1024**3+mf['expanded_bytes']+mf['runtime_staging_margin']+2*1024**2 and r['disk_fraction']>=.05
 time.sleep(1)
data=sys.stdin.buffer.read();assert len(data)==mf['payload_bytes'] and hashlib.sha256(data).hexdigest()==mf['payload_sha256']
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tf:
 members=tf.getmembers();assert {x.name for x in members}==set(mf['files'])
 for entry in members:
  assert entry.isfile() and (root/'input'/entry.name).resolve().is_relative_to((root/'input').resolve())
  assert hashlib.sha256(tf.extractfile(entry).read()).hexdigest()==mf['files'][entry.name]
 root.mkdir(mode=0o700);work=root/'input';work.mkdir();tf.extractall(work)
(root/'manifest.json').write_bytes(mfraw)
(root/'staging-admission.original.json').write_text(json.dumps(dict(kind='precompiled runtime, no SDK build or package restore',samples=samples,expanded_bytes=mf['expanded_bytes'],staging_margin_bytes=mf['runtime_staging_margin'],SDK_guard_unchanged_and_not_used=True))+'\n')
results=root/'results';results.mkdir();os.chown(results,1000,1000)
# Root must remain traversable to the numeric unprivileged test user; secrets
# stay in a separate root-owned 0600 environment file.
root.chmod(0o755)
for folder,_,names in os.walk(work):
 os.chmod(folder,0o755)
 for name in names:os.chmod(Path(folder)/name,0o644)
r=resource();assert r['available_ram']>=1800*1024**2 and r['free_disk']>=3*1024**3+mf['runtime_staging_margin'] and r['disk_fraction']>=.05
credentials=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())
private=root/'runtime.env';private.write_text('FANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database=season_stage;Username=season_stage;Password='+credentials['password']+';MaxPoolSize=16;Timeout=10;CommandTimeout=30\n');private.chmod(0o600)
filters=['PostgresRewardRefreshFundingTests']
command=['/workspace/bin/FantasyCard.Server.Tests.dll','-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose','-trx','/results/season-archive-runtime.trx','-xml','/results/xunit.original.xml']
for name in filters:command+=['-class','FantasyCard.Server.Tests.Persistence.'+name]
args=['docker','run','-d','--name','fc-season-archive-runtime-r103','--label','com.fantasycard.task='+label,'--network','container:'+pg,'--memory','1200m','--memory-swap','1200m','--cpus','1','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=128m,mode=1777','--user','1000:1000','-v',str(work)+':/workspace:ro','-v',str(results)+':/results','-w','/workspace','--env-file',str(private),'-e','DOTNET_CLI_HOME=/tmp','-e','DOTNET_NOLOGO=1','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','--entrypoint','dotnet',mf['image']]+command
cid=subprocess.check_output(args,text=True,timeout=20).strip()
proof=dict(container_id=cid,name='fc-season-archive-runtime-r103',label=label,database_container=pg,image_id=mf['image'],payload_sha256=mf['payload_sha256'],precompiled_on_local=True,cloud_SDK_started=False,production_database_used=False,new_game_matches=0,memory_mib=1200,cpus=1,command=command,admission_after_staging=r,started_at=time.time())
(root/'runtime-handle.json').write_text(json.dumps(proof,indent=2)+'\n')
guard=r"""from pathlib import Path
import time,json,subprocess,shutil
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r103');h=json.loads((root/'runtime-handle.json').read_text());cid=h['container_id']
with (root/'resource-guard.original.jsonl').open('x') as log:
 while True:
  p=json.loads(subprocess.check_output(['docker','inspect',cid]))[0];assert p['Config']['Labels']['com.fantasycard.task']==h['label']
  m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage(root)
  row=dict(at=time.time(),available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total,state=p['State']['Status']);log.write(json.dumps(row)+'\n');log.flush()
  if p['State']['Status']=='exited':
   (root/'guard-terminal.original.json').write_text(json.dumps(dict(state='exited',exit_code=p['State']['ExitCode'],owned_runtime_only=True))+'\n');break
  reason='ResourceProtectionStop' if row['available_ram']<500*1024**2 or d.free<3*1024**3 or d.free/d.total<.05 else 'ObservationWindowStop' if time.time()-h['started_at']>600 else None
  if reason:
   subprocess.run(['docker','stop','--time','10',cid],check=True)
   (root/'guard-terminal.original.json').write_text(json.dumps(dict(state=reason,owned_runtime_only=True,**row))+'\n');break
  time.sleep(2)
"""
(root/'resource-guard.py').write_text(guard)
g=subprocess.Popen(['python3',str(root/'resource-guard.py')],stdin=subprocess.DEVNULL,stdout=(root/'guard.stdout.original.log').open('x'),stderr=(root/'guard.stderr.original.log').open('x'),start_new_session=True)
(root/'guard-handle.json').write_text(json.dumps(dict(pid=g.pid,container_id=cid,only_owned_runtime_may_be_stopped=True))+'\n')
print(json.dumps(proof),flush=True)
