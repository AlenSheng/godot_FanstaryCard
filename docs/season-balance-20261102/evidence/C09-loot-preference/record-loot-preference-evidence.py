from pathlib import Path
import json,hashlib,shutil,gzip,subprocess,xml.etree.ElementTree as ET
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=repo/'docs/season-balance-20261102/evidence/C09-loot-preference';assert not out.exists();out.mkdir(parents=True)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
archives={70:'336b6a8a9bd365a8231c3d8667a7e0c1388728efd97cbd5c9ef1b71c3797960a',71:'0075322a179b0709448232c36fc3f72e7e0ae649b7d8de851d223b497cff68bd',72:'b125de4abdddc09dd7ea19bf786e024a6c1a5d11b050857cd28ff0fd0a77104a'}
for n,h in archives.items():
 p=base/f'storage-r{n}';assert sha(p/'public-evidence.tar.gz')==h;a=read(p/'public/audit.json');assert a['state']=='exited' and not a['oom_killed']
 for name,digest in a['files'].items():assert sha(p/'public'/name)==digest
 shutil.copytree(p/'public',out/f'r{n}')
 for name in ['input-manifest.json','start-storage-tests.py']:shutil.copy2(p/name,out/f'r{n}'/name)
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
def cases(p):
 t=ET.parse(p);defs={n.attrib['id']:n.find('t:TestMethod',ns).attrib['className'] for n in t.findall('.//t:UnitTest',ns)}
 return {defs[n.attrib['testId']]+'/'+n.attrib['testName']:n.attrib['outcome'] for n in t.findall('.//t:UnitTestResult',ns)}
domain=cases(out/'r71/loot-preference-domain.trx');assert len(domain)==581 and set(domain.values())=={'Passed'}
server71=cases(out/'r71/loot-preference-server.trx');server72=cases(out/'r72/loot-preference-corrected.trx');server={k:v for k,v in server71.items() if v=='Passed'};server.update(server72);assert len(server)==298 and set(server.values())=={'Passed'}
(out/'server-case-union.json').write_text(json.dumps(server,indent=2)+'\n');(out/'domain-cases.json').write_text(json.dumps(domain,indent=2)+'\n')
m71=read(base/'storage-r71/input-manifest.json');m72=read(base/'storage-r72/input-manifest.json');runtime={n:h for n,h in m72['files'].items() if n.startswith('server/src/') and n.endswith(('.cs','.sql'))}
assert len(runtime)==196 and all(m71['files'].get(n)==h==sha(repo/n) for n,h in runtime.items())
current_native=read(base/'loot-preference-native-r5/checks.json');assert current_native['ok'] and current_native['checks']==213
for n,h in read(base/'loot-preference-native-r5/source-pin.json').items():assert sha(repo/n)==h
for run in ['loot-preference-native-r1','loot-preference-native-r2','loot-preference-native-r3','loot-preference-native-r4','loot-preference-native-r5']:
 d=out/run;d.mkdir()
 for p in (base/run).iterdir():
  if p.is_file() and p.suffix in ['.gd','.json','.log']:shutil.copy2(p,d/p.name)
selected={'loot-preference-ui-a-r1':['c09_default','c09_preference'],'loot-preference-ui-b-r1':['c09_locked'],'loot-preference-ui-info-r4':['c09_info']}
all_runs=['loot-preference-ui-a-r1','loot-preference-ui-b-r1','loot-preference-ui-info-r2','loot-preference-ui-info-r3','loot-preference-ui-info-r4']
frames={};runs={};checks=0;captured=0
for run in all_runs:
 src=base/run;d=out/run;d.mkdir();r=read(src/'review.json');t=read(src/'terminal.original.json');captured+=r['screenshots']
 assert t['source_unchanged'] and t['all_checked_threads_private'] and t['input_desktop_unchanged'] and t['desktop_switch_calls']==0
 scenes=selected.get(run,[]);names={f['name'] for f in r['frames'] if any(f['name'].endswith('_'+s) for s in scenes)};used={k:v for k,v in r['checks'].items() if any(k.startswith(n+':') for n in names)}
 if names:
  assert len(names)==len(scenes)*33 and all(used.values()) and t['native_exit']==0
 for name in names:
  p=src/(name+'.png');assert p.is_file() and name+'.png' not in frames;frames[name+'.png']={'run':run,'sha256':sha(p),'bytes':p.stat().st_size}
 for p in src.iterdir():
  if p.is_file() and p.suffix in ['.json','.jsonl','.log']:
   if p.name in ['review.json','frames.original.jsonl']:
    dest=d/(p.name+'.gz');dest.write_bytes(gzip.compress(p.read_bytes(),mtime=0));assert gzip.decompress(dest.read_bytes())==p.read_bytes()
   else:shutil.copy2(p,d/p.name)
 runs[run]={'selected_states':scenes,'final_frames_used':len(names),'final_checks_used':len(used),'captured_frames':r['screenshots'],'raw_failed_checks':sum(not v for v in r['checks'].values()),'seconds':t['seconds']};checks+=len(used)
