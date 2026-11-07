from pathlib import Path
import json,hashlib,shutil,gzip,xml.etree.ElementTree as ET
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');repo=Path.cwd();out=repo/'docs/season-balance-20261102/evidence/C07-C08-ui'
assert not out.exists();out.mkdir(parents=True)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
selected={'crafting-ui-c07-r1':['c07_entry'],'crafting-ui-c07-r2':['c07_make','c07_orange','c07_locked','c07_confirm'],'crafting-ui-c08-a-r1':['c08_list','c08_learn'],'crafting-ui-c08-b-r1':['c08_preview','c08_confirm','c08_blocked'],'crafting-ui-states-r1':['c07_notjoined','c07_error','c08_numbers'],'crafting-ui-market-r1':['c08_market'],'crafting-ui-preview-tail-r1':['c08_preview_bottom']}
manifest={};runs={};check_count=0
for run,scenes in selected.items():
 src=b/run;d=out/run;d.mkdir()
 r=read(src/'review.json');term=read(src/'terminal.original.json')
 assert term['native_exit']==(1 if run=='crafting-ui-c07-r1' else 0)
 assert term['source_unchanged'] and term['input_desktop_unchanged'] and term['desktop_switch_calls']==0 and term['all_checked_threads_private']
 names={f['name'] for f in r['frames'] if any(f['name'].endswith('_'+s) for s in scenes)}
 used={k:v for k,v in r['checks'].items() if any(k.startswith(n+':') for n in names)}
 assert len(names)==len(scenes)*33 and used and all(used.values())
 for name in names:
  p=src/(name+'.png');assert p.is_file();assert name+'.png' not in manifest
  manifest[name+'.png']={'run':run,'sha256':sha(p),'bytes':p.stat().st_size,'scope':'C07' if '_c07_' in name else 'C08'}
 for p in src.iterdir():
  if p.is_file() and p.suffix in ['.json','.log','.jsonl']:
   if p.name in ['review.json','frames.original.jsonl','godot.original.log']:
    target=d/(p.name+'.gz');target.write_bytes(gzip.compress(p.read_bytes(),mtime=0));assert gzip.decompress(target.read_bytes())==p.read_bytes()
   else:shutil.copy2(p,d/p.name)
 runs[run]={'scenes':scenes,'frames_used':len(names),'checks_used':len(used),'full_run_frames':r['screenshots'],'full_run_failed_checks':sum(not v for v in r['checks'].values()),'seconds':term['seconds']}
 check_count+=len(used)
assert sum(v['scope']=='C07' for v in manifest.values())==231
assert sum(v['scope']=='C08' for v in manifest.values())==264
for run in ['crafting-native-r4','crafting-native-r5','crafting-native-r6','crafting-native-r7']:
 d=out/run;d.mkdir()
 for p in (b/run).glob('*'):
  if p.is_file() and p.suffix in ['.gd','.json','.log']:shutil.copy2(p,d/p.name)
for n in [66,67,68]:
 src=b/f'storage-r{n}';d=out/f'r{n}';shutil.copytree(src/'public',d)
 shutil.copy2(src/'input-manifest.json',d/'input-manifest.json');shutil.copy2(src/'start-storage-tests.py',d/'start-storage-tests.py')
for name in ['crafting-c07-review.jpg','crafting-c08-review.jpg','crafting-localization-r3.json','crafting-ui-text-r3.json','run-crafting-native-v2.py']:shutil.copy2(b/name,out/name)
current=read(b/'crafting-native-r7/checks.json');assert current['ok'] and current['checks']==154
for name,h in read(b/'crafting-native-r7/source-pin.json').items():
 if name not in ['client/tests/ui_visual_review.gd','client/ui/season_crafting_view.gd']:assert sha(repo/name)==h
runtime={n:h for n,h in read(b/'storage-r68/input-manifest.json')['files'].items() if n.startswith('server/src/') and n.endswith(('.cs','.sql'))}
assert all(sha(repo/n)==h for n,h in runtime.items())
assert all(read(b/'storage-r64/input-manifest.json')['files'].get(n)==h for n,h in runtime.items())
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
def cases(p):
 t=ET.parse(p);defs={u.attrib['id']:u.find('t:TestMethod',ns).attrib['className'] for u in t.findall('.//t:UnitTest',ns)}
 return {defs[u.attrib['testId']]+'/'+u.attrib['testName']:u.attrib['outcome'] for u in t.findall('.//t:UnitTestResult',ns)}
