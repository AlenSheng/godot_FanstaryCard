"""Lossless transport only: every decoded member must match the full payload SHA."""
import hashlib,struct,zlib

MAGIC=b'FCBDZ1\0\0'
BLOCK=16384
BACK=8192
MAX_FILE=64*1024**2

def encode(base,target):
    assert len(target)<=MAX_FILE
    result=bytearray(MAGIC+hashlib.sha256(base).digest()+struct.pack('!QII',len(target),BLOCK,BACK))
    for offset in range(0,len(target),BLOCK):
        dictionary=base[max(0,offset-BACK):offset+BLOCK+BACK]
        compressor=zlib.compressobj(9,zlib.DEFLATED,zlib.MAX_WBITS,zdict=dictionary) if dictionary else zlib.compressobj(9)
        compressed=compressor.compress(target[offset:offset+BLOCK])+compressor.flush()
        result.extend(struct.pack('!I',len(compressed)));result.extend(compressed)
    return bytes(result)

def decode(base,patch):
    if len(patch)<56 or patch[:8]!=MAGIC or patch[8:40]!=hashlib.sha256(base).digest():raise ValueError('Binary transport base or header differs.')
    length,block,back=struct.unpack('!QII',patch[40:56])
    if length>MAX_FILE or block!=BLOCK or back!=BACK:raise ValueError('Binary transport bounds differ.')
    position=56;result=bytearray()
    for offset in range(0,length,block):
        if position+4>len(patch):raise ValueError('Truncated binary transport length.')
        size=struct.unpack('!I',patch[position:position+4])[0];position+=4
        if size>BLOCK+1024 or position+size>len(patch):raise ValueError('Binary transport block is outside its bounds.')
        dictionary=base[max(0,offset-BACK):offset+block+back]
        decompressor=zlib.decompressobj(zdict=dictionary) if dictionary else zlib.decompressobj()
        expected=min(block,length-offset)
        value=decompressor.decompress(patch[position:position+size],expected+1);position+=size
        if len(value)!=expected or not decompressor.eof or decompressor.unconsumed_tail or decompressor.unused_data:
            raise ValueError('Binary transport block did not decode exactly.')
        result.extend(value)
    if position!=len(patch) or len(result)!=length:raise ValueError('Binary transport has trailing or missing data.')
    return bytes(result)

from pathlib import Path
import sys,struct,json,hashlib,io,tarfile,subprocess,shutil,time,os
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r115');label='season-balance-20261102-a03-runtime-r115'
assert not root.exists(),'Follow any existing owned runtime handle; do not duplicate'
header=sys.stdin.buffer.read(4);assert len(header)==4;size=struct.unpack('!I',header)[0];assert size<1024**2
control=json.loads(sys.stdin.buffer.read(size));mfraw=__import__('base64').b64decode(control['target_manifest_base64']);mf=json.loads(mfraw);delta=control['delta']
base=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r109');base_m=json.loads((base/'manifest.json').read_text());assert base_m['payload_sha256']==delta['base_payload_sha256']
assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r109','--format','{{.ID}}']).strip()
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
 assert r['available_ram']>=(1800+64)*1024**2 and r['free_disk']>=3*1024**3+delta['staging_allocation_bytes']+mf['runtime_staging_margin']+2*1024**2+delta['delta_bytes'] and r['disk_fraction']>=.05
 time.sleep(1)
data=sys.stdin.buffer.read();assert len(data)==delta['delta_bytes'] and hashlib.sha256(data).hexdigest()==delta['delta_sha256']
source=base/'input';base_files={p.relative_to(source).as_posix():p for p in source.rglob('*') if p.is_file()}
assert set(base_files)==set(base_m['files'])
for n,p in base_files.items():assert not p.is_symlink() and p.resolve().is_relative_to(source.resolve()) and hashlib.sha256(p.read_bytes()).hexdigest()==base_m['files'][n]
assert delta['format']=='FCBDZ1' and delta['staging_method']=='tmpfs_byte_verified_full_copy' and delta['tmpfs_allocation_bytes']==64*1024**2
assert os.stat(source).st_dev==os.stat(root.parent).st_dev
assert not any(p.is_symlink() for p in source.rglob('*'))
root.mkdir(mode=0o700);work=root/'input';work.mkdir()
subprocess.run(['mount','-t','tmpfs','-o','size=67108864,nosuid,nodev,mode=0755','season-runtime110-input',str(work)],check=True)
shutil.copytree(source,work,dirs_exist_ok=True,copy_function=shutil.copy2)
for n in delta['removed_files']:
 p=(work/n).resolve();assert p.is_relative_to(work.resolve());p.unlink()
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tf:
 members=tf.getmembers();assert {x.name for x in members}==set(delta['changed_files'])
 for entry in members:
  assert entry.isfile();p=(work/entry.name).resolve();assert p.is_relative_to(work.resolve());encoded=tf.extractfile(entry).read();original=base_files[entry.name].read_bytes() if entry.name in base_files else b'';value=decode(original,encoded);assert hashlib.sha256(value).hexdigest()==mf['files'][entry.name];p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():p.unlink()
  p.write_bytes(value)
