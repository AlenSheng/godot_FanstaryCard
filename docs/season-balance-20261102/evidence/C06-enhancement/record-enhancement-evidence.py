from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
repo=Path.cwd();base=Path(__file__).parent;out=repo/'docs/season-balance-20261102/evidence/C06-enhancement'
assert not out.exists()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 tree=ET.parse(p);ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
 defs={node.attrib['id']:node.find('t:TestMethod',ns).attrib['className'] for node in tree.findall('.//t:UnitTest',ns)}
 return {defs[row.attrib['testId']]+'/'+row.attrib['testName']:row.attrib['outcome'] for row in tree.findall('.//t:UnitTestResult',ns)}
expected={55:'3309acad18608e2a23bb797d74abfde03140b3e2808b0f8ad8dd2a6f0f506607',56:'ced5db2e462cc62a32d7854ce182af14f098b7c10762f7283412ba0b1bfda82e',57:'cd7105b55ab1e7dcbb348f5d68feb65a1cc9ad1c4d5ee0bf50aa69e12d566cf0',58:'eb38eea69c5af0d76a1731de9f48295f93b8bfee8d36503235146a47e7c1adf6'}
manifests={n:read(base/f'storage-r{n}/input-manifest.json') for n in expected}
runtime={name:h for name,h in manifests[58]['files'].items() if name.startswith('server/src/') and name.endswith(('.cs','.sql'))}
assert all(sha(repo/name)==h for name,h in runtime.items())
assert all(all(m['files'].get(name)==h for name,h in runtime.items()) for m in manifests.values())
for n,h in expected.items():
 root=base/f'storage-r{n}';assert sha(root/'public-evidence.tar.gz')==h
 audit=read(root/'public/audit.json');assert not audit['oom_killed']
 for name,digest in audit['files'].items():assert sha(root/'public'/name)==digest
domain=cases(base/'storage-r55/public/season-enhancement-domain.trx')
assert len(domain)==560 and set(domain.values())=={'Passed'}
server={}
first=cases(base/'storage-r55/public/season-enhancement-server.trx')
assert len(first)==189 and sum(v=='Passed' for v in first.values())==175
for n in [55,56,57,58]:
 for p in (base/f'storage-r{n}/public').glob('*.trx'):
  if 'domain' in p.name:continue
  server.update({k:v for k,v in cases(p).items() if v=='Passed'})
assert len(server)==193 and set(server.values())=={'Passed'}
enhancement={k:v for k,v in server.items() if 'PostgresSeasonEnhancementTests/' in k}
assert len(enhancement)==17
native=read(base/'enhancement-native-r5/checks.json');assert native['ok'] and native['checks']==117
assert read(base/'enhancement-native-r5/result.json')['source_unchanged']
for name,h in read(base/'enhancement-native-r5/source-pin.json').items():assert sha(repo/name)==h
runs={'enhancement-ui-a-r1':['c06_armor','c06_weapon'],'enhancement-ui-b-r1':['c06_confirm'],'enhancement-ui-material-r2':['c06_material'],'enhancement-ui-error-r1':['c06_error']}
locales=['zh-CN','en','es','fr','pt','id','hi','ar','ru','ja','ko'];widths=[960,1280,1920]
frames={};checks=0;run_rows={};scope_diffs={}
for run,scenes in runs.items():
 root=base/run;review=read(root/'review.json');terminal=read(root/'terminal.original.json')
 assert terminal['native_exit']==0 and terminal['source_unchanged'] and terminal['stop_reason'] is None
 assert terminal['input_desktop_unchanged'] and terminal['all_checked_threads_private'] and terminal['desktop_switch_calls']==0
 assert review['render_capture_complete'] and all(review['checks'].values())
 selected={f'{locale}_{width}_{scene}' for scene in scenes for locale in locales for width in widths}
 for frame in selected:
  name=frame+'.png';assert name not in frames
  frames[name]={'run':run,'sha256':sha(root/name),'bytes':(root/name).stat().st_size}
 subset={key:value for key,value in review['checks'].items() if key.split(':',1)[0] in selected}
 assert all(subset.values());checks+=len(subset)
 run_rows[run]={'unique_frames_used':len(selected),'checks_used':len(subset),'whole_run_frames':review['screenshots'],'seconds':terminal['seconds']}
 scope_diffs[run]=[name.replace('\\','/') for name,h in read(root/'source-pin.original.json').items() if sha(repo/name)!=h]
assert len(frames)==165
out.mkdir(parents=True)
for n in expected:
 shutil.copytree(base/f'storage-r{n}/public',out/f'r{n}')
 shutil.copy2(base/f'storage-r{n}/input-manifest.json',out/f'r{n}/input-manifest.json')
for run in ['enhancement-native-r1','enhancement-native-r2','enhancement-native-r3','enhancement-native-r4','enhancement-native-r5','enhancement-script-check-r1','enhancement-script-check-r2']:
 root=base/run;dest=out/run;dest.mkdir()
 for p in root.glob('*'):
  if p.is_file() and p.suffix in ['.json','.log','.gd']:shutil.copy2(p,dest/p.name)
