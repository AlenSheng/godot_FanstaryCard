from pathlib import Path
import json,hashlib,shutil,datetime,xml.etree.ElementTree as ET
repo=Path.cwd();base=Path(__file__).parent;out=repo/'docs/season-balance-20261102/evidence/C01-config17-r1';assert not out.exists();out.mkdir(parents=True)
orig={}
def copy(source,name):
 source=Path(source);data=source.read_bytes();target=out/name;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 orig[name]={'source':str(source),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
for directory,names in {
 'config17-workbook':['scope-comparison-r1.derived.json','style-preservation-r2.derived.json','source16-archive.original.json','build.mjs'],
 'config17-export':['result.json','build-result.json','build.original.log','export.original.log','client-catalog.original.log'],
 'config17-native-r1':['result.json','build-and-tests.original.log','results/contracts.trx','source-pin.json'],
 'config17-native-r2':['result.json','build-and-tests.original.log','results/contracts.trx','source-pin.json'],
 'config17-godot-r1':['result.json','tests.original.log'],
 'config17-godot-r2':['result.json','tests.original.log','cases.original.json'],
 'config17-ui-pilot-en-r1':['terminal.original.json','review.json','frames.original.jsonl'],
 'config17-ui-final-r1-ar':['terminal.original.json','review.json','frames.original.jsonl']}.items():
 for name in names:copy(base/directory/name,directory+'/'+name)
for p in (base/'config17-native-r2/wire').glob('*.json'):copy(p,'wire/'+p.name)
copy(base/'config17-ui-final-r1.plan.original.json','ui/plan-r1.original.json')
copy(base/'config17-ui-final-r2.plan.original.json','ui/plan-r2.original.json')
first=json.loads((base/'config17-ui-final-r1.plan.original.json').read_bytes());second=json.loads((base/'config17-ui-final-r2.plan.original.json').read_bytes());frames=[];checks=0
groups=[g for g in first['groups'] if g['locale'] not in ['ar','ja','ko','ru']]+second['groups']
assert len(groups)==11 and len({g['locale'] for g in groups})==11
current_pin={k.replace('\\','/'):v for k,v in json.loads((Path(second['groups'][0]['output'])/'source-pin.original.json').read_bytes()).items()}
old_ui=(repo/'client/tests/ui_visual_review.gd').read_text(encoding='utf-8').replace('label.text.contains(Palette.system_display_text(expected.replace(" · ", "\\n")))','label.text.contains(expected.replace(" · ", "\\n"))')
reuse=[]
for group in groups:
 folder=Path(group['output']);terminal=json.loads((folder/'terminal.original.json').read_bytes());review=json.loads((folder/'review.json').read_bytes())
 assert terminal['native_exit']==0 and terminal['source_unchanged'] and review['screenshots']==21 and all(v is True for v in review['checks'].values())
 pin={k.replace('\\','/'):v for k,v in json.loads((folder/'source-pin.original.json').read_bytes()).items()}
 assert {k:v for k,v in pin.items() if k!='client/tests/ui_visual_review.gd'}=={k:v for k,v in current_pin.items() if k!='client/tests/ui_visual_review.gd'}
 if group in first['groups']:
  assert hashlib.sha256(old_ui.encode()).hexdigest()==pin['client/tests/ui_visual_review.gd']
  reuse.append(group['locale'])
 checks+=len(review['checks'])
 for name in ['terminal.original.json','review.json','frames.original.jsonl','source-pin.original.json','headless-script-review.json']:
  copy(folder/name,'ui/'+group['locale']+'/'+name)
 for p in sorted(folder.glob('*.png')):frames.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size,final=True))
