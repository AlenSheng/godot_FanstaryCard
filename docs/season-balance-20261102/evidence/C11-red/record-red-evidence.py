from pathlib import Path
import json,hashlib,shutil,gzip,xml.etree.ElementTree as ET
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=repo/'docs/season-balance-20261102/evidence/C11-red';assert not out.exists()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
def cases(path):
 t=ET.parse(path);names={n.attrib['id']:n.find('t:TestMethod',ns).attrib['className'] for n in t.findall('.//t:UnitTest',ns)}
 return {names[n.attrib['testId']]+'/'+n.attrib['testName']:n.attrib['outcome'] for n in t.findall('.//t:UnitTestResult',ns)}
def runtime_pin(run):return {n:h for n,h in read(base/run/'source-pin.json').items() if n.startswith('server/src/') and n.endswith(('.cs','.sql'))}
domain=cases(base/'local-red-domain-r3/results/bot-domain.trx');assert list(domain.values()).count('Failed')==1
domain.update(cases(base/'local-red-domain-r6/results/bot-domain.trx'));assert len(domain)==614 and set(domain.values())=={'Passed'}
server=cases(base/'local-red-server-r5/results/bot-domain.trx');assert len(server)==248 and set(server.values())=={'Passed'}
pg=cases(base/'local-red-postgres-r1/results/bot-real-custody.trx');assert list(pg.values()).count('Failed')==1
pg.update(cases(base/'local-red-postgres-r2/results/bot-real-custody.trx'));pg.update(cases(base/'local-red-postgres-r3/results/bot-real-custody.trx'));assert len(pg)==9 and set(pg.values())=={'Passed'}
server.update(pg);assert len(server)==257
for n,h in read(base/'local-red-server-r5/source-pin.json').items():assert sha(repo/n)==h,n
for n,h in read(base/'local-red-domain-r6/source-pin.json').items():assert sha(repo/n)==h,n
for n,h in read(base/'local-red-postgres-r3/source-pin.json').items():assert sha(repo/n)==h,n
for name in ['local-red-postgres-r1','local-red-postgres-r2','local-red-postgres-r3']:assert read(base/name/'owned-tunnel-terminal.json')['exit_code']==0
final_ui=['red-ui-a-r3','red-ui-b-r1','red-ui-c-r1'];old_ui=['red-ui-a-r1','red-ui-a-r2'];frames={};checks=0;raw_frames=0;ui_runs={}
for run in old_ui+final_ui:
 d=read(base/run/'review.json');terminal=read(base/run/'terminal.original.json');raw_frames+=d['screenshots']
 failed=sum(not v for v in d['checks'].values());ui_runs[run]={'frames':d['screenshots'],'checks':len(d['checks']),'failed':failed,'layout_errors':len(d['legacy_layout_observations']),'final':run in final_ui,'native_exit':terminal['native_exit']}
 assert terminal['all_checked_threads_private'] and terminal['desktop_switch_calls']==0 and terminal['source_unchanged']
 if run in final_ui:
  assert not failed and not d['legacy_layout_observations'] and terminal['native_exit']==0
  checks+=len(d['checks'])
  for frame in d['frames']:
   name=frame['name']+'.png';p=base/run/name;assert name not in frames and p.is_file();frames[name]={'run':run,'sha256':sha(p),'bytes':p.stat().st_size}
  for n,h in read(base/run/'source-pin.original.json').items():
   if isinstance(h,str) and len(h)==64 and (repo/n).is_file():assert sha(repo/n)==h,n
