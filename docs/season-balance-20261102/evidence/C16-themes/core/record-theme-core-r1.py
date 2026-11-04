from pathlib import Path
import gzip,hashlib,json,shutil,xml.etree.ElementTree as E
repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/C16-themes/core'
assert not e.exists();e.mkdir(parents=True)
def copy(src,dest=None):
 p=b/src;q=e/(dest or src);assert p.is_file(),p
 q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for name in ['local-config-r12','local-theme-domain-r1','local-theme-domain-r2','local-theme-domain-r3','local-theme-config-r1','local-theme-config-r2','local-theme-server-build-r1','theme-native-r1','theme-native-r2','theme-native-r3','theme-wire-r1']:
 for p in (b/name).iterdir():
  if p.is_file() and p.suffix in ['.json','.jsonl','.log','.gd','.bin']:copy(p.relative_to(b).as_posix())
 for p in (b/name/'results').glob('*.trx'):copy(p.relative_to(b).as_posix())
for p in (b/'storage-r90').iterdir():
 if p.is_file() and p.suffix in ['.json','.log','.py']:copy(p.relative_to(b).as_posix())
shutil.copytree(b/'storage-r90/public',e/'storage-r90/public')
for p in b.iterdir():
 if p.is_file() and p.suffix=='.py' and ('theme' in p.name) and 'pilot' not in p.name:copy(p.name)
for n in ['workbook/season-themes.mjs','workbook/season-themes-r2.mjs','workbook/verify-theme-workbook.py','workbook/verify-theme-workbook-r2.py']:copy(n)
for stage in ['season-themes','season-themes-r2']:
 root=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79'/stage
 for p in root.iterdir():
  if p.is_file() and p.suffix in ['.json','.ndjson','.png']:copy(p.relative_to(b).as_posix(),'workbook/'+stage+'/'+p.name)
ui=e/'ui';ui.mkdir();raw=[];final=[];runtime=None;checks=0
runs=['theme-ui-en-r1','theme-ui-en-r2','theme-ui-en-r3','theme-ui-a-r1']+[f'theme-ui-group{i}-r1' for i in range(1,6)]
for run in runs:
 dst=ui/run;dst.mkdir()
 for p in (b/run).iterdir():
  if not p.is_file() or p.suffix=='.png':continue
  if p.name in ['review.json','frames.original.jsonl']:(dst/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
  else:shutil.copy2(p,dst/p.name)
 rows=[dict(run=run,file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (b/run).glob('*.png')];raw.extend(rows)
 if 'group' not in run:continue
 report=json.loads((b/run/'review.json').read_text(encoding='utf-8'));t=json.loads((b/run/'terminal.original.json').read_text(encoding='utf-8'))
 assert report['render_capture_complete'] and not report['legacy_layout_observations'] and all(report['checks'].values())
 assert t['native_exit']==0 and t['source_unchanged'] and t['all_checked_threads_private'] and t['desktop_switch_calls']==0
 pin=json.loads((b/run/'source-pin.original.json').read_text(encoding='utf-8'));current={n:h for n,h in pin.items() if not n.replace(chr(92),'/').startswith('client/tests/')}
 if runtime is None:runtime=current
 else:assert runtime==current
 for n,h in current.items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h,n
 final.extend(rows);checks+=len(report['checks'])
assert len(raw)==471 and len(final)==330 and len({r['file'] for r in final})==330 and checks==27464
(ui/'raw-frame-manifest.json').write_text(json.dumps(raw,indent=2)+'\n',encoding='utf-8')
(ui/'final-frame-manifest.json').write_text(json.dumps(dict(frames=final,checks=checks,runtime_sources_identical=True,actual_full_game_matches=0,balance_criteria_accepted=False),indent=2)+'\n',encoding='utf-8')
representatives={'theme-ui-group1-r1':['ar_960_c16_wood_info.png'],'theme-ui-group2-r1':['hi_1280_c16_earth_info.png','ru_960_c16_metal_info.png'],'theme-ui-group3-r1':['fr_960_c16_water_info.png','en_960_c16_wood_regen.png'],'theme-ui-group4-r1':['zh-CN_1920_c16_map.png'],'theme-ui-group5-r1':['es_960_c16_pvp.png']}
manual={}
for run,names in representatives.items():
 for n in names:
  target=ui/('final-'+n);shutil.copy2(b/run/n,target);manual[n]=dict(source=run,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
(ui/'manual-review.json').write_text(json.dumps(dict(reviewer='assistant visual inspection recorded during original run',representatives=manual,human_experience_test=False,observations=['No clipping, overlap or unreadable glyphs in inspected final representatives.','Actual regeneration HP is displayed; it is not a basis-point value.','Original 2D font, panel and border style retained.','Mage 80/70 is a legal overcap sentinel.','Encounter balance remains separate and unaccepted.']),indent=2)+'\n',encoding='utf-8')
cases={};counts=[]
for file in [b/'local-theme-config-r2/results/bot-domain.trx',b/'storage-r90/public/season-theme-server.trx']:
 count=0
 for node in E.parse(file).iter():
  if node.tag.endswith('UnitTestResult'):
   assert node.get('outcome')=='Passed';count+=1;cases[node.get('testName')]=dict(source=str(file.relative_to(b)),test_id=node.get('testId'),outcome='Passed')
 counts.append(count)
assert counts==[94,52] and len(cases)==145
(e/'server-case-union.json').write_text(json.dumps(dict(count=145,union_not_one_physical_run=True,runs=counts,cases=cases),indent=2)+'\n',encoding='utf-8')
for folder in ['theme-native-r3','theme-wire-r1']:
 r=json.loads((b/folder/'result.json').read_text(encoding='utf-8'));assert r['exit']==0 and not r['engine_errors'] and r['source_unchanged']
result=dict(status='C16_mechanisms_UI_verified_combat_balance_pending',C16_complete=False,whole_goal_complete=False,completed_items=19,configuration='season-v1-config-12',workbook_sha256='5b6153af4fa777857a2ae4d17a3a6a3d91b54c49bf6c8f420fbea1e1a630564e',content_hash='e6f2083dd671e321c166296063a25c7794896399a15664febf98bacb457a876a',binary_sha256='e9e38944f668d7e453590fe62702774561033d70b96267f9d1822a47b3c61118',domain_passed=108,server_union_passed=145,native_checks=75,generated_CSharp_wire_checks=7,actual_network_wire_files=0,UI=dict(final_frames=330,raw_frames_retained=471,checks=27464,locales=11,widths=[960,1280,1920],private_inactive_desktop=True),owned_SDK_removed='f5af34b8960360a4124dd0f8858090230c78b3e1286457af250fa5a4dbf63fbd',production_deployed=False,production_restarted=False,season_activated=False,new_full_routes=0,capacity100_retest=False,B05_budget='291/300',combat_acceptance='pending: original starter pilot failed; mature mixed observations are separate',external_original_evidence_root=str(b))
(e/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()}
(e/'manifest.json').write_text(json.dumps(dict(files=manifest,external_full_evidence_root=str(b),all_original_PNGs_retained_with_hashes=True),indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
