from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
from PIL import Image,ImageDraw
repo=Path.cwd();base=Path(__file__).parent;target=repo/'docs/season-balance-20261102/evidence/C05-integration'
assert not target.exists()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def trx(path):
    tree=ET.parse(path);ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
    definitions={}
    for test in tree.findall('.//t:UnitTest',ns):
        method=test.find('t:TestMethod',ns)
        if method is not None:definitions[test.attrib['id']]=method.attrib['className']
    return {definitions[row.attrib['testId']]+'/'+row.attrib['testName']:row.attrib['outcome'] for row in tree.findall('.//t:UnitTestResult',ns)}
stages={n:read(base/('storage-r'+str(n))/'input-manifest.json') for n in [50,51,53,54]}
public_hashes={50:'c3efb0c7569eb33fdd08e21401a8015604ece0a9310c1495b83966dd1d1dde8d',51:'7643f5f1f334ffdce6fddba8be0f27b86561748de205d2f2232b93bb95cdf9a6',53:'21b9b609e274d4b0a49be1405d4d3579289055777003d2764b1a36b137043f3f',54:'32b705b1b2f46453d887d92a39d6fc0866b116f0cb5312d674318e7430278388'}
for stage,h in public_hashes.items():
    p=base/('storage-r'+str(stage));assert sha(p/'public-evidence.tar.gz')==h
    audit=read(p/'public/audit.json')
    for name,checksum in audit['files'].items():assert sha(p/'public'/name)==checksum
    assert not audit['oom_killed']
runtime_files={name:h for name,h in stages[54]['files'].items() if name.startswith('server/src/') and name.endswith(('.cs','.sql'))}
assert all(sha(repo/name)==h for name,h in runtime_files.items())
domain53=trx(base/'storage-r53/public/season-equipment-domain-final.trx')
domain54=trx(base/'storage-r54/public/season-equipment-runtime-final.trx')
domain_union={k:v for k,v in domain53.items() if 'SeasonEquipmentRuntimeTests/' not in k};domain_union.update(domain54)
assert len(domain53)==549 and len(domain54)==4 and len(domain_union)==550 and set(domain_union.values())=={'Passed'}
server51={}
for p in (base/'storage-r51/public').glob('*.trx'):server51.update(trx(p))
server53=trx(base/'storage-r53/public/season-equipment-action-recovery.trx')
server54=trx(base/'storage-r54/public/season-equipment-transport-final.trx')
server_union={k:v for k,v in server51.items() if v=='Passed'};server_union.update(server53);server_union.update(server54)
assert len(server51)==196 and sum(v=='Passed' for v in server51.values())==194
assert len(server_union)==196 and set(server_union.values())=={'Passed'}
runs={'equipment-ui-a-r2':['c05_gear','c05_prep','c05_enhance','c05_compare'],'equipment-ui-numbers-r1':['c05_numbers'],'equipment-ui-inventory-r3':['c05_inventory'],'equipment-ui-inventory-details-r2':['c05_inventory_details'],'equipment-ui-relic-r1':['c05_relic']}
locales=['zh-CN','en','es','fr','pt','id','hi','ar','ru','ja','ko'];widths=[960,1280,1920]
frames={};ui_checks=0;run_summaries={}
for run,scenes in runs.items():
    root=base/run;review=read(root/'review.json');terminal=read(root/'terminal.original.json')
    assert terminal['native_exit']==0 and not terminal['stop_reason'] and terminal['source_unchanged']
    assert terminal['all_checked_threads_private'] and terminal['input_desktop_unchanged'] and terminal['desktop_switch_calls']==0
    assert review['render_capture_complete'] and all(review['checks'].values())
    expected={f'{locale}_{width}_{scene}.png' for scene in scenes for locale in locales for width in widths}
    assert {p.name for p in root.glob('*.png')}==expected
    for name in expected:
        assert name not in frames
        frames[name]={'run':run,'sha256':sha(root/name),'bytes':(root/name).stat().st_size}
    ui_checks+=len(review['checks'])
    run_summaries[run]={'frames':len(expected),'checks':len(review['checks']),'private_desktop':True,'deadline_seconds':180,'seconds':terminal['seconds']}
assert len(frames)==264
native=read(base/'equipment-native-r3/checks.json');assert native['ok'] and all(native['checks'].values())
assert read(base/'equipment-native-r3/result.json')['source_unchanged']
legacy=read(base/'config-client-native-r8/result.json');assert all(row['exit']==0 and not row['engine_errors'] for row in legacy['runs'])
for name,h in read(base/'equipment-native-r3/source-pin.json').items():assert sha(repo/name)==h
target.mkdir(parents=True)
for stage in public_hashes:
    root=base/('storage-r'+str(stage));shutil.copytree(root/'public',target/('r'+str(stage)))
    shutil.copy2(root/'input-manifest.json',target/('r'+str(stage))/'input-manifest.json')
for name in ['equipment-native-r1','equipment-native-r2','equipment-native-r3']:
    dest=target/name;dest.mkdir()
    for p in (base/name).iterdir():
        if p.is_file() and p.suffix in ['.json','.log','.gd']:shutil.copy2(p,dest/p.name)
for name in ['equipment-localization-r2.json','equipment-ui-text-r2.json','red-equipment-art-proof.json']:
    shutil.copy2(base/name,target/name)
