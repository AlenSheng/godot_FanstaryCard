"""Cloud-only fresh source preparation; root fills the concrete published release."""
import fcntl,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
RELEASE='ROOT_REPLACE_FINAL_RELEASE_SHA'
B=Path('/home/ubuntu/pr13-acceptance-20261009');GIT=Path('/opt/fantasycard-github');A='b09-legal-route-r3-20261011';OWNER='pr13-cap-'+A;BOOT=B/'evidence/b09-legal-route-bootstrap-r3-20261011';E=B/'evidence'/A;W=B/'work'/A;SOURCE=W/'source';CACHE=B/'cache/nuget-b09-r2';DONOR=B/'work/b09-legal-route-r2-20261011/source';HOLD=B/'evidence/pool-render-segments-r3/scheduling-hold.json'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(65536),b''):h.update(data)
 return h.hexdigest()
def write(p,v):
 assert not p.exists()
 with p.open('xb') as f:f.write((json.dumps(v,indent=2)+'\n').encode());f.flush();os.fsync(f.fileno())
def command(args):return subprocess.check_output(args,timeout=45)
def unit():return dict(s.split('=',1) for s in command(['systemctl','show',OWNER,'--property=LoadState,MainPID,ActiveState,InvocationID']).decode().splitlines())
assert re.fullmatch('[0-9a-f]{40}',RELEASE)
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 state=unit();assert state['LoadState']=='loaded' and state['ActiveState']=='active' and int(state['MainPID'])>0
 cap=json.loads(command(['python3',str(B/'evidence/cap-experiment-full-r3/controller.py'),'status']));assert cap['current'] is None and cap['logical_verified_units']>=121
 prev=B/'evidence/b08-fixture-lifecycle-r4-20261011';g=json.loads((prev/'local-backup-receipt.json').read_bytes());cleanup=json.loads((prev/'local-storage-cleanup.json').read_bytes());assert g['ok'] is True and g['fixture_lifecycle_outputs_verified'] is True and cleanup['ok'] is True and cleanup['passed_owned_tmpfs_removed'] is True and cleanup['local_G_archive_sha256']==g['sha256']
 restoration_path=B/'evidence/b09-legal-route-bootstrap-r1-20261011/full-nuget-restore-r2-result.json';restored=json.loads(restoration_path.read_bytes());assert restored['ok'] is True and restored['files_verified']==1157 and restored['directories_verified']==777 and restored['cache_root']==str(CACHE) and restored['all_restored_files_SHA_and_modes_verified'] is True
 assert command(['git','-C',str(GIT),'rev-parse','HEAD']).decode().strip()==RELEASE and not command(['git','-C',str(GIT),'status','--porcelain','--untracked-files=no']).strip()
 assert not E.exists() and not W.exists() and not E.is_symlink() and not W.is_symlink()
 # Protect both shared immutable donors and the fresh destination from active binds.
 for cid in command(['sudo','-n','docker','ps','-q','--no-trunc']).decode().splitlines():
  v=json.loads(command(['sudo','-n','docker','inspect',cid]))[0]
  for mount in v.get('Mounts',[]):
   if mount.get('Type')!='bind':continue
   if v['Id']=='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a' and mount['Source']=='/' and mount['RW'] is False:continue
   p=Path(mount['Source']).resolve();assert not any(p==q or p.is_relative_to(q) or q.is_relative_to(p) for q in (DONOR,W,CACHE))
 s=os.statvfs(B);assert s.f_bavail*s.f_frsize-224*1024**2>=s.f_blocks*s.f_frsize*.15
 E.mkdir();SOURCE.mkdir(parents=True);records=[];sources={};written=0;linked=0
 listing=command(['git','-C',str(GIT),'ls-tree','-r','-z','--full-tree',RELEASE,'--','client','server','protocol'])
 for item in listing.split(b'\0'):
  if not item:continue
  meta,name=item.split(b'\t',1);mode,kind,oid=meta.decode().split();name=name.decode();assert kind=='blob' and mode in ('100644','100755') and not '.godot' in Path(name).parts
  if name.startswith('server/') and any(part in ('bin','obj','.migration-archive') for part in Path(name).parts):continue
  old=DONOR/name;target=SOURCE/name;target.parent.mkdir(parents=True,exist_ok=True);digest=None
  if old.is_file() and not old.is_symlink():
   size=old.stat().st_size;h=hashlib.sha1(b'blob '+str(size).encode()+b'\0');d=hashlib.sha256()
   with old.open('rb') as f:
    for data in iter(lambda:f.read(65536),b''):h.update(data);d.update(data)
   if h.hexdigest()==oid:
    os.link(old,target);linked+=1
    digest=d.hexdigest()
  if digest is None:
   size=int(command(['git','-C',str(GIT),'cat-file','-s',oid]));assert size<=16*1024**2 and written+size<=64*1024**2
   body=command(['git','-C',str(GIT),'cat-file','blob',oid]);assert len(body)==size and hashlib.sha1(b'blob '+str(size).encode()+b'\0'+body).hexdigest()==oid
   with target.open('xb') as f:f.write(body)
   target.chmod(0o755 if mode=='100755' else 0o644);digest=hashlib.sha256(body).hexdigest();written+=size
  assert sha(target)==digest;sources[name]=digest;records.append({'path':name,'bytes':target.stat().st_size,'sha256':digest,'git_blob_sha1':oid})
 derived={}
 for p in sorted((DONOR/'client/.godot').rglob('*')):
  assert not p.is_symlink()
  if p.is_file():
   name=p.relative_to(DONOR).as_posix();target=SOURCE/name;target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target);derived[name]=sha(p);sources[name]=derived[name]
 assert len(derived)==1246 and {'client/network/gateway.gd','server/tests/FantasyCard.Server.Tests/Realtime/MonsterPoolLegalRouteWireTests.cs','client/tests/run_monster_pool_legal_route_vectors.gd','client/tests/test_monster_pool_legal_route_vectors.gd'}<=set(sources)
 for name in ('runner.py','inner.py'):shutil.copyfile(BOOT/name,E/name)
 cache_manifest=json.loads((B/'evidence/nuget-cache-delivery-r1/delivery-manifest.json').read_bytes());packages={r['path'].removeprefix('cache/nuget/'):r['sha256'] for r in cache_manifest['files'] if r['path'].startswith('cache/nuget/')};assert len(packages)==1157 and all(sha(CACHE/n)==h for n,h in packages.items())
 inputs={'attempt':A,'release_sha':RELEASE,'source_files':sources,'current_Git_source_records':records,'current_client_server_protocol_Git_bytes_verified':True,'reused_derived_cache_not_Git_source':derived,'source_directory':str(SOURCE),'package_root':str(CACHE),'packages':packages,'runner_sha256':sha(E/'runner.py'),'inner_sha256':sha(E/'inner.py'),'B08_G_receipt_sha256':sha(prev/'local-backup-receipt.json'),'B08_cleanup_sha256':sha(prev/'local-storage-cleanup.json'),'Nuget_restoration_sha256':sha(restoration_path),'server_generated_bin_obj_excluded':True,'entire_source_container_mount_readonly':True,'build_artifacts_separate_owned_directory':True,'hardlinked_unchanged_client_files':linked,'new_source_bytes':written,'expected_fixtures':9,'expected_original_Godot_commands':63,'expected_native_routes':99,'expected_native_event_rows':72,'MAIN_accepted':False,'LIVE_accepted':False}
 write(E/'inputs.json',inputs);write(E/'preparation-result.json',{'ok':True,'source_files':len(sources),'release_sha':RELEASE,'new_source_bytes':written,'native_started':False})
 # The admission is explicit and last; all checks precede the future execv.
 hold=json.loads(HOLD.read_bytes());assert hold['owner']=='pr13-cap-b09-legal-route-r2-20261011' and hold['active'] is True
 write(BOOT/'previous-lifecycle-hold.original.json',hold);hold.update(owner=OWNER,previous_owner=hold['owner'],reason='Explicit bounded B09 original-wire native/Godot validation',B08_G_verified_and_cleaned=True)
 temp=HOLD.with_name('scheduling-hold-B09-legal-route.tmp');write(temp,hold);os.replace(temp,HOLD)
 write(BOOT/'admission.json',{'attempt':A,'explicit_root_admission':True,'release_sha':RELEASE,'runner_sha256':sha(E/'runner.py'),'inputs_sha256':sha(E/'inputs.json'),'B08_full_G_backup_and_cleanup_verified':True,'cap_previous_original_G_closed':True,'full_Nuget_G_cache_restored_verified':True,'at':time.time(),'MAIN_accepted':False})
print(json.dumps({'ok':True,'attempt':A,'release_sha':RELEASE,'source_files':len(sources),'inputs_sha256':sha(E/'inputs.json'),'explicit_root_admission_written':True}))
