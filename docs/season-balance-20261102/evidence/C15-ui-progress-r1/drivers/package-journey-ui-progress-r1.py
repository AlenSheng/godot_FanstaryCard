from pathlib import Path
import gzip,hashlib,importlib.util,json,shutil

repo=Path.cwd();base=Path(__file__).parent;target=repo/'docs/season-balance-20261102/evidence/C15-ui-progress-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
stages=['journey-client-import-r1','journey-client-ui-en-pilot-r1','journey-client-ui-en-pilot-r2','journey-client-ui-en-pilot-r3','journey-client-ui-enzh-r1','journey-client-ui-arhi-r1','journey-client-ui-arhi-r2','journey-client-ui-jako-r1','journey-controller-native-r3']
raws={};summaries={}
for name in stages:
 source=base/name;destination=target/name;destination.mkdir()
 for p in sorted(source.glob('*')):
  if p.is_file() and p.suffix in ('.json','.jsonl','.log'):
   raw=p.read_bytes();public.inspect_public_bytes(p,raw);out=destination/(p.name+'.gz' if len(raw)>150000 else p.name)
   out.write_bytes(gzip.compress(raw,mtime=0) if len(raw)>150000 else raw)
   raws[(Path(name)/p.name).as_posix()]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'stored':out.relative_to(target).as_posix(),'gzip':len(raw)>150000}
 review=source/'review.json'
 if review.is_file():
  data=json.loads(review.read_bytes());checks=data['checks'];summaries[name]={'frames':len(data['frames']),'expected':data['expected_frames'],'checks':len(checks),'failed_checks':[key for key,value in checks.items() if not value],'render_capture_complete':data['render_capture_complete'],'layout_errors':data['legacy_layout_observations']}
  assert not summaries[name]['failed_checks'] and not summaries[name]['layout_errors'] and summaries[name]['render_capture_complete']
for name in ['run-journey-client-import-r1.py','run-journey-client-ui-r1.py','run-journey-client-ui-r2.py','run-journey-client-ui-r3.py','run-journey-client-ui-r4.py','run-journey-controller-native-r1.py']:
 p=base/name;out=target/'drivers'/name;out.parent.mkdir(exist_ok=True);out.write_bytes(p.read_bytes())
selected={
 'journey-client-ui-en-pilot-r3':['en_960_claim_hall_equipped.png','en_960_claim_deck_equipped.png','en_960_claim_rewards_confirm.png','en_960_claim_cosmetics_tail.png'],
 'journey-client-ui-enzh-r1':['en_960_claim_cosmetics_middle.png','zh-CN_960_claim_cosmetics_middle.png','zh-CN_960_claim_rewards_class_menu.png'],
 'journey-client-ui-arhi-r2':['ar_960_claim_cosmetics_owned.png','hi_960_claim_rewards_confirm.png','ar_1920_claim_cosmetics_tail.png']}
for stage,names in selected.items():
 for name in names:
  out=target/'viewed'/stage/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/stage/name,out)
images={}
for name in stages:
 for p in sorted((base/name).glob('*.png')):images[(Path(name)/p.name).as_posix()]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
matrix=['journey-client-ui-enzh-r1','journey-client-ui-arhi-r2','journey-client-ui-jako-r1']
assert sum(summaries[n]['frames'] for n in matrix)==216
result={'status':'first_six_language_matrix_verified_later_RTL_date_fix_and_final_matrix_pending','first_matrix_frames':216,'first_matrix_languages':['en','zh-CN','ar','hi','ja','ko'],'first_matrix_widths':[960,1280,1920],'first_matrix_states':12,'first_matrix_checks':sum(summaries[n]['checks'] for n in matrix),'first_matrix_failed_checks':0,'all_original_PNGs_retained':len(images),'final_required_unique_frames':396,'final_required_languages':11,'final_current_source_accepted':False,'remaining':['Native17casecontroller checks: newfull-class-nameassertion had resource admission rejection before Godot import.','CurrentwholeISOdate/time RTL isolation has not been compiled/rendered yet.','Freeze corrected source and finish12states*11languages*3widths actual frames plus direct visual review.','New mail permanent-copy draft and eightPG cases still need local compilation and isolatedPG validation; do not count them passed.'],'C15_complete':False,'overall_completed_items':20,'overall_items':35,'new_full_routes':0,'new_balance_encounters':0,'capacity100_retest':False,'production_restarted':False,'full_original_directory':str(base)}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(target/'frame-manifest.json').write_text(json.dumps(images,indent=2)+'\n',encoding='utf-8')
(target/'raw-text-manifest.json').write_text(json.dumps(raws,indent=2)+'\n',encoding='utf-8')
(target/'first-matrix-reports.json').write_text(json.dumps(summaries,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':manifest},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'first_matrix_frames':216,'all_raw_PNGs':len(images),'first_matrix_checks':result['first_matrix_checks'],'current_source_accepted':False,'files':len(manifest)}))