original_runs=[*runs,'equipment-ui-a-r1','equipment-ui-b-r1','equipment-ui-inventory-r1','equipment-ui-inventory-r2','equipment-ui-inventory-details-r1']
original_manifest={}
for run in original_runs:
    root=base/run;dest=target/'ui'/run;dest.mkdir(parents=True)
    for p in root.glob('*'):
        if p.is_file():
            original_manifest[run+'/'+p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
            if p.suffix in ['.json','.log','.jsonl']:shutil.copy2(p,dest/p.name)
for scene in [s for ss in runs.values() for s in ss]:
    sheet=Image.new('RGB',(3*320,11*198),(12,26,30));draw=ImageDraw.Draw(sheet)
    for row,locale in enumerate(locales):
        for col,width in enumerate(widths):
            name=f'{locale}_{width}_{scene}.png';entry=frames[name]
            im=Image.open(base/entry['run']/name).convert('RGB');im.thumbnail((320,180))
            x=col*320;y=row*198;sheet.paste(im,(x,y+18));draw.text((x+3,y+2),f'{locale} {width} {scene}',fill=(245,210,135))
    sheet.save(target/('contact-'+scene+'.jpg'),quality=88)
for name in ['es_960_c05_inventory.png','ru_960_c05_inventory_details.png','ar_960_c05_numbers.png','en_1920_c05_compare.png','ja_1280_c05_relic.png']:
    e=frames[name];shutil.copy2(base/e['run']/name,target/name)
(target/'ui-original-files.json').write_text(json.dumps({'root':str(base),'files':original_manifest},indent=2)+'\n',encoding='utf-8')
(target/'final-frame-manifest.json').write_text(json.dumps(frames,indent=2)+'\n',encoding='utf-8')
diffs={f'{a}_to_{b}':[name for name,h in stages[b]['files'].items() if stages[a]['files'].get(name)!=h] for a,b in [(51,53),(53,54)]}
proof={'status':'C05_scope_complete_whole_goal_pending','C05_complete':True,'whole_goal_complete':False,'configuration_version':'season-v1-config-3','stats_version':'season-equipment-v1','configuration_binary_sha256':'8ece4158eac78e3e554cc6d2a5f0d7f873b27eb026d764791089a5e0e309fa08','domain_r53_passed':549,'runtime_r54_passed':4,'domain_current_check_union':550,'server_r51_passed':194,'server_r51_failed':2,'corrected_server_r53_passed':2,'server_r54_equipment_and_persistence_passed':7,'server_current_check_union':196,'union_is_not_a_single_full_run':True,'tests_skipped':0,'runtime_files_pinned':len(runtime_files),'source_changes_between_evidence':diffs,'native_model_protocol_art_checks':len(native['checks']),'native_legacy_checks':250,'ui':{'unique_frames':len(frames),'checks_passed':ui_checks,'languages':locales,'widths':widths,'runs':run_summaries,'whole_project_UI_complete':False},'public_archive_sha256':public_hashes,'failures_retained':[{'run':'r50','domain_passed':548,'server_passed':190,'server_failed':2,'reason':'combat-action fixture SQL used obsolete stats reference after definition was updated'},{'run':'r51','server_passed':194,'server_failed':2,'reason':'combat-action fixture constructed prototype catalog while restart restored the frozen published catalog'},{'run':'equipment-native-r1','reason':'external SceneTree runner used direct Game identifier before autoload context; no product checks executed'},{'run':'equipment-ui-a-r1','frames':132,'failed_checks':30,'reason':'warehouse equipment button names truncated; red art absent'},{'run':'equipment-ui-b-r1','frames':73,'reason':'OwnedRendererDeadline 180s; incomplete, not a pass'},{'run':'equipment-ui-inventory-r1','frames':56,'reason':'OwnedRendererDeadline 180s; incomplete, not a pass'},{'run':'equipment-ui-inventory-r2','frames':33,'failed_checks':15,'reason':'worn armor button text truncated in es/pt/ru'},{'run':'equipment-ui-inventory-details-r1','frames':33,'failed_checks':15,'reason':'same worn armor text truncation'},{'run':'r53 initial transport','reason':'incorrect expected SHA rejected before SDK start; corrected against retained original'},{'run':'r50/r53/r54 resource admission','reason':'fixed disk guard refused SDK start; ended owned archives SHA-verified locally before retiring cloud copies'}],'scope_limits':['Red persistence tests explicitly seed previously owned red controls; C11 fresh mint and weekly quota remain pending','C06 enhancement costs/material selection remain pending; this batch preserves metadata only','Diagnostic attribute/Resolver tests do not prove full-route DPS or PVP balance','264 frames cover eight affected equipment states, not full E02','Historical 100-player failures retained; no capacity retry','B05 remains 291/300, nine routes left','Production season not activated; production not deployed or restarted by this batch'],'production_deployed':False,'production_restarted':False,'full_gameplay_or_capacity_matches_added':0,'B05_routes_used':291,'B05_routes_remaining':9}
(target/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(target/'runtime-files.json').write_text(json.dumps(runtime_files,indent=2)+'\n')
print(json.dumps({'frames':len(frames),'UI_checks':ui_checks,'domain_union':len(domain_union),'server_union':len(server_union),'native_checks':len(native['checks']),'runtime_files':len(runtime_files)}))