assert len(frames)==231 and raw_frames==396 and checks==5973
assert read(base/'red-native-r1/checks.json')['checks']==224 and read(base/'red-native-r2/checks.json')['checks']==11
for n,h in read(base/'red-native-r2/source-pin.json').items():assert sha(repo/n)==h,n
assert read(base/'red-native-r2/checks.json')['ok'] and read(base/'red-interop-r1/result.json')['ok']
assert len(read(base/'red-interop-r1/godot-checks.json')['checks'])==14 and read(base/'red-localization-audit-r1.json')['ok']
configuration=read(base/'red-configuration-proof.json');assert configuration['version']=='season-v1-config-7'
wb=base/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/red-mint';preservation=read(wb/'preservation-proof.json');assert sha(repo/'config/FantasyCard_Config.xlsx')==preservation['after_sha256']
out.mkdir(parents=True)
for run in ['local-red-build-r1','local-red-build-r2','local-red-actor-r1']+['local-red-domain-r'+str(i) for i in range(1,7)]+['local-red-server-r'+str(i) for i in range(1,6)]+['local-red-postgres-r'+str(i) for i in range(1,4)]+['local-config-r7','red-native-r1','red-native-r2','red-interop-r1']:
 src=base/run;target=out/run;target.mkdir()
 for p in src.rglob('*'):
  rel=p.relative_to(src)
  if p.is_file() and not {'build','obj','bin','user-profile','.godot','runtime'}.intersection(rel.parts) and p.suffix not in ['.dll','.pdb','.exe']:
   dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
