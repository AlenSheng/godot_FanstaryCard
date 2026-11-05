from pathlib import Path
import json,hashlib,shutil,xml.etree.ElementTree as E
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');target=repo/'docs/season-balance-20261102/evidence/C01-refresh-price-ui';assert not target.exists()
final=['refresh-price-ui-en-r4','refresh-price-ui-group1-r4','refresh-price-ui-group2-r4','refresh-price-ui-group3-r4']
previous=['refresh-price-ui-en-r1','refresh-price-ui-en-r2','refresh-price-ui-group1-r1','refresh-price-ui-group2-r1','refresh-price-ui-group3-r1','refresh-price-ui-en-r3','refresh-price-ui-group1-r2','refresh-price-ui-group2-r2','refresh-price-ui-group3-r2','refresh-price-ui-group1-r3','refresh-price-ui-group2-r3']
frames=[];checks=0;languages=set();final_inputs=None
for stage in final:
 o=b/stage;terminal=json.loads((o/'terminal.original.json').read_text(encoding='utf-8'));d=json.loads((o/'review.json').read_text(encoding='utf-8'))
 assert terminal['native_exit']==0 and terminal['stop_reason'] is None and terminal['source_unchanged'] and terminal['desktop_switch_calls']==0 and terminal['all_checked_threads_private']
 cleanup=json.loads((o/'desktop-cleanup.original.json').read_text(encoding='utf-8'));assert cleanup['own_thread_restored'] and cleanup['owned_desktop_closed'] and cleanup['desktop_switch_calls']==0
 assert d['render_capture_complete'] and d['screenshots']==d['expected_frames'] and not d['legacy_layout_observations'] and not any(x is False for x in d['checks'].values())
 pin=json.loads((o/'source-pin.original.json').read_text(encoding='utf-8'))
 if final_inputs is None:final_inputs=pin
 else:assert pin==final_inputs
 assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
 for p in sorted(o.glob('*.png')):frames.append(dict(run=stage,file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 checks+=len(d['checks']);languages.update(d['languages'])
assert len(frames)==99 and len(languages)==11 and checks==5145
raw_frames=[dict(run=stage,file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for stage in previous+final for p in sorted((b/stage).glob('*.png'))]
assert len(raw_frames)==354
selected=[]
for stage in previous+final:
 selected += [p for p in (b/stage).iterdir() if p.is_file() and p.suffix in ['.json','.jsonl','.log']]
for stage in ['local-refresh-config-build-r1','local-refresh-config-core-r1','local-config-r13']:
 selected += [p for p in (b/stage).iterdir() if p.is_file() and p.suffix in ['.json','.log']]
 selected += list((b/stage/'results').glob('*.trx'))
selected += list((b/'refresh-config-http-r1').iterdir())
for name in ['result.json','native-result.json','source-pin.json','import.original.log','tests.original.log','data/config_bundle.gd','tests/test_reward_refresh_config.gd','run.gd','project.godot']:
 selected.append(b/'refresh-config-native-r1'/name)
for name in ['before.png','after.png','artifact-before.original.log','artifact-edit.original.log','preservation-proof.json','FantasyCard_Config.before.xlsx','FantasyCard_Config.xlsx']:
 selected.append(b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/refresh-prices-r1'/name)
selected += [b/'workbook/refresh-prices.mjs',b/'workbook/verify-refresh-prices-r1.py',b/'workbook/verify-preservation.py',b/'workbook/verify-styles.py']
selected += list(b.glob('*refresh-config*.py'))+list(b.glob('*artifact-refresh*.py'))+list(b.glob('*refresh-price-ui*.py'))
selected += [b/'workbook-dimensions-validation-proof.json',b/'title-art-analysis.original.json',b/'refresh-config-native-comment-delta.json',b/'refresh-price-final-source-pin.json',b/'refresh-price-final-source-pin-r2.json',b/'refresh-price-final-source-pin-r3.json',b/'refresh-price-final-source-pin-r4.json']
manual=[('refresh-price-ui-en-r4','en_960_refresh_original.png'),('refresh-price-ui-en-r4','en_960_refresh_unavailable.png'),('refresh-price-ui-group1-r4','ar_960_refresh_original.png'),('refresh-price-ui-group1-r4','hi_1280_refresh_exhausted.png'),('refresh-price-ui-group1-r4','zh-CN_1920_refresh_unavailable.png'),('refresh-price-ui-group3-r4','ru_960_refresh_exhausted.png'),('refresh-price-ui-group3-r4','ja_1280_refresh_original.png'),('refresh-price-ui-group2-r4','fr_1920_refresh_unavailable.png')]
selected += [b/stage/name for stage,name in manual]
for p in set(selected):
 assert p.is_file(),p
 q=target/p.relative_to(b);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);assert q.read_bytes()==p.read_bytes()
(target/'final-frame-manifest.json').write_text(json.dumps(dict(frames=frames,checks=checks,languages=sorted(languages),widths=[960,1280,1920],states=['original_price','exhausted','original_unavailable'],manual_representatives=[dict(run=s,file=n) for s,n in manual],all_original_pngs_retained_on_G=True),indent=2)+'\n',encoding='utf-8')
(target/'all-original-frame-manifest.json').write_text(json.dumps(dict(frames=raw_frames,total=354,final=99,previous=255,previous_visually_rejected_despite_automatic_checks=True),indent=2)+'\n',encoding='utf-8')
proof=json.loads((b/'local-config-r13/config-preservation-proof.json').read_text(encoding='utf-8'));workbook=json.loads((b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/refresh-prices-r1/preservation-proof.json').read_text(encoding='utf-8'))
result=dict(status='original_reward_refresh_price_and_three_UI_states_verified_overall_open',overall_complete=False,completed_items=20,C01_complete=False,E01_complete=False,E02_complete=False,
 version=proof['version'],content_hash=proof['content_hash'],binary_sha256=proof['binary_sha256'],workbook_sha256=proof['workbook_sha256'],sheets_preserved=36,old_values_checked=18822,old_styles_checked=19684,formulas_preserved=8,native_tables_preserved=2,only_cell_changed='LootRules!E4: server -> both',data_rows_unchanged=True,prices=[60,180,450],original_config12_archived_byte_identically=True,
 dotnet_final_passed=6,dotnet_final_failed=0,native_passed_checks=45,native_failed_checks=0,native_comment_only_reuse_boundary='refresh-config-native-comment-delta.json',CSharp_real_typed_response_encoding=True,actual_HTTP_network_not_claimed=True,
 UI_final_frames=99,UI_final_checks=checks,UI_languages=sorted(languages),UI_widths=[960,1280,1920],UI_states=3,title_font_size=32,title_minimum_physical_pixels=16,title_source_aspect=4,previous_UI_raw_frames=255,all_raw_frames=354,first_failure='Fixture reset reused the previous unavailable room card map; three original frames retained. Lobby fixtures now read the formal lobby catalog.',manual_rejection='The next99 automatic passes did not grant final acceptance: Japanese heading approached decorative border. The next narrowed plate failed18 French/Portuguese checks. A later candidate still assumed5:1 although the source image is4:1. Final layout uses the real source aspect, fixed32px type and up to2 complete lines; all99 frames rerendered with physical16px at960 and measured text bounds.',
 missing_original_policy='Show localized unavailable quote and disable refresh, never substitute a current lobby price.',old_archive_policy='Decode exact refresh_gold from verified original full bundles even with old Server scope; leave other Server columns filtered. Full old bytes and historical hashes are immutable.',
 original_evidence_root=str(b),all_raw_pngs_and_binary_inputs_retained_on_G=True,production_deployed=False,production_restarted=False,cloud_SDK_started=False,new_full_routes=0,capacity100_retest=False,B05_total=291,C16_total=121,
 remaining='Other source audit, original preparation catalog previews and broader E01/E02; C15 item rewards, C16 balance, D/F gates remain incomplete.')
(target/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
(target/'manifest.json').write_text(json.dumps(dict(files=manifest,source_unchanged=True,large_original_outputs_retained_on_G=True),indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(evidence_files=len(manifest)+1,final_frames=99,checks=checks,raw_frames=len(raw_frames))))