actual={p.relative_to(work).as_posix():p for p in work.rglob('*') if p.is_file()};assert set(actual)==set(mf['files'])
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==mf['files'][n] for n,p in actual.items())
assert all(hashlib.sha256(p.read_bytes()).hexdigest()==base_m['files'][n] for n,p in base_files.items())
(root/'delta-staging.original.json').write_text(json.dumps(dict(base_payload_sha256=base_m['payload_sha256'],target_payload_sha256=mf['payload_sha256'],delta_sha256=delta['delta_sha256'],changed_files=delta['changed_files'],all_target_files_verified=True,base_input_unchanged=True,base_input_reverified_after_reconstruction=True,staging_method=delta['staging_method'],new_data_and_metadata_budget=delta['staging_allocation_bytes'],full_expanded_bytes=mf['expanded_bytes']))+chr(10))
(root/'manifest.json').write_bytes(mfraw)
(root/'staging-admission.original.json').write_text(json.dumps(dict(kind='precompiled runtime, no SDK build or package restore',samples=samples,expanded_bytes=mf['expanded_bytes'],staging_margin_bytes=mf['runtime_staging_margin'],SDK_guard_unchanged_and_not_used=True))+'\n')
results=root/'results';results.mkdir();os.chown(results,1000,1000)
# Root must remain traversable to the numeric unprivileged test user; secrets
# stay in a separate root-owned 0600 environment file.
root.chmod(0o755)
for folder,_,names in os.walk(work):
 os.chmod(folder,0o755)
 for name in names:os.chmod(Path(folder)/name,0o644)
r=resource();assert r['available_ram']>=(1800+64)*1024**2 and r['free_disk']>=3*1024**3+mf['runtime_staging_margin'] and r['disk_fraction']>=.05
credentials=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())
private=root/'runtime.env';private.write_text('FANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database=season_stage;Username=season_stage;Password='+credentials['password']+';MaxPoolSize=16;Timeout=10;CommandTimeout=30\n');private.chmod(0o600)
command=['-c',"set -e\ndotnet /workspace/bin/FantasyCard.Server.Tests.dll -noLogo -noColor -noAutoReporters -failSkips -parallel none -reporter verbose -trx /results/group-a.trx -xml /results/group-a.xml -method 'FantasyCard.Server.Tests.Persistence.PostgresAssetDomainCompositeTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonAssetDomainTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonArchiveTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonReadModelTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonLoadoutTests.*'\ndotnet /workspace/bin/FantasyCard.Server.Tests.dll -noLogo -noColor -noAutoReporters -failSkips -parallel none -reporter verbose -trx /results/group-b.trx -xml /results/group-b.xml -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonPreparationTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonMatchmakingTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresHistoricalEquipmentTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresPreparationConfigVersionTests.*'\ndotnet /workspace/bin/FantasyCard.Server.Tests.dll -noLogo -noColor -noAutoReporters -failSkips -parallel none -reporter verbose -trx /results/group-c.trx -xml /results/group-c.xml -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonRoomTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresConfigVersionRoomTests.*' -method 'FantasyCard.Server.Tests.Persistence.PostgresSeasonSettlementTests.*'\n"]
args=['docker','run','-d','--name','fc-season-archive-runtime-r115','--label','com.fantasycard.task='+label,'--network','container:'+pg,'--memory','1200m','--memory-swap','1200m','--cpus','1','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=128m,mode=1777','--user','1000:1000','-v',str(work)+':/workspace:ro','-v',str(results)+':/results','-w','/workspace','--env-file',str(private),'-e','FANTASYCARD_E2E_SERVER_DLL=/workspace/bin/FantasyCard.Server.dll','-e','FANTASYCARD_E2E_PROCESS_LOG_DIR=/results/process-logs','-e','FANTASYCARD_JOURNEY_REWARD_INTEROP_DIR=/results/journey-reward-client','-e','DOTNET_CLI_HOME=/tmp','-e','DOTNET_NOLOGO=1','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1','--entrypoint','/bin/sh',mf['image']]+command
cid=subprocess.check_output(args,text=True,timeout=20).strip()
proof=dict(container_id=cid,name='fc-season-archive-runtime-r115',label=label,database_container=pg,image_id=mf['image'],payload_sha256=mf['payload_sha256'],precompiled_on_local=True,cloud_SDK_started=False,production_database_used=False,new_game_matches=0,memory_mib=1200,cpus=1,command=command,admission_after_staging=r,started_at=time.time())
(root/'runtime-handle.json').write_text(json.dumps(proof,indent=2)+'\n')
guard=r"""from pathlib import Path
import time,json,subprocess,shutil
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r115');h=json.loads((root/'runtime-handle.json').read_text());cid=h['container_id']
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
   (root/'guard-terminal.original.json').write_text(json.dumps(dict(row,state=reason,owned_runtime_only=True))+'\n');break
  time.sleep(2)
"""
(root/'resource-guard.py').write_text(guard)
g=subprocess.Popen(['python3',str(root/'resource-guard.py')],stdin=subprocess.DEVNULL,stdout=(root/'guard.stdout.original.log').open('x'),stderr=(root/'guard.stderr.original.log').open('x'),start_new_session=True)
(root/'guard-handle.json').write_text(json.dumps(dict(pid=g.pid,container_id=cid,only_owned_runtime_may_be_stopped=True))+'\n')
print(json.dumps(proof),flush=True)