for p in sorted((base/'config17-ui-pilot-en-r1').glob('*.png')):frames.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size,final=False))
for p in sorted((base/'config17-ui-final-r1-ar').glob('*.png')):frames.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size,final=False))
assert sum(x['final'] for x in frames)==231 and len(frames)==273
(out/'ui/reuse-boundary.derived.json').write_text(json.dumps(dict(reused_locales=reuse,reused_frames=147,new_r2_frames=84,product_source_bytes_equal=True,only_ui_test_assertion_changed=True,old_test_source_hash_checked_by_reconstruction=True,reconstructed_text_is_not_an_original_log=True),indent=2)+'\n')
(out/'ui/frame-manifest.derived.json').write_text(json.dumps(frames,indent=2)+'\n')
visual=json.loads((base/'config17-visual-review-r1.derived.json').read_bytes());assert visual['passed'] and len(visual['reviewed'])>=12
copy(base/'config17-visual-review-r1.derived.json','ui/direct-review.derived.json')
for i,entry in enumerate(visual['reviewed']):copy(entry['path'],'ui/representatives/'+Path(entry['path']).name)
native=json.loads((base/'config17-native-r2/result.json').read_bytes());assert native['exit']==0 and native['source_unchanged']
trx=ET.parse(base/'config17-native-r2/results/contracts.trx');ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};assert len(trx.findall('.//t:UnitTestResult',ns))==10
godot=json.loads((base/'config17-godot-r2/cases.original.json').read_bytes());assert all(t['ok'] for t in godot.values()) and len(godot['test_mage_return_budget.gd']['checks'])==68
continuation=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes())
for bank in continuation['D03_latest_banks']:assert hashlib.sha256(Path(bank['source']).read_bytes()).hexdigest()==bank['sha256']
result=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),formal_local_config='season-v1-config-17',content_hash='3e4efc7f04d2acc0d70f1ef3ba7f2ce9cc4b675543b443606880a10b6cc1e490',binary_sha256='7620228c6290fe23d8cadee6d79eeeab4bb6aae7f7dd2723f3764f8a29f5cf40',workbook_sha256='cad81ea021cf00184e9e5edc9b40fae337ed92c5febaa7f9262bcf4dd3c4d032',native_unique_passed=10,godot_named_checks_passed=68,godot_existing_suites_passed=2,UI_final_frames=231,UI_final_checks=checks,UI_original_frames_retained=273,UI_reused_passed_frames=147,UI_new_r2_passed_frames=84,UI_visual_passed=True,new_B05_encounters=0,new_D03_encounters=0,new_D02_encounters=0,B05_used=330,B05_remaining=0,D03_used=284,D03_remaining=16,D02_used=112,D02_remaining=188,capital_banks_unchanged=True,progress='29/35',whole_goal_complete=False,production_deployed=False,production_restarted=False,cloud_modified=False,capacity100_retested=False,local_reserve_GiB=2,startup_GiB=1,historical_failures_retained=['Godot r1 missing gateway fixture; corrected r2, no product workaround','English pilot 6 card assertions omitted existing Base label; corrected assertion, no product workaround','Arabic6 HUD assertions omitted existing BiDi isolates; exact display normalization fixed,147 prior passed frames reused on identical product bytes plus84 newframes','All old D03 timing/class/route failures; original75 and prospective67.5 pacing still failed; no retroactive widening'])
(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'source-manifest.json').write_text(json.dumps(orig,indent=2)+'\n')
continuation.update(updated_at_utc=result['at'],config17_native_passed=10,config17_godot_named_passed=68,config17_godot_existing_suites_passed=2,config17_ui_protocol_pending=False,config17_UI_final_frames=231,config17_UI_final_checks=checks,config17_UI_final_passed=True,all_own_test_handles_terminal=True,pending_test_handles=[],latest_report='docs/season-balance-20261102/C01-CONFIG17-MAGE-RETURN.md',latest_evidence='docs/season-balance-20261102/evidence/C01-config17-r1/result.json',next_focus='Formal local17/optional own credit protocol/client forecast+MAG10 versioned full descriptions verified: native10, Godot68+2 suites, 231 affected11locale3width frames and direct review. Scoped report/evidence ready; push integration branch then continue D03/D04/E02/F01/F02/F03, whole29/35. No production beforeF03. B05 fullyclosed330/330, no extra. D03 284/300,16remain. Oldpacing75/67.5 failures remain. Nine latestbanks byteunchanged; do not reset. No100/oldpassedUI/full normalsettlement reruns.')
(base/'current-journey-client-continuation-20261105.json').write_text(json.dumps(continuation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
