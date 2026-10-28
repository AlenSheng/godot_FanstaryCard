import gzip,hashlib,importlib.util,json,os,tarfile,time
from pathlib import Path,PurePosixPath
B=Path(__file__).parent

watch=B/'current-missing-DB-CI-AUDIT-r1-scheduled/last-native-observation.json'
deadline=time.monotonic()+187200
while True:
 assert time.monotonic()<deadline
 if watch.exists():
  v=json.loads(watch.read_bytes())
  if v.get('result') is not None and v['state']['MainPID']=='0':break
 time.sleep(15)

OUT=B/'current-missing-DB-CI-AUDIT-r1-complete-originals-complete-G-delta';DEST=Path('G:/PR13Evidence/current-missing-DB-CI-AUDIT-r1-complete-originals');assert not OUT.exists() and not DEST.exists();OUT.mkdir();basepath=B/'current-PG-runtime25-r1-complete-originals-on-G';proof=json.loads((basepath/'local-backup-receipt.json').read_bytes());assert proof['ok'] and proof['all_original_members_SHA_verified'];base_manifest=json.loads((basepath/'delivery-manifest.json').read_bytes());known={(r['bytes'],r['sha256']):str(Path(proof['local_directory'])/r['path']) for r in base_manifest['files']};spec=importlib.util.spec_from_file_location('failed_PG_delta',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
cloud=r'''
import hashlib,json,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='current-missing-db-ci-audit-r1-20261012';E=B/'evidence'/A;W=B/'work'/A;D=B/'work/real-PG-TLS-framing-r2-inputs';RAM=Path('/dev/shm/pr13-'+A);meta=json.loads((E/'inputs.original.json').read_bytes())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
def collect():
 result=json.loads((E/'run-result.json').read_bytes());state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show','pr13-cap-'+A,'--property=MainPID,ActiveState'],text=True).splitlines());assert state['MainPID']=='0' and state['ActiveState'] in ('inactive','failed') and result['owned_containers_removed'];journal=E/'terminal-journal.original.jsonl'
 if not journal.exists():journal.write_bytes(subprocess.check_output(['journalctl','--unit=pr13-cap-'+A,'--no-pager','--output=json']))
 files=[]
 for root,prefix in ((E,'metadata'),(W,'native-build'),(Path(meta['source']),'frozen-source'),(Path(meta['package_root']),'frozen-packages'),(Path(meta['supplemental_package_root']),'frozen-supplemental-packages')):
  assert root.exists() and not root.is_symlink()
  for p in sorted(root.rglob('*')):
   assert not p.is_symlink()
   if p.is_file():files.append({'source':str(p),'path':prefix+'/'+p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 assert sum(r['bytes'] for r in files)<512*1024**2
 return {'native_ok':result['ok'],'original_failed_outputs_retained':True,'files':files,'MAIN_accepted':False}
'''
def remote(code,target=None):
 c=base.connect()
 try:
  ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');raw=code.encode()
  for i in range(0,len(raw),512):ch.sendall(raw[i:i+512]);time.sleep(.1)
  ch.shutdown_write();return m.receive(ch,target)
 finally:c.close()
raw,_,err=remote(cloud+'\nprint(json.dumps(collect(),indent=2))\n');assert not err;v=json.loads(raw);refs=[];transfers=[]
for row in v['files']:
 p=known.get((row['bytes'],row['sha256']))
 if p:
  path=Path('\\\\?\\'+str(Path(p).resolve()));assert path.stat().st_size==row['bytes'] and m.sha(path)==row['sha256'];refs.append({**row,'verified_existing_G_path':p})
 else:transfers.append(row)
manifest={**v,'transferred_members':transfers,'verified_existing_G_members':refs,'original_base_G_receipt':proof};manifest_raw=(json.dumps(manifest,indent=2)+'\n').encode();(OUT/'complete-logical-delivery-manifest.json').write_bytes(manifest_raw);selected={r['path'] for r in transfers};expected=hashlib.sha256(raw).hexdigest();code=cloud+'\nEXPECTED='+repr(expected)+'\nSELECTED='+repr(selected)+'\n'+r'''
import gzip,io,sys,tarfile
v=collect();raw=(json.dumps(v,indent=2)+'\n').encode();assert hashlib.sha256(raw).hexdigest()==EXPECTED
class Sink:
 def __init__(self):self.h=hashlib.sha256();self.n=0
 def write(self,b):n=sys.stdout.buffer.write(b);assert n==len(b);self.n+=n;self.h.update(b);return n
 def flush(self):sys.stdout.buffer.flush()
sink=Sink()
with gzip.GzipFile(fileobj=sink,mode='wb',mtime=0,compresslevel=1) as gz:
 with tarfile.open(fileobj=gz,mode='w|') as t:
  i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
  for row in v['files']:
   if row['path'] not in SELECTED:continue
   p=Path(row['source']);assert sha(p)==row['sha256'];i=tarfile.TarInfo(row['path']);i.size=row['bytes']
   with p.open('rb') as f:t.addfile(i,f)
sink.flush();assert collect()==v;sys.stderr.write('ACK '+json.dumps({'bytes':sink.n,'sha256':sink.h.hexdigest(),'manifest_sha256':EXPECTED})+'\n')
'''
archive=OUT/'delivery.delta.private.tar.gz'
with archive.open('xb') as f:_,count,err=remote(code,f);f.flush();os.fsync(f.fileno())
assert err.startswith(b'ACK ') and len(err.splitlines())==1;ack=json.loads(err[4:]);assert ack['bytes']==count==archive.stat().st_size and ack['sha256']==m.sha(archive) and ack['manifest_sha256']==expected;DEST.mkdir();rows={r['path']:r for r in transfers};seen=set()
with tarfile.open(archive,'r|gz') as t:
 for item in t:
  p=PurePosixPath(item.name);assert item.isfile() and not p.is_absolute() and '..' not in p.parts and item.name not in seen;seen.add(item.name);f=t.extractfile(item)
  if item.name=='manifest.json':assert f.read()==raw;continue
  row=rows[item.name];target=Path('\\\\?\\'+str((DEST/item.name).resolve()));assert target.resolve().is_relative_to(Path('\\\\?\\'+str(DEST.resolve())));target.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();n=0
  with target.open('xb') as out:
   for b in iter(lambda:f.read(65536),b''):out.write(b);h.update(b);n+=len(b)
  assert n==item.size==row['bytes'] and h.hexdigest()==row['sha256']
assert seen==set(rows)|{'manifest.json'}
with gzip.open(archive,'rb') as f:
 for _ in iter(lambda:f.read(65536),b''):pass
receipt={'ok':True,'native_ok':v['native_ok'],'local_directory':str(DEST),'archive_bytes':archive.stat().st_size,'archive_sha256':m.sha(archive),'archive_gzip_CRC_verified':True,'logical_original_members_verified':len(v['files']),'existing_G_members_rehashed':len(refs),'changed_members_transferred':len(transfers),'complete_logical_manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'failed_cloud_outputs_kept':True,'cloud_cleanup_performed':False,'MAIN_accepted':False};(OUT/'local-backup-receipt.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode());print(json.dumps(receipt))
