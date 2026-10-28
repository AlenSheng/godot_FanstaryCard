"""Whole original G archive from exact existing G bytes and missing cloud bytes."""
import gzip,hashlib,importlib.util,io,json,os,shutil,sys,tarfile
from pathlib import Path,PurePosixPath
B=Path(__file__).parent;sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('original_B08_transport',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
OUT=B/'b08-lifecycle-r4-backup-on-G-r3';ASSEMBLY=Path('G:/PR13Evidence/b08-lifecycle-r4-assembly-r3');DEST=Path('G:/PR13Evidence/b08-lifecycle-r4-r3')
assert not OUT.exists() and not ASSEMBLY.exists() and not DEST.exists();OUT.mkdir();ASSEMBLY.mkdir(parents=True)
coverage=json.loads((B/'b08-r4-local-byte-reuse-coverage.json').read_bytes());prior=B/'b08-lifecycle-r4-backup-on-G-r2';raw=(prior/'delivery-manifest.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==coverage['manifest_sha256']=='de1001db5432275f84f65092c32dc99b81593ee30d98706d1e5df6e60e6d892d';manifest=json.loads(raw);rows={r['path']:r for r in manifest['files']};assert len(rows)==3397
assert len(coverage['matched'])==3349 and len(coverage['missing'])==48 and set(x['path'] for x in coverage['matched'])|set(x['path'] for x in coverage['missing'])==set(rows)
(OUT/'delivery-manifest.json').write_bytes(raw)
interrupted=prior/'delivery.private.tar.gz.partial';assert interrupted.is_file()
(OUT/'prior-interrupted-stream-receipt.json').write_text(json.dumps({'native_or_cloud_test_stopped':False,'incomplete_stream_retained':str(interrupted),'bytes':interrupted.stat().st_size,'sha256':m.sha(interrupted),'replacement_missing_cloud_members':48,'MAIN_accepted':False},indent=2)+'\n')
def target(name):
 parts=PurePosixPath(name);assert not parts.is_absolute() and '..' not in parts.parts and '\\' not in name;p=ASSEMBLY/name;assert p.resolve().is_relative_to(ASSEMBLY.resolve());p.parent.mkdir(parents=True,exist_ok=True);return p
for row in coverage['matched']:
 src=Path(row['local_source']);assert src.drive.upper()=='G:' and src.is_file() and not src.is_symlink();p=target(row['path']);expected=rows[row['path']]
 if row.get('CRLF_to_LF_only'):
  body=src.read_bytes().replace(b'\r\n',b'\n');assert len(body)==expected['bytes'] and hashlib.sha256(body).hexdigest()==expected['sha256'];p.write_bytes(body)
 else:
  assert src.stat().st_size==expected['bytes'] and m.sha(src)==expected['sha256'];shutil.copyfile(src,p)
 assert p.stat().st_size==expected['bytes'] and m.sha(p)==expected['sha256']
print(json.dumps({'state':'existing_G_members_copied_and_exact_SHA_verified','members':3349,'bytes':coverage['matched_bytes'],'missing_cloud_members':48,'native_executed':False}),flush=True)
base=m.load('backup_failed_tuning_equivalence_r1_to_G.py');c=base.connect();missing=[x['path'] for x in coverage['missing']]
code=m.CLOUD+'\nEXPECTED='+repr(coverage['manifest_sha256'])+'\nSELECTED='+repr(missing)+'\n'+r'''
raw,v=checked();assert hashlib.sha256(raw).hexdigest()==EXPECTED
by_path={r['path']:r for r in v['files']};assert len(SELECTED)==48 and len(set(SELECTED))==48 and all(k in by_path for k in SELECTED)
class Sink:
 def __init__(self):self.count=0;self.h=hashlib.sha256()
 def write(self,b):
  n=sys.stdout.buffer.write(b);assert n==len(b);self.count+=n;self.h.update(b);return n
 def flush(self):sys.stdout.buffer.flush()
sink=Sink()
with gzip.GzipFile(fileobj=sink,mode='wb',compresslevel=1,mtime=0) as zipped:
 with tarfile.open(fileobj=zipped,mode='w|') as tar:
  for k in SELECTED:
   r=by_path[k];p=Path(r['source']);assert p.stat().st_size==r['bytes'] and m.sha(p)==r['sha256'];info=tarfile.TarInfo(k);info.size=r['bytes'];info.mode=0o600
   with p.open('rb') as f:tar.addfile(info,f)
sink.flush();after,_=checked();assert after==raw
ack={'attempt':A,'manifest_sha256':EXPECTED,'selected_members':len(SELECTED),'selected_original_source_bytes':sum(by_path[k]['bytes'] for k in SELECTED),'archive_bytes':sink.count,'archive_sha256':sink.h.hexdigest(),'gzip_footer_closed':True,'all_original_sources_revalidated':True,'native_reexecuted':False}
sys.stderr.write('PR13_B08_R4_SELECTED_STREAM_ACK '+json.dumps(ack)+'\n');sys.stderr.flush()
'''
try:
 partial=OUT/'missing-originals.private.tar.gz.partial'
 with partial.open('xb') as f:_,count,err=m.receive(base.session(c,code),f);f.flush();os.fsync(f.fileno())
 lines=err.splitlines();prefix=b'PR13_B08_R4_SELECTED_STREAM_ACK ';assert len(lines)==1 and lines[0].startswith(prefix);ack=json.loads(lines[0][len(prefix):]);assert ack['manifest_sha256']==coverage['manifest_sha256'] and ack['selected_members']==48 and ack['archive_bytes']==count==partial.stat().st_size and ack['archive_sha256']==m.sha(partial) and ack['all_original_sources_revalidated'] and ack['gzip_footer_closed'];partial.rename(OUT/'missing-originals.private.tar.gz')
finally:c.close()
seen=set()
with tarfile.open(OUT/'missing-originals.private.tar.gz','r|gz') as t:
 for item in t:
  assert item.isfile() and item.name in missing and item.name not in seen;seen.add(item.name);p=target(item.name);assert not p.exists();expected=rows[item.name];f=t.extractfile(item);h=hashlib.sha256();count=0
  with p.open('xb') as out:
   for block in iter(lambda:f.read(65536),b''):out.write(block);h.update(block);count+=len(block)
  assert count==expected['bytes']==item.size and h.hexdigest()==expected['sha256']
assert seen==set(missing)
with gzip.open(OUT/'missing-originals.private.tar.gz','rb') as f:
 for _ in iter(lambda:f.read(65536),b''):pass
whole=OUT/'delivery.private.tar.gz'
with whole.open('xb') as sink:
 with gzip.GzipFile(fileobj=sink,mode='wb',compresslevel=1,mtime=0) as zipped:
  with tarfile.open(fileobj=zipped,mode='w|') as t:
   info=tarfile.TarInfo('manifest.json');info.size=len(raw);t.addfile(info,io.BytesIO(raw))
   for row in manifest['files']:
    p=ASSEMBLY/row['path'];assert p.stat().st_size==row['bytes'] and m.sha(p)==row['sha256'];info=tarfile.TarInfo(row['path']);info.size=row['bytes'];info.mode=0o600
    with p.open('rb') as f:t.addfile(info,f)
transport={'ok':True,'attempt':m.A,'manifest_sha256':coverage['manifest_sha256'],'members':3397,'source_bytes':sum(x['bytes'] for x in manifest['files']),'local_archive':str(whole),'bytes':whole.stat().st_size,'sha256':m.sha(whole),'transfer_mode':'whole_archive_assembled_on_G_from_exact_existing_bytes_and_missing_cloud_originals','existing_G_members_verified':3349,'cloud_selected_members_verified':48,'remote_selected_completion_ack':ack,'all_source_bytes_match_original_cloud_manifest':True,'native_reexecuted':False,'MAIN_accepted':False};(OUT/'transport-receipt.json').write_text(json.dumps(transport,indent=2)+'\n')
m.OUT=OUT;m.DEST=DEST;proof=m.verify();assert proof['members_verified']==3397
print(json.dumps({'ok':True,'complete_archive':str(whole),'members_verified':3397,'native_reexecuted':False,'prior_partial_retained':True}),flush=True)
