"""Only hashes, CRC and immutable JSON metadata locally; native study stays Tencent."""
import gzip,hashlib,importlib.util,json,os,shutil,tarfile,time,traceback
from pathlib import Path,PurePosixPath
import strict_compressed_TCP_NODELAY_cloud_transport as transport
B=Path(__file__).parent;OUT=B/'B04-single-factor-full-r1-local-driver';G=Path('G:/PR13Evidence/B04-single-factor-full-r1');C='/home/ubuntu/pr13-acceptance-20261009/evidence/B04-single-factor-full-r1-20261013/controller.original.py';A='B04-single-factor-full-r1-20261013'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def write(p,v):p=Path(p);assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def event(v):
 v={'at':time.time(),**v}
 with (OUT/'events.original.jsonl').open('a') as f:f.write(json.dumps(v)+'\n')
 print(json.dumps(v),flush=True)
spec=importlib.util.spec_from_file_location('receiver',B/'b08_lifecycle_r4_G_transport_gc_r2.py');receiver=importlib.util.module_from_spec(spec);spec.loader.exec_module(receiver)
def remote(action,*args,target=None):
 c=transport.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');data=('import runpy,sys\nsys.argv='+repr([C,action,*args])+'\nrunpy.run_path(sys.argv[0],run_name="__main__")\n').encode()
  for i in range(0,len(data),512):ch.sendall(data[i:i+512]);time.sleep(.1)
  ch.shutdown_write();raw,count,err=receiver.receive(ch,target)
  if target is not None:return count,err
  assert not err;return json.loads(raw)
 finally:c.close()
def backup(name):
 packet=remote('delivery',name);m=packet['manifest'];assert packet['ok'] and m['unit']==name and m['attempt']==A and m['encounters']==40;root=G/'units'/name;archive=G/'archives'/(name+'.original.tar.gz');assert not root.exists() and not archive.exists();root.mkdir();assert shutil.disk_usage(G).free>500000000+sum(r['bytes'] for r in m['files'])*2
 with archive.open('xb') as f:n,err=remote('stream',name,target=f);f.flush();os.fsync(f.fileno())
 assert err.startswith(b'ACK ') and len(err.splitlines())==1;ack=json.loads(err[4:]);assert n==archive.stat().st_size==ack['bytes'] and sha(archive)==ack['sha256'] and ack['manifest_sha256']==packet['manifest_sha256'];rows={r['path']:r for r in m['files']};seen=set()
 with tarfile.open(archive,'r:gz') as t:
  for item in t:
   p=PurePosixPath(item.name);assert item.isfile() and not p.is_absolute() and '..' not in p.parts and ':' not in item.name and '\\' not in item.name and item.name not in seen;seen.add(item.name);data=t.extractfile(item).read()
   if item.name=='complete-original-manifest.json':assert hashlib.sha256(data).hexdigest()==packet['manifest_sha256']
   else:r=rows[item.name];assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
   q=root.joinpath(*p.parts);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
 assert seen==set(rows)|{'complete-original-manifest.json'}
 with gzip.open(archive,'rb') as f:
  while f.read(65536):pass
 for r in rows.values():p=root/r['path'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
 v=json.loads((root/'outputs/native/independent-part-validation.original.json').read_bytes());assert v['ok'] and v['samples']==20 and v['encounters']==40;receipt={'ok':True,'attempt':A,'unit':name,'local_directory':str(root),'archive_bytes':n,'archive_sha256':ack['sha256'],'manifest_sha256':packet['manifest_sha256'],'members':len(rows),'all_members_SHA_verified':True,'gzip_CRC_verified':True,'native_reexecuted_by_backup':False,'local_checks':'byte hash CRC JSON metadata only','MAIN_accepted':False};write(root/'local-G-receipt.original.json',receipt);cleaned=remote('cleanup',name,json.dumps(receipt));assert cleaned['ok'] and cleaned['originals_G_complete'];write(root/'cloud-cleanup.original.json',cleaned);event({'phase':'GVerifiedAndExactCloudOutputCleaned','unit':name,'encounters':40,'archive_bytes':n})
def main():
 assert not OUT.exists() and not G.exists();OUT.mkdir();G.mkdir();(G/'archives').mkdir();(G/'units').mkdir();receiver.OUT=OUT;write(OUT/'started.original.json',{'PID':os.getpid(),'attempt':A,'native_execution_locally':False,'required_parts':5400,'required_encounters':216000,'wait_for_original_T03_full360':True,'at':time.time()});last_reason=None
 while True:
  st=remote('status');assert st['ok']
  if st['completed_G_verified_parts']==5400:
   v=remote('final');assert v['ok'];write(G/'full-native-and-G-complete.original.json',v);event({'phase':'FullOriginal216000NativeAndGComplete','final_independent_statistics_pending':True});return
  cur=st['current']
  if cur is not None:
   if cur['result'] is not None:
    assert cur['result']['ok'],'Actual failed native part; originals retained, no skipped seeds'
    if cur['state']['MainPID']=='0' and cur['state']['ActiveState']=='inactive' and cur['state']['ExecMainStatus']=='0':backup(cur['spec']['unit']);last_reason=None;continue
   event({'phase':'ExactNativeHandleRunning','unit':cur['spec']['unit'],'completed_G_parts':st['completed_G_verified_parts']});time.sleep(15);continue
  launched=remote('launch');assert launched['ok']
  if launched.get('resource_deferred'):
   reason=launched.get('reason','Resource admission hold')
   if reason!=last_reason:event({'phase':'LaunchDeferred','detail':launched});last_reason=reason
   time.sleep(30)
  else:event({'phase':'ExactPhysicalPartDispatched','detail':launched});last_reason=None
if __name__=='__main__':
 try:main()
 except Exception as error:
  if OUT.exists():write(OUT/'driver-failure.original.json',{'error':type(error).__name__,'detail':str(error),'traceback':traceback.format_exc(),'original_handles_and_partial_archives_preserved':True,'automatic_native_restart':False})
  raise