ui_file_manifest={}
for run in [*runs]:
 root=base/run;dest=out/'ui'/run;dest.mkdir(parents=True)
 for p in root.glob('*'):
  if p.is_file():
   ui_file_manifest[run+'/'+p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
   if p.suffix in ['.json','.log','.jsonl']:shutil.copy2(p,dest/p.name)
for name in ['enhancement-localization-r2.json','enhancement-ui-text-r2.json','ended-expanded-inputs-v1.json','consumed-transfer-origins-50.json','consumed-transfer-origins-early.json','run-enhancement-native.py','archive-ended-expanded-inputs.py','archive-ended-expanded-inputs-v2.py','record-ended-input-locations.py']:
 shutil.copy2(base/name,out/name)
for scene in [s for ss in runs.values() for s in ss]:
 sheet=Image.new('RGB',(960,2178),(12,26,30));draw=ImageDraw.Draw(sheet)
 for row,locale in enumerate(locales):
  for col,width in enumerate(widths):
   name=f'{locale}_{width}_{scene}.png';entry=frames[name]
   im=Image.open(base/entry['run']/name).convert('RGB');im.thumbnail((320,180))
   sheet.paste(im,(col*320,row*198+18));draw.text((col*320+3,row*198+2),f'{locale} {width} {scene}',fill=(245,210,135))
 sheet.save(out/('contact-'+scene+'.jpg'),quality=88)
for name in ['en_960_c06_armor.png','en_960_c06_weapon.png','ru_960_c06_material.png','ar_960_c06_confirm.png','es_960_c06_error.png']:
 entry=frames[name];shutil.copy2(base/entry['run']/name,out/name)
proof={'status':'enhancement_pipeline_verified_C06_remains_in_progress_until_C08_body_reforge_budget','C06_complete':False,'whole_goal_complete':False,
 'configuration_version':'season-v1-config-3','workbook_or_published_bytes_changed':False,'domain_full_passed':560,
 'server_selected_check_union':len(server),'server_union_not_single_full_run':True,'new_Postgres_enhancement_case_union':len(enhancement),'tests_skipped':0,
 'runtime_files_byte_identical_across_r55_to_r58':len(runtime),'native_checks':117,'native_new_enhancement_checks':29,'native_equipment_regression_checks':88,
 'ui':{'unique_final_frames':165,'checks_passed':checks,'locales':locales,'widths':widths,'runs':run_rows,'whole_project_E02_complete':False,
  'scope_changes_after_earlier_runs':'Only material-dialog Cancel localization, failed-quote source guard and unused diagnostic fixtures changed. Earlier positive/confirmation paths are unchanged; final material and error branches were rendered separately.'},
 'actual_upgrade_budgets':{'days30':{'oneOrangeFourPurple_to3':52,'oneOrangeFourPurple_to5':573,'red_to5':281},'days42and60':{'oneOrangeFourPurple_to3':60,'oneOrangeFourPurple_to5':780,'red_to5':390},'permanent_weapon_to5':248},
 'still_required_for_C06':['Actual five-body learned-template rebuild costing four purple fragments plus two orange fragments: C07/C08 dependents; arithmetic +6 is not a transaction proof'],
 'other_pending':['A03 permanent-weapon wallet selector UI remains pending; the existing explicit server wallet API is preserved','C07 marks, crafting and wishes; C08 recipes and one-in/one-out reforge; C11 fresh red mint/quota','D/E/F full-route, full UI and final production release gates'],
 'public_archive_sha256':expected,
 'failures_retained':[{'run':'r55','domain_passed':560,'server_passed':175,'server_failed':14,'reason':'Fixture declared purple/orange/red existing items as D0 origin; ck_equipment_generated_difficulty_quality correctly rejected before enhancement. Origin corrected to D5 without changing caps.'},
 {'run':'r56','passed':16,'failed':1,'reason':'Owner-control fixture reused a display name and therefore the same local-name account; unique names and distinct-player assertion added.'},
 {'run':'enhancement-native-r1','reason':'90-second incomplete caller stop; original runner failed to persist buffered exception output; missing native output is explicitly retained as an evidence gap.'},
 {'run':'enhancement-native-r2','reason':'Caller treated an independent SceneTree protocol script as a run_test suite; watchdog ended the incomplete diagnostic, with raw engine errors retained.'},
 {'run':'enhancement-script-check-r1','reason':'New visual fixture cost variable needed explicit String type; no renderer started.'},
 {'run':'enhancement-ui-b-r1 material subset','reason':'Native AcceptDialog OK label was English; localized Cancel and 33 material frames re-rendered.'},
 {'run':'r57 resource admission','reason':'Fixed 3GiB+256MiB startup guard rejected before SDK; no threshold lowered.'}],
 'resource_evidence':{'local_reserve_gib':6,'cloud_ram_floor_mib':500,'cloud_disk_floor_gib':3,'cloud_disk_floor_percent':5,
  'ended_expanded_snapshot_sha256':'8dd121792f5455cb1bcee17f7b2a8a2644244eb4801e3d4331627f8564045b00','expanded_files_preserved':2906,
  'original_source_and_public_archives_unchanged':True,'complete_snapshot_cloud_and_local':True,'only_verified_expanded_copies_retired':True,
  'production_services_or_other_tasks_modified':False},
 'full_gameplay_or_capacity_matches_added':0,'B05_routes_used':291,'B05_routes_remaining':9,'production_deployed':False,'production_restarted':False}
(out/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'runtime-files.json').write_text(json.dumps(runtime,indent=2)+'\n')
(out/'final-frame-manifest.json').write_text(json.dumps(frames,indent=2)+'\n')
(out/'ui-original-file-manifest.json').write_text(json.dumps({'external_root':str(base),'files':ui_file_manifest},indent=2)+'\n')
(out/'source-scope-diffs.json').write_text(json.dumps(scope_diffs,indent=2)+'\n')
print(json.dumps({'domain_passed':560,'server_union':len(server),'new_transaction_cases':len(enhancement),'native_checks':117,'unique_frames':165,'ui_checks':checks,'runtime_sources':len(runtime),'C06_complete':False}))

