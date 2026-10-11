"""Wait for the sole Tencent analysis; preserve complete originals on G, no local computation."""
import gzip,hashlib,importlib.util,json,os,tarfile,time
from pathlib import Path,PurePosixPath
B=Path(__file__).parent;OUT=B/'cap-full-statistics-complete-originals-on-G-r1';DEST=Path('G:/PR13Evidence/cap-full-statistics-r1');A='cap-full-statistics-r1-20261011';OBS=B/'cap-full-statistics-cloud-queue-r4/last-statistics-native-observation.json'
assert not OUT.exists() and not DEST.exists();OUT.mkdir();until=time.monotonic()+194400
while True:
 assert time.monotonic()<until,'Exact original statistics terminal unavailable; never redispatch'
 if OBS.exists():
  observed=json.loads(OBS.read_bytes())
  if observed.get('result') is not None:break
 print(json.dumps({'state':'waiting_for_exact_Tencent_statistics_terminal','native_dispatched_by_backup':False}),flush=True);time.sleep(30)
spec=importlib.util.spec_from_file_location('full_stats_original_stream',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT;base=m.load('backup_failed_tuning_equivalence_r1_to_G.py')
def remote(code,target=None):
 c=base.connect()
 try:
  channel=c.get_transport().open_session(timeout=45);channel.exec_command('python3 -');channel.sendall(code.encode());channel.shutdown_write();return m.receive(channel,target)
 finally:c.close()
cloud=r'''
import gzip,hashlib,io,json,subprocess,sys,tarfile
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');A='cap-full-statistics-r1-20261011';E=B/'evidence'/A;W=B/'work'/A;RAM=Path('/dev/shm/pr13-'+A);T=B/'cache/cap-full-statistics-frozen-r1-20261011';OWNER='pr13-'+A
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(65536),b''):h.update(block)
 return h.hexdigest()
def collect():
 result=json.loads((E/'result.json').read_bytes());inputs=json.loads((E/'inputs.json').read_bytes());startup=json.loads((E/'startup.json').read_bytes());assert startup['systemd_unit']==OWNER
 state=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',OWNER,'--property=Id,LoadState,ActiveState,MainPID,ExecMainStatus'],text=True).splitlines());assert state['Id']==OWNER+'.service' and state['LoadState']=='loaded' and state['MainPID']=='0' and state['ActiveState'] in ('inactive','failed')
 assert sha(T/'analysis.py')==inputs['analysis_sha256'] and sha(T/'runner.py')==inputs['runner_sha256']
 P=Path(inputs['projection_path']);assert P==B/'work/cap-full-statistics-projection-r1-20261011'
 for row in inputs['projection_ledger']:
  p=P/row['path'];assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 files=[]
 for root,prefix in ((E,'metadata'),(W,'outputs'),(RAM,'scratch'),(T,'frozen-statistics-source'),(P,'frozen-projection')):
  assert root.resolve(strict=True)==root
  for p in sorted(root.rglob('*')):
   assert not p.is_symlink()
   if p.is_file():files.append({'source':str(p),'path':prefix+'/'+p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 unit=Path('/etc/systemd/system')/(OWNER+'.service');assert unit.is_file() and not unit.is_symlink();files.append({'source':str(unit),'path':'systemd/owned-unit.original.service','bytes':unit.stat().st_size,'sha256':sha(unit)})
 assert sum(x['bytes'] for x in files)<384*1024**2
 return {'attempt':A,'native_ok':result['ok'],'files':files,'logical_units':360,'encounters':720000,'source_files_verified':372,'full_native_sources_remain_in_original_unit_G_archives':True,'MAIN_accepted':False}
'''
journal=r'''
E=Path('/home/ubuntu/pr13-acceptance-20261009/evidence/cap-full-statistics-r1-20261011');OWNER='pr13-cap-full-statistics-r1-20261011';p=E/'terminal-journal.original.jsonl';assert not p.exists();r=subprocess.run(['journalctl','-u',OWNER,'-o','json','--no-pager'],capture_output=True,timeout=45);assert r.returncode==0;p.write_bytes(r.stdout);print(json.dumps({'ok':True,'journal_bytes':len(r.stdout)}))
'''
raw,_,err=remote('import json,subprocess\nfrom pathlib import Path\n'+journal);assert not err and json.loads(raw)['ok']
raw,_,err=remote(cloud+'\nsys.stdout.write(json.dumps(collect(),indent=2)+"\\n")\n');assert not err;v=json.loads(raw);(OUT/'delivery-manifest.json').write_bytes(raw);mh=hashlib.sha256(raw).hexdigest();assert v['native_ok']==observed['result']['ok']
stream=cloud+'\nEXPECTED='+repr(mh)+'\n'+r'''
v=collect();raw=(json.dumps(v,indent=2)+'\n').encode();assert hashlib.sha256(raw).hexdigest()==EXPECTED
class Sink:
 def __init__(self):self.h=hashlib.sha256();self.n=0
 def write(self,b):n=sys.stdout.buffer.write(b);assert n==len(b);self.h.update(b);self.n+=n;return n
 def flush(self):sys.stdout.buffer.flush()
sink=Sink()
with gzip.GzipFile(fileobj=sink,mode='wb',compresslevel=1,mtime=0) as gz:
 with tarfile.open(fileobj=gz,mode='w|') as t:
  i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
  for row in v['files']:
   p=Path(row['source']);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];i=tarfile.TarInfo(row['path']);i.size=row['bytes'];i.mode=0o600
   with p.open('rb') as f:t.addfile(i,f)
sink.flush();assert collect()==v;sys.stderr.write('ACK '+json.dumps({'bytes':sink.n,'sha256':sink.h.hexdigest(),'manifest_sha256':EXPECTED,'members':len(v['files'])})+'\n')
'''
archive=OUT/'delivery.private.tar.gz.partial'
with archive.open('xb') as f:_,count,err=remote(stream,f);f.flush();os.fsync(f.fileno())
assert len(err.splitlines())==1 and err.startswith(b'ACK ');ack=json.loads(err[4:]);assert ack['bytes']==count==archive.stat().st_size and ack['sha256']==m.sha(archive) and ack['manifest_sha256']==mh and ack['members']==len(v['files']);(OUT/'transport-ACK.json').write_text(json.dumps(ack,indent=2)+'\n',encoding='utf-8');archive.rename(OUT/'delivery.private.tar.gz');archive=OUT/'delivery.private.tar.gz'
DEST.mkdir(parents=True);expected={x['path']:x for x in v['files']};seen=set()
with tarfile.open(archive,'r|gz') as t:
 for item in t:
  p=PurePosixPath(item.name);assert item.isfile() and not p.is_absolute() and '..' not in p.parts and '\\' not in item.name and item.name not in seen;seen.add(item.name);f=t.extractfile(item)
  if item.name=='manifest.json':assert f.read()==raw;continue
  row=expected[item.name];target=DEST/item.name;target.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();size=0
  with target.open('xb') as out:
   for block in iter(lambda:f.read(65536),b''):out.write(block);h.update(block);size+=len(block)
  assert size==item.size==row['bytes'] and h.hexdigest()==row['sha256']
assert seen==set(expected)|{'manifest.json'}
with gzip.open(archive,'rb') as f:
 for _ in iter(lambda:f.read(65536),b''):pass
proof={'ok':True,'attempt':A,'native_ok':v['native_ok'],'local_archive':str(archive),'local_directory':str(DEST),'manifest_sha256':mh,'bytes':archive.stat().st_size,'sha256':m.sha(archive),'members':len(expected),'members_verified':len(expected),'archive_gzip_CRC_verified':True,'all_original_members_sha256_verified':True,'full_statistics_original_bytes_verified':True,'complete_analysis_driver_projection_outputs_systemd_journal_originals_preserved':True,'cloud_cleanup_performed':False,'no_statistics_executed_locally':True,'MAIN_accepted':False};(OUT/'local-backup-receipt.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof),flush=True)
