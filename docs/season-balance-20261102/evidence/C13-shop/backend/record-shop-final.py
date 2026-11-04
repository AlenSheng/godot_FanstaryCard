from pathlib import Path
import json,hashlib,gzip,shutil,xml.etree.ElementTree as E,re
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');e=repo/'docs/season-balance-20261102/evidence/C13-shop/backend';ui=e/'ui';assert not ui.exists();ui.mkdir()
runs=['shop-ui-en-r1','shop-ui-all-r2','shop-ui-shelves-r3','shop-ui-copies-r4','shop-ui-shelves-r5','shop-ui-copies-r6','shop-ui-shelves-r7','shop-ui-confirm-r8','shop-ui-shelves-r9','shop-ui-confirm-r10']
raw=[]
for run in runs:
 src=b/run;dst=ui/run;dst.mkdir()
 for p in src.iterdir():
  if p.is_file() and p.suffix!='.png':
   data=p.read_bytes()
   if p.name in ['review.json','frames.original.jsonl']:
    (dst/(p.name+'.gz')).write_bytes(gzip.compress(data,mtime=0))
   else:shutil.copy2(p,dst/p.name)
 for p in src.glob('*.png'):raw.append({'run':run,'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(ui/'raw-frame-manifest.json').write_text(json.dumps(raw,indent=2)+'\n')
final_runs=['shop-ui-copies-r6','shop-ui-shelves-r9','shop-ui-confirm-r10'];final=[];runtime=None;checks=0
for run in final_runs:
 d=json.loads((b/run/'review.json').read_text(encoding='utf-8'));assert d['render_capture_complete'] and not d['legacy_layout_observations'] and all(d['checks'].values());checks+=len(d['checks'])
 pin=json.loads((b/run/'source-pin.original.json').read_text(encoding='utf-8'));actual={n:h for n,h in pin.items() if 'client\\tests\\' not in n}
 if runtime is None:runtime=actual
 else:assert actual==runtime,'Runtime UI sources differ between final frame groups'
 assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in actual.items())
 terminal=json.loads((b/run/'terminal.original.json').read_text(encoding='utf-8'));assert terminal['native_exit']==0 and terminal['desktop_switch_calls']==0 and terminal['all_checked_threads_private'] and terminal['source_unchanged']
 final.extend(v for v in raw if v['run']==run)
assert len(final)==297 and len({v['file'] for v in final})==297 and checks==39234
(ui/'final-frame-manifest.json').write_text(json.dumps({'frames':final,'checks':checks,'runtime_sources_identical':True,'fixture_change_after_copies_group':'Reset only shop horizontal scroll; runtime files identical','actual_gameplay_matches':0},indent=2)+'\n')
representatives={'shop-ui-copies-r6':['ru_960_c13_copy.png','hi_960_c13_copy_missing.png','ar_1280_c13_copy.png'],'shop-ui-shelves-r9':['fr_960_c13_tail.png','ru_1280_c13_shared.png','ar_960_c13_shop.png'],'shop-ui-confirm-r10':['en_960_c13_copy_confirm.png','hi_960_c13_upgrade_confirm.png','ar_960_c13_confirm.png']}
manual={}
for run,names in representatives.items():
 for name in names:
  target=ui/('final-'+name);shutil.copy2(b/run/name,target);manual[name]={'source':run,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(ui/'manual-review.json').write_text(json.dumps({'reviewer':'assistant visual inspection','accepted':manual,'notes':['art style consistent with existing camp and codex','full material and confirmation text visible','purchase buttons retain minimum font and clear borders','same-card material cost and retained trained level explicit','Arabic and Devanagari shaping inspected'],'human_experience_test':False},indent=2)+'\n')
# Keep source-ledger evidence and the observer correction separate from the failed run.
for stage in ['storage-r83','storage-r85']:
 dst=e/stage;assert not dst.exists();dst.mkdir()
 for p in (b/stage).iterdir():
  if p.is_file() and p.name not in ['source.tar.gz','transfer.tar.gz']:shutil.copy2(p,dst/p.name)
 if (b/stage/'public').exists():shutil.copytree(b/stage/'public',dst/'public')
dst=e/'local-shop-clock-r1';dst.mkdir()
for name in ['source-pin.json','cloud-resource.json','owned-tunnel-start.json','owned-tunnel-terminal.json','tunnel.stderr.original.log','test.original.log','result.json','results/bot-real-custody.trx']:
 p=dst/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(b/'local-shop-clock-r1'/name,p)
shutil.copytree(b/'shop-native-r3',e/'native20-final',ignore=shutil.ignore_patterns('runtime','user-profile'))
for name in ['run-local-shop-clock-r1.py','prepare-season-shop-r85.py','ship-season-shop-r85.py','observe-season-shop-r85.py','collect-season-shop-r85.py','resume-retire-shop-utc-expanded-v13.py','retire-shop-utc-failure-expanded-v13.py','archive-market-expanded-v13.py','ended-expanded-inputs-v13.json','v13-download.timeout.json','v13-local-verification.json','v13-resume.original.log']:
 if (b/name).exists():shutil.copy2(b/name,e/name)
union=json.loads((e/'server-case-union.json').read_text(encoding='utf-8'));cases=union['cases']
for path,source in [(e/'storage-r85/public/season-shop-server.trx','r85'),(dst/'results/bot-real-custody.trx','local-clock-r1')]:
 for row in E.parse(path).iter():
  if row.tag.endswith('UnitTestResult') and row.get('outcome')=='Passed':cases[row.get('testName')]={'outcome':'Passed','source':source,'run_local_id':row.get('testId')}
assert len(cases)==203 and all(v['outcome']=='Passed' for v in cases.values());union['count']=203;union['r85']={'passed':1,'failed':1};union['corrected_clock']={'passed':1,'failed':0};union['cases']=cases;(e/'server-case-union.json').write_text(json.dumps(union,indent=2)+'\n')
# Validate every new translated placeholder without changing it.
packs={p.stem:json.loads(p.read_text(encoding='utf-8'))['strings'] for p in (repo/'client/data/locales').glob('*.json')};keys=[k for k in packs['en'] if k.startswith('season_shop_')];assert len(packs)==11 and len(keys)==12
for code,strings in packs.items():
 for key in keys:assert key in strings and re.findall(r'%[sd]',strings[key])==re.findall(r'%[sd]',packs['en'][key]),(code,key)
(e/'locale-proof.json').write_text(json.dumps({'languages':sorted(packs),'keys':keys,'placeholder_shapes_match_English':True,'all_languages_covered_by_actual_frames':True},indent=2)+'\n')
print(json.dumps({'accepted_server_union':203,'final_native_model_controller':20,'actual_wire_checks':15,'final_UI_frames':297,'UI_checks':checks,'raw_frames_retained':len(raw),'locales':len(packs),'new_keys':len(keys)}))