assert len(frames)==132 and checks==19665 and captured==231
bounds={k:v for k,v in read(base/'loot-preference-ui-info-r4/review.json')['checks'].items() if 'content inside decorated panel' in k};assert len(bounds)==99 and all(bounds.values())
(out/'final-frame-manifest.json').write_text(json.dumps(dict(sorted(frames.items())),indent=2)+'\n')
wb=base/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/loot-preference';proof=read(wb/'preservation-proof.json');assert sha(repo/'config/FantasyCard_Config.xlsx')==proof['after_sha256']
d=out/'workbook';d.mkdir()
for name in ['SeasonLootPreference.png','preference-rows.json','preservation-proof.json','FantasyCard_Config.xlsx.inspect.ndjson']:shutil.copy2(wb/name,d/name)
for name in ['season-loot-preference.mjs','verify-loot-preference-workbook.py']:shutil.copy2(base/'workbook'/name,d/name)
for name in ['loot-preference-final-contact.jpg','loot-preference-contact.jpg','loot-preference-localization-r1.json','loot-preference-ui-text-r5.json','run-loot-preference-native.py','ended-expanded-inputs-v5.json']:shutil.copy2(base/name,out/name)
shutil.copytree(base/'local-config-r5',out/'local-config-r5')
shutil.copy2(base/'storage-r70/publication-proof.json',out/'publication-proof.json')
shutil.copy2(base/'loot-preference-ui-info-r2/fr_1280_c09_info.png',out/'rejected-info-overflow-fr1280.png')
for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
 assert (repo/'server/config/generated'/name).read_bytes()==(repo/'client/data/generated'/name).read_bytes()
 assert (repo/'server/config/archive/season-v1-config-4'/name).read_bytes()==subprocess.check_output(['git','show','HEAD:server/config/generated/'+name])
publication=read(out/'publication-proof.json')
result={'status':'C09_completed_current_scope','C09_complete':True,'whole_goal_complete':False,'configuration':publication,'workbook_preservation':proof,'domain_current_targeted_passed':581,'new_preference_domain_cases':sum('SeasonLootPreferenceTests/' in k for k in domain),'server_current_targeted_union_passed':298,'server_union_not_single_full_run':True,'r71_passed':294,'r71_failed':4,'r71_skipped':2,'r72_corrected_passed':4,'runtime_sources_identical_between_r71_and_r72':196,'native_current_checks':213,'ui':{'unique_final_frames':132,'all_captured_frames_including_rejected':231,'final_checks_passed':checks,'new_parent_boundary_checks':99,'locales':11,'widths':[960,1280,1920],'runs':runs,'private_desktop_only':True,'whole_project_E02_complete':False,'manual_reviewed':['en960 preference','hi1920 default','ar960 locked','fr1280 final info','ar960 final info','ru1920 preference'],'branch_reuse':'Only the info dialog and its test bounds/cleanup changed after first UI batches. Default/selection/locked visual paths are unchanged; final info33 frames replace all earlier info frames.'},'retained_failures':[{'stage':'local-config-r5','SDK_started':False,'reason':'Local resource admission below6GiB+1GiB; cloud compiler used within unchanged guards'},{'stage':'r71','cases':4,'reason':'Two historical D5 base-drop assertions omitted2.2x/4x factors; two action-recovery fixtures omitted original preparation. Test inputs corrected; runtime checks not relaxed.'},{'stage':'loot-preference-native-r1','reason':'Borrowed suite depended on isolated-only languages.json. It now iterates all eleven actual registered packs; interrupted test cleanup caused the retained exit leaks, final native run is clean.'},{'stage':'loot-preference-ui-b-r1/info','automated_checks_passed':True,'visual_accepted':False,'reason':'Oversized flat info panel, excessive blank area; replaced with existing ornate panel and one Close button.'},{'stage':'loot-preference-ui-info-r2','automated_checks_passed':True,'visual_accepted':False,'reason':'French representative visibly overflowed; old geometry assertions did not check parent bounds.'},{'stage':'loot-preference-ui-info-r3','failed_checks':57,'reason':'New parent-bound assertions exposed Label minimum-height expansion. Authored text rectangles now stay fixed and wrapped; final99 boundary checks pass.'}],'retained_skips':{'count':2,'scope':'A05 dedicated process fault tests; F02 pending; not counted as passed'},'source_semantics':['Preference defaults from frozen table; initial candidateFire follows first reusable fire-theme direction, C16 full theme implementation still separate','Prepared preference is optional in old requests, explicit in new snapshots, owned per player and immutable in room','Durable preparation is checked during queue launch and every room snapshot read/save/recovery/owned-terminal path','Natural choice/treasure equipment40% preference and four15% alternatives; no combat bonus','No extra reward RNG draws; separate base loot, reward, bot, duel and player streams retained; crafting uses independent cryptographic RNG','Actual configuration4 archive retains absent preference; new fields are additive and null omitted from old request hash inputs'],'public_archive_sha256':archives,'production_deployed':False,'production_restarted':False,'season_activated':False,'capacity_retested':False,'complete_gameplay_routes_added':0,'B05_routes_used':291,'B05_routes_remaining':9,'remaining':['C10 bot projection/real-loot provenance and once-per-human reward','C11-C16 source/economy/theme gates','Remaining A/D/E/F, final integration and deployment']}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'C09_complete':True,'domain':581,'server_union':298,'native':213,'final_frames':132,'final_checks':checks,'captured_frames':captured}))
