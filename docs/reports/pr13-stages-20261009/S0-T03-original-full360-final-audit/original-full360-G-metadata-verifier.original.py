"""Verify byte/Git/CRC/JSON provenance only; no local native or statistical execution."""
import gzip,hashlib,json
from pathlib import Path
B=Path(__file__).parent;G=Path('G:/PR13Evidence/T03-conditioned-full-r2');OUT=B/'T03-conditioned-full360-G-independent-check';assert not OUT.exists();OUT.mkdir();init=json.loads((G/'cloud-initialization-result.original.json').read_bytes());plan=init['plan'];units=plan['units'];assert len(units)==360 and {s['block'] for s in units}=={0,1,2}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
rows=[];members=0;bytes_checked=0
for spec in units:
 root=G/'units'/spec['unit'];receipt=json.loads((root/'local-G-receipt.original.json').read_bytes());cleanup=json.loads((root/'cloud-cleanup.original.json').read_bytes());assert receipt['ok'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified'] and receipt['unit']==spec['unit'] and not receipt['native_reexecuted_by_backup'];assert cleanup['ok'] and cleanup['originals_G_complete'] and cleanup['manifest_sha256']==receipt['manifest_sha256'];m=root/'complete-original-manifest.json';assert sha(m)==receipt['manifest_sha256'];manifest=json.loads(m.read_bytes());assert manifest['unit']==spec['unit'] and manifest['witnesses']==8000
 for row in manifest['files']:
  p=root/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];members+=1;bytes_checked+=row['bytes']
 archive=G/'archives'/(spec['unit']+'.original.tar.gz');assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
 with gzip.open(archive,'rb') as f:
  while f.read(65536):pass
 native=json.loads((root/'outputs/native/summary.original.json').read_bytes());validation=json.loads((root/'outputs/native/independent-validation.original.json').read_bytes());result=json.loads((root/'metadata/result.original.json').read_bytes());assert result['ok'] and not result['oom_killed'] and result['owned_container_removed'] and result['source_and_runtime_unchanged'] and result['spec']==spec;assert native['passed'] and native['samples']==1000 and native['block']==spec['block'] and native['witnesses']==native['expected_witnesses']==8000 and not native['candidate_activation'];assert validation['ok'] and validation['actual_witnesses']==8000 and validation['exact_stratum']==[spec['hero'],spec['group'],spec['element'],spec['level']];rows.append({'unit':spec['unit'],'native_witnesses':8000,'original_G_archive_SHA256':receipt['archive_sha256'],'original_manifest_SHA256':receipt['manifest_sha256'],'cloud_exact_passed_output_cleaned':True})
report={'ok':True,'source_sha':plan['source_sha'],'blocks':[0,1,2],'required_and_verified_units':360,'required_and_verified_witnesses':2880000,'original_members_SHA_rechecked':members,'original_member_bytes_rechecked':bytes_checked,'all360_original_archive_SHA_and_CRC_rechecked':True,'local_checks':'Byte hash CRC and JSON metadata only; native witness validation performed on Tencent','cloud_full_final_metadata_audit_and_case_review_still_required':True,'full_required_units':360,'full_required_witnesses':2880000,'original720000_study_and314_gaps_unchanged':True,'formal_EXPERIMENT_accepted':False,'MAIN_accepted':False,'units':rows};(OUT/'independent-G-checkpoint.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in report.items() if k!='units'}))