for run in old_ui+final_ui:
 target=out/run;target.mkdir()
 for p in (base/run).iterdir():
  if p.is_file() and p.suffix in ['.json','.jsonl','.log']:
   if p.name in ['review.json','frames.original.jsonl']:(target/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
   else:shutil.copyfile(p,target/p.name)
workbook=out/'workbook';workbook.mkdir()
for n in ['SeasonRedRules.png','preservation-proof.json','FantasyCard_Config.xlsx.inspect.ndjson']:shutil.copyfile(wb/n,workbook/n)
for n in ['season-red-mint.mjs','verify-red-mint-workbook.py']:shutil.copyfile(base/'workbook'/n,workbook/n)
for n in ['red-configuration-proof.json','red-localization-audit-r1.json','run-red-native.py','run-red-native-targeted.py','run-red-interop-r1.py','finish-red-interop-r1.py','export-red-config-r7.py']+[f'run-local-red-postgres-r{i}.py' for i in range(1,4)]:shutil.copyfile(base/n,out/n)
raw_manifest={run+'/'+p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for run in old_ui+final_ui for p in (base/run).glob('*.png')};assert len(raw_manifest)==396
(out/'raw-frame-manifest.json').write_text(json.dumps(raw_manifest,indent=2)+'\n')
for source,target in [('red-ui-a-r1/zh-CN_960_c11_pending.png','rejected-clipped-red-description.png'),('red-ui-a-r2/ru_960_c11_pending.png','rejected-long-russian-replacement.png'),('red-ui-c-r1/ar_960_c11_confirm_bottom.png','final-arabic-confirm-bottom.png')]:shutil.copyfile(base/source,out/target)
(out/'final-frame-manifest.json').write_text(json.dumps(dict(sorted(frames.items())),indent=2)+'\n')
(out/'domain-case-union.json').write_text(json.dumps(domain,indent=2)+'\n');(out/'server-case-union.json').write_text(json.dumps(server,indent=2)+'\n')
current={p.relative_to(repo).as_posix():sha(p) for root in ['server/src','client/ui','client/network','client/data'] for p in (repo/root).rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.gd','.json','.proto','.bytes','.txt','.sha256'] and not {'bin','obj','build','.godot'}.intersection(p.parts)}
(out/'current-runtime-files.json').write_text(json.dumps(current,indent=2)+'\n')
prior=runtime_pin('local-red-postgres-r1');delta=[n for n,h in prior.items() if sha(repo/n)!=h];assert sorted(delta)==['server/src/FantasyCard.Domain/Rooms/BattleRoom.cs','server/src/FantasyCard.Server/Realtime/RoomSnapshotProjection.cs']
result={'status':'C11_completed_current_scope','C11_complete':True,'whole_goal_complete':False,'configuration':configuration,'workbook_preservation':preservation,'domain_targeted_union_passed':614,'domain_union_not_one_physical_run':True,'domain_original_full_passed':610,'domain_original_full_failed':1,'domain_final_focused_passed':20,'server_targeted_union_passed':257,'server_union_not_one_physical_run':True,'server_latest_non_database_passed':248,'database_union_passed':9,'database_original_passed':7,'database_original_failed':1,'native_targeted_union_checks':238,'native_gameplay_and_controller_checks':224,'native_final_changed_UI_controller_checks':11,'interoperability_Godot_checks':14,'interoperability_server_frames':3,'interoperability_Godot_commands':1,'interoperability_is_offline_not_live_network':True,'ui':{'unique_final_frames':231,'raw_frames_including_rejected':396,'final_checks_passed':5973,'locales':11,'widths':[960,1280,1920],'runs':ui_runs,'private_desktop_only':True,'manual_representatives_reviewed':['zh-CN960 pending','zh-CN1920 pending and confirm','ru960 pending and confirm','ar1280 pending bottom','ar960 confirm bottom','hi960 replacement list bottom'],'whole_project_E02_complete':False},'runtime_delta_after_original_database_batch':delta,'delta_verification':'Final20 Domain controls cover real duel/resume/death red custody; current248 server controls cover all affected Rooms/Realtime/Config; final original-mint database case includes real disconnect death and original-item RelicPile settlement. Other seven original database controls plus populated-upgrade case have unchanged mint/quota/migration runtime inputs.','source_semantics':['Only new candidate7 seasonal rooms enable the policy; actual candidate6 original bundle remains archived','D2+ core Boss:independent40/10000 roll; D0/D1 and ordinary choice never mint red; chest disabled and activity does not create red in current enabled rules','Logical economy binding and scope/week primary key shared by Boss/ShopChest/Activity primitive; no season/process/channel key and no rollover','Monday04:00 Shanghai; source season expiry closes a new pending mint; original attempts replay unchanged across weeks','Pending roll and property seed are checkpointed; attempt advisory lock and one PostgreSQL transaction claim quota, create original item, record delivery hold','Real red item holds original ID and attributes before temporary bag; full bag remains pending until explicit replacement and confirmation','Independent pending red may pause for PVP; battle actions remain available, victory restores original choice; disconnect death moves the original into relic custody','No refund for death, transfer or recycle; real original-mint database death settlement preserves RedBoss/mint/source fields','Actor awaits authoritative persistence before ACK; recovery after item transaction but before delivery resolves the original attempt without another mint','Future disabled chest/activity channels are not claimed as live enabled-route tests; their shared quota primitive is tested and their later features remain separate C12-C16 gates'],'retained_failures':[{'run':'local-red-build-r1','reason':'Configuration accessor and analyzer corrections; no tests counted passed'},{'run':'local-red-build-r2','reason':'New actor tests lacked explicit xUnit cancellation tokens; originals retained'},{'run':'local-red-domain-r1','reason':'New test Json options allocation and indexed First analyzer errors; test-only corrections'},{'run':'local-red-domain-r3','passed':610,'failed':1,'reason':'Embedded config contract still expected candidate6; explicit version7 assertion corrected; no runtime rule loosened'},{'run':'local-red-postgres-r1','passed':7,'failed':1,'reason':'New custody fixture used unsupported Destroyed location at the final recycle control; existing Recycled location used, unchanged database check retained; corrected source then extended through actual death/RelicPile settlement'},{'run':'red-ui-a-r1','failed_checks':36,'reason':'Fixed-height red detail text clipped, and Russian button too long; originals retained'},{'run':'red-ui-a-r2','failed_checks':6,'reason':'Scrolling detail fixed clipping; Russian inherited full-bag button still too long; all eleven locales received a short dedicated label'},{'run':'local-red-server-r4','reason':'New projection test constant array violated CA1861; static readonly expected actions corrected'}],'resource_protection':{'local_reserve_GiB':6,'local_startup_GiB':1,'local_admission_samples':3,'cloud_RAM_floor_MiB':500,'cloud_disk_floor_GiB':3,'cloud_disk_fraction':0.05,'cloud_SDK_started':False,'own_SSH_tunnels_exited_normally':3,'other_project_processes_modified':False},'production_database_used':False,'production_deployed':False,'production_restarted':False,'season_activated':False,'capacity_retested':False,'complete_gameplay_routes_added':0,'B05_routes_used':291,'B05_routes_remaining':9,'remaining':['C12-C16 market/shop/activity/progression/theme','Remaining A/D/E/F including full population/season rollover and final integration/deployment/restart']}
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'C11_complete':True,'domain_union':614,'server_union':257,'database_union':9,'native_union':238,'UI_frames':231,'UI_checks':5973}))
