from pathlib import Path
import json,hashlib,shutil
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');target=repo/'docs/season-balance-20261102/evidence/A04-client-preparation-config-r1';assert not target.exists()
final=['preparation-source-ui-en-r2','preparation-source-ui-group1-r1','preparation-source-ui-group2-r2','preparation-source-ui-group3-r1','preparation-source-ui-menu-final-r1'];previous=['preparation-source-ui-en-r1','preparation-source-ui-group2-r1'];frames=[];checks=0;langs=set();reuse=[];included_checks={}
old_native=b/'preparation-client-native-r3'
for stage in final:
 o=b/stage;t=json.loads((o/'terminal.original.json').read_text(encoding='utf-8'));r=json.loads((o/'review.json').read_text(encoding='utf-8'));assert t['native_exit']==0 and t['stop_reason'] is None and t['source_unchanged'] and t['all_checked_threads_private'] and t['desktop_switch_calls']==0
 clean=json.loads((o/'desktop-cleanup.original.json').read_text(encoding='utf-8'));assert clean['owned_desktop_closed'] and clean['own_thread_restored']
 assert r['render_capture_complete'] and not r['legacy_layout_observations'] and not any(x is False for x in r['checks'].values())
 pins=json.loads((o/'source-pin.original.json').read_text(encoding='utf-8'))
 for raw_name,h in pins.items():
  n=raw_name.replace('\\','/')
  if hashlib.sha256((repo/n).read_bytes()).hexdigest()==h:continue
  if n in ['client/ui/reference_ui.gd','client/tests/ui_visual_review.gd']:
   assert stage!='preparation-source-ui-menu-final-r1'
   old=b/('preparation-menu-style-before-reference.original.gd' if n.endswith('reference_ui.gd') else 'preparation-menu-style-before-review.original.gd');assert hashlib.sha256(old.read_bytes()).hexdigest()==h;reuse.append(dict(run=stage,unrendered_popup_style_only=n,prior_source_bytes_verified=True));continue
  assert n in ['client/data/locales/pt.json','client/data/locales/ru.json'];old=old_native/n.removeprefix('client/');assert hashlib.sha256(old.read_bytes()).hexdigest()==h
  a=json.loads(old.read_text(encoding='utf-8'));z=json.loads((repo/n).read_text(encoding='utf-8'));before=a['strings'].pop('preparation_backpack_details');after=z['strings'].pop('preparation_backpack_details');assert a==z and n.split('/')[-1][:-5] not in r['languages']
  reuse.append(dict(run=stage,unrendered_locale=n,before=before,after=after,all_other_source_bytes_unchanged=True))
 for p in sorted(o.glob('*.png')):
  if stage!='preparation-source-ui-menu-final-r1' and p.name.endswith('_prep_source_menu.png'):continue
  frames.append(dict(run=stage,file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 for f in r['frames']:
  if stage!='preparation-source-ui-menu-final-r1' and f['name'].endswith('_prep_source_menu'):continue
  included_checks.update(f['checks'])
 langs.update(r['languages'])
checks=len(included_checks)
assert len(frames)==264 and len(langs)==11 and not any(v is False for v in included_checks.values())
raw=[dict(run=s,file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for s in previous+final for p in sorted((b/s).glob('*.png'))];assert len(raw)==377
selected=[]
for stage in previous+final+['preparation-source-scripts-r1','preparation-source-scripts-r2','preparation-source-scripts-r3','preparation-source-scripts-r4','preparation-source-scripts-r5']:
 selected += [p for p in (b/stage).iterdir() if p.is_file() and p.suffix in ['.json','.jsonl','.log']]
for stage in ['local-preparation-client-build-r1','local-preparation-client-build-r2','preparation-client-regression-r1','preparation-client-native-r1','preparation-client-native-r2','preparation-client-native-r3','preparation-client-native-r4']:
 o=b/stage
 if o.exists():selected += [p for p in o.iterdir() if p.is_file() and p.suffix in ['.json','.log','.gd','.godot']]
for stage in ['runtime-r104','runtime-r105']:
 o=b/stage;assert json.loads((o/'collection-audit.json').read_text())['state']=='exited'
 selected += [p for p in o.rglob('*') if p.is_file() and p.name not in ['payload.tar.gz','public-evidence.tar.gz','delta.tar.gz','transport-stream-r3.bin']]
selected += list((b/'preparation-client-http-r1').iterdir())
selected += [b/'preparation-menu-style-before-reference.original.gd',b/'preparation-menu-style-before-review.original.gd']
for pattern in ['*preparation-client*.py','*preparation-source*.py','preparation-source-localization*.json','preparation-source-locale-length-fix.original.json','runtime-r103-input-retirement-r3.original.log']:
 selected += list(b.glob(pattern))
manual=[('preparation-source-ui-en-r2','en_960_prep_source_owned.png'),('preparation-source-ui-en-r2','en_1280_prep_source_locked.png'),('preparation-source-ui-en-r2','en_1920_prep_source_deck_bottom.png'),('preparation-source-ui-group1-r1','ar_960_prep_source_owned.png'),('preparation-source-ui-group1-r1','hi_1280_prep_source_unavailable.png'),('preparation-source-ui-group1-r1','zh-CN_1920_prep_source_deck.png'),('preparation-source-ui-group2-r2','pt_960_prep_source_owned.png'),('preparation-source-ui-menu-final-r1','fr_1280_prep_source_menu.png'),('preparation-source-ui-group3-r1','ru_960_prep_source_owned.png'),('preparation-source-ui-group3-r1','ja_1920_prep_current_d1.png')]
selected += [b/s/n for s,n in manual]
for p in set(selected):
 assert p.is_file(),p
 q=target/p.relative_to(b);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);assert q.read_bytes()==p.read_bytes()
(target/'final-frame-manifest.json').write_text(json.dumps(dict(frames=frames,checks=checks,languages=sorted(langs),widths=[960,1280,1920],screens=8,locale_scoped_reuse=reuse,manual_representatives=[dict(run=s,file=n) for s,n in manual],full_originals_retained_on_G=True),indent=2)+'\n',encoding='utf-8')
(target/'all-original-frame-manifest.json').write_text(json.dumps(dict(frames=raw,total=377,final=264,previous=113),indent=2)+'\n',encoding='utf-8')
result=dict(status='original_preparation_client_subchain_verified_overall_open',completed_items=20,whole_goal_complete=False,A03_complete=False,A04_complete=False,E01_complete=False,E02_complete=False,
 actual_PG_final_passed=1,actual_PG_cases=['owned','borrowed'],actual_PG_initial_failed=1,PG_inputs_files=10,PG_source_configs='Current lobby13 with active-preparation-archive source,Wood preference,free21,zero-based slot12C30,controlD1Green not formalD1Purple',
 native_final_passed=255,native_final_failed=0,native_initial_failures='Two combined array comparisons in r1/r2 rejected typed-array vs JSON-number-array identity; values recorded equal, replaced with exact per-slot comparisons; production code unchanged by that test correction.',
 UI_final_frames=264,UI_final_checks=checks,UI_languages=sorted(langs),UI_widths=[960,1280,1920],UI_screens=8,UI_all_original_frames=377,UI_prior_failure='8frame pilot had one generic Deck-page classifier applied to a preparation text preview; fixed by actual screen scoping.72frame es/fr/pt run had42 Portuguese paid-bag detail clipping checks; new Portuguese/Russian detail strings compacted. Menu-only33 frames restyled to dark/gold and revalidated, all earlier files retained.',
 armor_contract='D-tier projects cards/signatureweapon only. Real +5 armor is preserved in the authoritative preparation snapshot and preview; first wrong +1 fixture and uncommitted draft were corrected with GDD/source evidence.',
 behavior=['Exact original preparation/active season config cache, identity/origin/epoch fencing and concurrent immutable hash protection','Derived backpack capacities and safe indexes, original loot default and borrowed template','Owned and virtual deck previews with original card text and actual/effective card+weapon levels','Missing original disables confirmation/matching while retaining known preparation and cancellation; other lobby data remains usable','Preparation portrait/numerical class follows the locked snapshot instead of later profile selection'],
 production_deployed=False,production_restarted=False,capacity100_retest=False,cloud_SDK_started=False,new_full_routes=0,B05_total=291,C16_total=121,
 remaining='Comprehensive economic/source audit, broader E01/E02, approved C15 item/cosmetic implementation, C16 balance and D/F gates.',original_evidence_root=str(b))
(target/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
m={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()};(target/'manifest.json').write_text(json.dumps(dict(files=m,raw_originals_preserved=True),indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(files=len(m)+1,final_frames=264,checks=checks,total_raw=len(raw))))
