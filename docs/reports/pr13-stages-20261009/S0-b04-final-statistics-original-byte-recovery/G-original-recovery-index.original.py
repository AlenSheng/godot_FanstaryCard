"""G-side bytes/CRC/JSON identity only; never computes experiment statistics."""
import gzip,hashlib,json
from pathlib import Path

BASE=Path(__file__).parent;G=Path('G:/PR13Evidence/B04-single-factor-full-r1');OUT=BASE/'B04-full-final-original-recovery-index-r1';TARGET='/home/ubuntu/pr13-acceptance-20261009/evidence/B04-full-final-original-inputs-r1-20261013'
NATIVE_FILES=['manifest.original.json','summary.original.json','encounters.original.jsonl.gz','independent-part-validation.original.json']
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def prepare():
 require(not OUT.exists(),'Original recovery index already exists');complete=G/'full-native-and-G-complete.original.json';require(complete.exists(),'Original full 216000 execution and G custody not complete');final=json.loads(complete.read_bytes());require(final['ok'] and final['original_G_parts']==5400 and final['actual_encounters']==216000,'Full original denominator differs');plan=json.loads((G/'common-frozen-inputs/plan.original.json').read_bytes());require(len(plan['units'])==5400 and plan['expected_encounters']==216000,'Original plan differs');parts=[];files=[];members=0;total=0
 for spec in plan['units']:
  root=G/'units'/spec['unit'];receipt=json.loads((root/'local-G-receipt.original.json').read_bytes());clean=json.loads((root/'cloud-cleanup.original.json').read_bytes());manifest=root/'complete-original-manifest.json';m=json.loads(manifest.read_bytes());require(receipt['ok'] and receipt['attempt']=='B04-single-factor-full-r1-20261013' and receipt['unit']==spec['unit'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified'] and not receipt['native_reexecuted_by_backup'] and clean['ok'] and clean['originals_G_complete'] and receipt['manifest_sha256']==sha(manifest)==clean['manifest_sha256'],'Original G custody or native parent differs');archive=G/'archives'/(spec['unit']+'.original.tar.gz');require(archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256'],'Original archive bytes differ')
  with gzip.open(archive,'rb') as f:
   while f.read(1024**2):pass
  by={r['path']:r for r in m['files']}
  for name in NATIVE_FILES:
   p=root/'outputs/native'/name;r=by['outputs/native/'+name];require(p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],'Original native analysis input differs');remote=TARGET+'/units/'+spec['unit']+'/'+name;files.append({'local_source':str(p),'remote_path':remote,'bytes':r['bytes'],'sha256':r['sha256'],'original_parent_manifest_sha256':receipt['manifest_sha256']});members+=1;total+=r['bytes']
  p=root/'local-G-receipt.original.json';files.append({'local_source':str(p),'remote_path':TARGET+'/units/'+spec['unit']+'/local-G-receipt.original.json','bytes':p.stat().st_size,'sha256':sha(p),'original_parent_manifest_sha256':receipt['manifest_sha256']});parts.append({'unit':spec['unit'],'directory':TARGET+'/units/'+spec['unit'],'source_G_original_directory':str(root),'original_G_archive_sha256':receipt['archive_sha256'],'original_manifest_sha256':receipt['manifest_sha256']})
 require(len(parts)==5400 and members==21600,'Complete original selected input count differs');OUT.mkdir();(OUT/'parts-index.original.json').write_bytes((json.dumps({'parts':parts,'no_original_native_resimulation':True},indent=2)+'\n').encode());proof={'ok':True,'formal_original_parts':5400,'formal_original_encounters':216000,'selected_native_original_files_rehashed':members,'selected_native_original_bytes':total,'all5400_original_archive_SHA_and_CRC_rechecked':True,'native_receipt_and_independent_result_parents_preserved':True,'copy_reference_not_derived_statistical_data':True,'local_operations':'byte SHA CRC immutable JSON identity only','target':TARGET,'files':files,'MAIN_accepted':False};(OUT/'recovery-input-ledger.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());return proof
if __name__=='__main__':
 p=prepare();print(json.dumps({k:v for k,v in p.items() if k!='files'}))