union=read(repo/'docs/season-balance-20261102/evidence/C07-C08-backend/server-case-union.json');union.update(cases(out/'r67/season-crafting-api.trx'));union.update(cases(out/'r68/recipe-edges.trx'))
assert set(union.values())=={'Passed'} and len(union)==265
(out/'server-case-union.json').write_text(json.dumps(union,indent=2)+'\n')
(out/'final-frame-manifest.json').write_text(json.dumps(dict(sorted(manifest.items())),indent=2)+'\n')
proof={'status':'C07_C08_completed_current_scope','C07_complete':True,'C08_complete':True,'whole_goal_complete':False,'configuration_version':'season-v1-config-4','workbook_and_config_unchanged_since_backend':True,'runtime_sources_unchanged_since_r64':len(runtime),'domain_targeted_union_passed':561,'server_targeted_union_passed':265,'server_not_one_full_run':True,'r67_real_Protobuf_HTTP_session':{'passed':1,'routes_exercised':5,'real_server_process':True,'isolated_PostgreSQL':True},'r68_PostgreSQL_recipe_tests':{'passed':11,'failed':0,'skipped':0,'new_case_count':5},'native_checks':154,'native_rendered_claim':False,'ui':{'C07_unique_frames':231,'C08_unique_frames':264,'checks_used':check_count,'locales':11,'widths':[960,1280,1920],'runs':runs,'manual_reviewed':['fr 960 craft and market','hi 1280 orange','ru 1920 locked','ja 960 craft confirm','ar 960 unaffixed purple learn','ru 1280 preview','hi 1920 reforge confirm','ja 960 numerical comparison','ru 960 preview bottom'],'scroll_warning_reachable_33_frames':True,'private_desktop_only':True,'whole_project_E02_complete':False,'branch_reuse_note':'Earlier core frames retain their original source pins. Later production changes are market-only layout and a nonvisual preview-scroll node name, plus quote ownership guard; new fixtures and controller tests do not alter earlier visuals. Entry subset comes from first run; its failing craft frames are excluded and preserved.'},'retained_failures':[{'run':'crafting-ui-c07-r1','failed_checks':36,'reason':'French/Indonesian/Russian income hints clipped; panel and hint expanded; corrected132 frames passed'},{'run':'r66','failed_cases':1,'reason':'Test key rebuild had7 characters; existing minimum8 rejected. Corrected test keys only; real HTTP r67 passed'},{'run':'crafting-native-r4,r5,r6','assertions_passed':True,'acceptance_passed':False,'reason':'Controller fixture played audio on short-lived headless process. Verbose r5 identified upgrade/error WAV; fixture muted without persistence; r7 exit clean'}],'previous_failures_and_skips_retained':'C07-C08-backend/result.json; no old result overwritten','public_archive_sha256':{'r66':sha(b/'storage-r66/public-evidence.tar.gz'),'r67':sha(b/'storage-r67/public-evidence.tar.gz'),'r68':sha(b/'storage-r68/public-evidence.tar.gz')},'current_UI_source_hashes':{p.relative_to(repo).as_posix():sha(p) for p in [repo/'client/ui/main.gd',repo/'client/ui/season_crafting_view.gd',repo/'client/ui/reference_ui.gd',repo/'client/ui/season_crafting_model.gd',repo/'client/tests/ui_visual_review.gd',repo/'client/tests/test_season_crafting_controller.gd']},'production_deployed':False,'production_restarted':False,'capacity_retested':False,'actual_game_matches_added':0,'B05_used':291,'B05_remaining':9,'still_required':['C09 natural preferred-element weighting and non-choice resource scales','C10 bot reward provenance','C11 red mint quota','Remaining A/C/D/E/F gates and final deployment']}
(out/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'C07_frames':231,'C08_frames':264,'checks':check_count,'server_union':len(union),'status':proof['status']}))
