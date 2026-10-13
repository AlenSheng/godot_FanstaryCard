"""Local byte/SHA/CRC/immutable JSON identity checks only; no experiment calculation."""
import gzip,hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];G=Path('G:/PR13Evidence/B04-single-factor-full-r1');OUT=B/'B04-first-full1000-paired-block-G-check-r1'
def require(v,m):
 if not v:raise ValueError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 plan_path=G/'common-frozen-inputs/plan.original.json';plan=json.loads(plan_path.read_bytes());specs=plan['units'][:50];require(len(plan['units'])==5400 and plan['expected_encounters']==216000 and plan['required_paired_seeds_per_stratum']==3000,'Original quota differs');require(len(specs)==50 and all((s['hero'],s['group'],s['strategy'],s['block'],s['samples'],s['encounters'])==('Mage','O1','baseline_all_hand',0,20,40) for s in specs) and [s['offset'] for s in specs]==list(range(0,1000,20)),'Exact first complete original 1000-paired block differs');require(not OUT.exists(),'Immutable verification already exists')
 # Refuse incomplete block before creating an output or a passing observation.
 for s in specs:require((G/'units'/s['unit']/'cloud-cleanup.original.json').is_file(),'First original complete seed block not yet G-closed')
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();require(not subprocess.check_output(['git','diff','--name-only',plan['source_sha'],head,'--','server','protocol'],cwd=R).strip(),'Current executed product source differs')
 rows=[];members=0;original_bytes=0
 for s in specs:
  root=G/'units'/s['unit'];p=root/'complete-original-manifest.json';m=json.loads(p.read_bytes());receipt=json.loads((root/'local-G-receipt.original.json').read_bytes());clean=json.loads((root/'cloud-cleanup.original.json').read_bytes());require(m['ok'] and m['unit']==s['unit'] and m['encounters']==40 and receipt['ok'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified'] and not receipt['native_reexecuted_by_backup'] and clean['ok'] and clean['originals_G_complete'] and sha(p)==receipt['manifest_sha256']==clean['manifest_sha256'],'Original complete custody differs')
  for f in m['files']:
   p=root/f['path'];require(p.stat().st_size==f['bytes'] and sha(p)==f['sha256'],'Original full member bytes differ');members+=1;original_bytes+=f['bytes']
  archive=G/'archives'/(s['unit']+'.original.tar.gz');require(archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256'],'Original archive bytes differ')
  with gzip.open(archive,'rb') as f:
   while f.read(1024**2):pass
  native=json.loads((root/'metadata/result.original.json').read_bytes());v=json.loads((root/'outputs/native/independent-part-validation.original.json').read_bytes());meta=json.loads((root/'outputs/native/manifest.original.json').read_bytes());require(native['ok'] and native['exit_code']==0 and not native['oom_killed'] and native['owned_container_removed'] and native['runtime_and_controller_unchanged'] and native['spec']==s,'Exact original native part failed');require(v['ok'] and v['samples']==20 and v['encounters']==40 and v['seed_start']==450001+s['offset'] and v['block']==0 and v['hero']=='Mage' and v['group']=='O1' and v['strategy']=='baseline_all_hand' and v['source_sha']==plan['source_sha'],'Actual independent per-part identity differs');require(v['actual_twenty_original_instances_and_legal_additions_verified'] and v['fixed_default_policies_off'] and v['complete_gzip_SHA_and_CRC_verified'] and meta['baseline_budget']==meta['candidate_budget'] and meta['embedded_resource_bytes_sha256']==v['embedded_resource_bytes_sha256'],'Actual original inputs or independent checks differ');rows.append({'unit':s['unit'],'spec':s,'original_G_archive_sha256':receipt['archive_sha256'],'original_delivery_manifest_sha256':receipt['manifest_sha256'],'independent_original_validation_sha256':sha(root/'outputs/native/independent-part-validation.original.json'),'actual_native_result_sha256':sha(root/'metadata/result.original.json'),'complete_original_G_receipt':receipt,'exact_cloud_cleanup':clean})
 report={'ok':True,'implementation_source_sha':plan['source_sha'],'current_documentation_release_sha':head,'original_complete_block':{'hero':'Mage','group':'O1','strategy':'baseline_all_hand','block':0,'actual_physical_parts':50,'actual_paired_seed_count':1000,'actual_both_arm_encounters':2000},'full_required_physical_parts':5400,'full_required_encounters':216000,'full_required_independent_blocks':3,'remaining_blocks_and_other_strata_still_required':True,'original_plan_sha256':sha(plan_path),'all50_original_archives_SHA_CRC_rechecked':True,'all_original_member_count_rehashed':members,'all_original_member_bytes_rehashed':original_bytes,'local_operations':'byte SHA CRC and frozen JSON metadata only; native rules and original numerical validation execute on Tencent','full_statistics_not_executed':True,'formal_profile_acceptance':False,'MAIN_accepted':False,'units':rows};OUT.mkdir();(OUT/'independent-G-check.original.json').write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in report.items() if k!='units'}))
if __name__=='__main__':main()
