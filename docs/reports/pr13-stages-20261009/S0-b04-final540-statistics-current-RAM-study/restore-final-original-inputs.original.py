"""Restore selected original bytes for final Tencent analysis, with full SHA custody."""
import base64,gzip,hashlib,importlib.util,json,time
from pathlib import Path
import strict_compressed_TCP_NODELAY_cloud_transport as transport

B=Path(__file__).parent;D=B/'B04-reduced-final-original-recovery-index-r2';OUT=B/'B04-reduced-final-original-inputs-cloud-restoration-r2';TARGET='/home/ubuntu/pr13-acceptance-20261009/evidence/B04-reduced-final-original-inputs-r1-20261014'
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 require(D.exists() and not OUT.exists(),'Complete original recovery index required and no duplicate restoration');ledger=json.loads((D/'recovery-input-ledger.original.json').read_bytes());require(ledger['ok'] and ledger['formal_original_parts']==540 and ledger['formal_original_encounters']==21600 and ledger['all540_original_archive_SHA_and_CRC_rechecked'] and ledger['target']==TARGET,'Original full custody differs');files=ledger['files'];require(len(files)==2700,'All original native fields and receipts required')
 for r in files:
  p=Path(r['local_source']);require(p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],'G original input changed after preparation');require(r['remote_path'].startswith(TARGET+'/units/') and '..' not in Path(r['remote_path']).parts,'Restoration target escapes exact owner')
 OUT.mkdir();spec=importlib.util.spec_from_file_location('receiver',B/'b08_lifecycle_r4_G_transport_gc_r2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.OUT=OUT
 def remote(code):
  c=transport.connect()
  try:
   ch=c.get_transport().open_session(timeout=45);ch.exec_command('sudo -n python3 -');data=code.encode()
   for i in range(0,len(data),4096):ch.sendall(data[i:i+4096]);time.sleep(.02)
   ch.shutdown_write();raw,_,err=m.receive(ch);require(not err,'Original restoration diagnostics');return json.loads(raw)
  finally:c.close()
 start='import json,os\nfrom pathlib import Path\np=Path('+repr(TARGET)+');assert p.parent==Path("/home/ubuntu/pr13-acceptance-20261009/evidence") and not p.exists();s=os.statvfs("/");assert s.f_bavail*s.f_frsize>=.15*s.f_blocks*s.f_frsize+'+str(sum(r['bytes'] for r in files)+16*1024**2)+';p.mkdir();(p/"units").mkdir();print(json.dumps({"ok":True,"target":str(p),"exact_original_files":2700}))\n';v=remote(start);require(v['ok'],'Exact owned restore root not created');(OUT/'started.original.json').write_bytes((json.dumps(v,indent=2)+'\n').encode());copied=[]
 # Batch original bytes only; no rows are parsed or recomputed locally.
 for offset in range(0,len(files),100):
  batch=files[offset:offset+100];payload=[]
  for r in batch:
   data=Path(r['local_source']).read_bytes();payload.append({'path':r['remote_path'],'bytes':r['bytes'],'sha256':r['sha256'],'base64':base64.b64encode(data).decode()})
  packed=base64.b64encode(gzip.compress(json.dumps(payload,separators=(',',':')).encode(),compresslevel=1,mtime=0)).decode()
  code='PAYLOAD='+repr(packed)+'\n'+r'''
import base64,gzip,hashlib,json,os
from pathlib import Path
root=Path('/home/ubuntu/pr13-acceptance-20261009/evidence/B04-reduced-final-original-inputs-r1-20261014');rows=json.loads(gzip.decompress(base64.b64decode(PAYLOAD)));restored=[]
for r in rows:
 p=Path(r['path']);assert p.is_relative_to(root/'units') and not p.exists();data=base64.b64decode(r['base64']);assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'];s=os.statvfs('/');assert s.f_bavail/s.f_blocks>=.15;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);assert p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];restored.append({'path':str(p),'bytes':r['bytes'],'sha256':r['sha256']})
print(json.dumps({'ok':True,'original_files_restored':len(restored),'files':restored}))
'''
  result=remote(code);require(result['ok'] and result['original_files_restored']==len(batch),'Exact original byte batch not confirmed');copied.extend(result['files'])
  with (OUT/'restored-progress.original.jsonl').open('a') as f:f.write(json.dumps({'original_files_restored':offset+len(batch),'last_original_path':batch[-1]['remote_path']})+'\n')
 index_bytes=(D/'parts-index.original.json').read_bytes();packed=base64.b64encode(gzip.compress(index_bytes,compresslevel=1,mtime=0)).decode();v=remote('import base64,gzip,hashlib,json\nfrom pathlib import Path\ndata=gzip.decompress(base64.b64decode('+repr(packed)+'));assert hashlib.sha256(data).hexdigest()=='+repr(hashlib.sha256(index_bytes).hexdigest())+';p=Path('+repr(TARGET+'/parts-index.original.json')+');assert not p.exists();p.write_bytes(data);print(json.dumps({"ok":True,"sha256":hashlib.sha256(data).hexdigest()}))\n');require(v['ok'],'Exact full parts index restoration failed');proof={'ok':True,'original_files_restored':2700,'original_parts':540,'original_encounters':21600,'all_selected_inputs_restored_byte_exact':True,'original_raw_files_not_statistically_derived_or_resimulated':True,'original_source_ledger_sha256':sha(D/'recovery-input-ledger.original.json'),'restored_parts_index_sha256':v['sha256'],'restored_target':TARGET,'native_statistics_not_executed_by_restoration':True,'MAIN_accepted':False};(OUT/'complete-original-restoration-receipt.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
if __name__=='__main__':main()
