"""Local G byte/JSON archive driver. All native and experimental validation stays on Tencent."""
import gzip,hashlib,importlib.util,json,os,shutil,sys,tarfile,time,traceback
from pathlib import Path,PurePosixPath
import strict_compressed_TCP_NODELAY_cloud_transport as transport
B=Path(__file__).parent;OUT=B/'T03-conditioned-full-r2-local-driver';DEST=Path('G:/PR13Evidence/T03-conditioned-full-r2')
CONTROLLER='/home/ubuntu/pr13-acceptance-20261009/evidence/T03-conditioned-full-r2-20261012/controller.original.py';ATTEMPT='T03-conditioned-full-r2-20261012'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def write(p,v):
 p=Path(p);assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def event(v):
 v={'at':time.time(),**v}
 with (OUT/'events.original.jsonl').open('a') as f:f.write(json.dumps(v)+'\n')
 print(json.dumps(v),flush=True)
spec=importlib.util.spec_from_file_location('receiver',B/'b08_lifecycle_r4_G_transport_gc_r2.py');receiver=importlib.util.module_from_spec(spec);spec.loader.exec_module(receiver)
def remote(action,*args,target=None):
 c=transport.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');code='import runpy,sys\nsys.argv='+repr([CONTROLLER,action,*args])+'\nrunpy.run_path(sys.argv[0],run_name="__main__")\n';data=code.encode()
  for i in range(0,len(data),512):ch.sendall(data[i:i+512]);time.sleep(.1)
  ch.shutdown_write();raw,count,err=receiver.receive(ch,target)
  if target is not None:return count,err
  assert not err;return json.loads(raw)
 finally:c.close()
def backup(name):
 packet=remote('delivery',name);assert packet['ok'];manifest=packet['manifest'];assert manifest['unit']==name and manifest['attempt']==ATTEMPT and manifest['witnesses']==8000
 root=DEST/'units'/name;archive=DEST/'archives'/(name+'.original.tar.gz');assert not root.exists() and not archive.exists();root.mkdir(parents=True)
 assert shutil.disk_usage(DEST).free>500000000+sum(r['bytes'] for r in manifest['files'])*2
 with archive.open('xb') as f:count,err=remote('stream',name,target=f);f.flush();os.fsync(f.fileno())
 assert err.startswith(b'ACK ') and len(err.splitlines())==1;ack=json.loads(err[4:]);assert count==archive.stat().st_size==ack['bytes'] and sha(archive)==ack['sha256'] and packet['manifest_sha256']==ack['manifest_sha256']
 rows={r['path']:r for r in manifest['files']};assert len(rows)==len(manifest['files']);seen=set()
 with tarfile.open(archive,'r:gz') as t:
  for item in t:
   path=PurePosixPath(item.name);assert item.isfile() and not path.is_absolute() and '..' not in path.parts and '\\' not in item.name and ':' not in item.name and item.name not in seen;seen.add(item.name);data=t.extractfile(item).read()
   if item.name=='complete-original-manifest.json':assert hashlib.sha256(data).hexdigest()==ack['manifest_sha256'] and json.loads(data)==manifest
   else:r=rows[item.name];assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
   p=root.joinpath(*path.parts);assert p.resolve().is_relative_to(root.resolve());p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 assert seen==set(rows)|{'complete-original-manifest.json'}
 with gzip.open(archive,'rb') as f:
  while f.read(65536):pass
 for r in rows.values():
  p=root/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
 # Metadata checks only: never run a .NET binary, validator or experiment locally.
 native=json.loads((root/'outputs/native/summary.original.json').read_bytes());validation=json.loads((root/'outputs/native/independent-validation.original.json').read_bytes());assert native['passed'] and native['samples']==1000 and native['witnesses']==8000 and validation['ok'] and validation['actual_witnesses']==8000
 receipt={'ok':True,'attempt':ATTEMPT,'unit':name,'local_directory':str(root),'archive_bytes':count,'archive_sha256':ack['sha256'],'manifest_sha256':ack['manifest_sha256'],'members':len(rows),'all_members_SHA_verified':True,'gzip_CRC_verified':True,'native_reexecuted_by_backup':False,'local_checks':'byte_hash_CRC_and_JSON_metadata_only','formal_EXPERIMENT_accepted':False,'MAIN_accepted':False};write(root/'local-G-receipt.original.json',receipt)
 cleaned=remote('cleanup',name,json.dumps(receipt));assert cleaned['ok'] and cleaned['originals_G_complete'];write(root/'cloud-cleanup.original.json',cleaned);event({'phase':'GVerifiedAndExactCloudOutputCleaned','unit':name,'witnesses':8000,'archive_bytes':count});return receipt
def main():
 assert not OUT.exists() and not DEST.exists();OUT.mkdir();DEST.mkdir();(DEST/'archives').mkdir();(DEST/'units').mkdir();receiver.OUT=OUT;write(OUT/'started.original.json',{'PID':os.getpid(),'attempt':ATTEMPT,'local_native_execution':False,'no_automatic_retry_on_uncertain_transport':True,'at':time.time()})
 init=json.loads((B/'T03-conditioned-full-r2-dispatch/cloud-initialization-result.original.json').read_bytes());plan=init['plan'];assert len(plan['units'])==360
 pilot_runtime=Path('G:/PR13Evidence/T03-conditioned-pilot-r1/native-artifacts-and-output/artifacts/bin/T03ConditionedRoomBoundary/release')
 for r in plan['runtime_files']:
  p=pilot_runtime/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
 for file in ('T03_conditioned_full_R2_controller.original.py','T03_conditioned_full_validator.original.py','T03_conditioned_full_R2_G_driver.original.py'):(DEST/file).write_bytes((B/file).read_bytes())
 write(DEST/'cloud-initialization-result.original.json',init);event({'phase':'Started','required_units':360,'required_witnesses':2880000})
 while True:
  st=remote('status');assert st['ok'];completed=st['completed_G_verified_units']
  if completed==360:
   final=remote('final');assert final['ok'];write(DEST/'full-native-complete.original.json',final);write(OUT/'full-native-complete.original.json',final);event({'phase':'Full360Complete','witnesses':2880000});return
  current=st['current']
  if current:
   name=current['spec']['unit'];state=current['state'];result=current['result']
   if result is not None:
    assert result['ok'],'Actual failed unit; retain originals and stop'
    if state['MainPID']=='0' and state['ActiveState']=='inactive' and state['ExecMainStatus']=='0':
     backup(name)
     if (completed+1)%120==0:write(OUT/('block-'+str((completed+1)//120-1)+'-G-complete.original.json'),{'ok':True,'completed_units':completed+1,'completed_witnesses':(completed+1)*8000,'formal_EXPERIMENT_accepted':False});event({'phase':'SeedBlockComplete','completed_units':completed+1})
     continue
   assert state['ActiveState'] in ('active','activating','deactivating'),'Native handle ended without proven success; do not restart'
   event({'phase':'ExactNativeHandleRunning','unit':name,'completed_G_units':completed});time.sleep(5);continue
  launched=remote('launch');assert launched['ok'];event({'phase':'LaunchDeferred' if launched.get('resource_deferred') else 'ExactUnitDispatched',**launched})
  time.sleep(10 if launched.get('resource_deferred') else 2)
if __name__=='__main__':
 try:main()
 except BaseException as e:
  if OUT.exists():
   p=OUT/'stopped.original.json'
   if not p.exists():write(p,{'ok':False,'error':type(e).__name__,'detail':str(e),'traceback':traceback.format_exc(),'same_handle_inspection_required':True,'no_native_restart':True,'at':time.time()})
  raise
