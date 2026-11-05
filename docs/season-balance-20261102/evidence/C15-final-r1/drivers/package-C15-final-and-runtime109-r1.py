from pathlib import Path
import gzip,hashlib,importlib.util,json,shutil,xml.etree.ElementTree as ET

repo=Path.cwd();base=Path(__file__).parent;target=repo/'docs/season-balance-20261102/evidence/C15-final-r1';assert not target.exists();target.mkdir()
spec=importlib.util.spec_from_file_location('public',repo/'tools/pr13_public_evidence.py');public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
raws={}
def copy(p,name):
 raw=p.read_bytes();public.inspect_public_bytes(p,raw);dest=target/name
 if len(raw)>150000 and p.suffix in ('.json','.jsonl','.log'):dest=dest.with_name(dest.name+'.gz');packed=True
 else:packed=False
 dest.parent.mkdir(parents=True,exist_ok=True);assert not dest.exists();dest.write_bytes(gzip.compress(raw,mtime=0) if packed else raw)
 raws[str(name)]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'stored':dest.relative_to(target).as_posix(),'gzip':packed}

stages=['journey-client-ui-final-ar-r1','journey-client-ui-final-enzh-r2','journey-client-ui-final-jako-r1','journey-client-ui-final-hifrru-r1','journey-client-ui-final-esptid-r1']
baseline=json.loads((base/stages[0]/'source-pin.original.json').read_text('utf-8'));frames={};reports={};checks=0
for name in stages:
 root=base/name;review=json.loads((root/'review.json').read_bytes());terminal=json.loads((root/'terminal.original.json').read_bytes());pins=json.loads((root/'source-pin.original.json').read_bytes())
 assert all(review['checks'].values()) and review['render_capture_complete'] and not review['legacy_layout_observations']
 assert terminal['native_exit']==0 and terminal['source_unchanged'] and terminal['input_desktop_unchanged'] and terminal['desktop_switch_calls']==0
 diff=[n for n,h in baseline.items() if pins.get(n)!=h];assert all(n.replace('\\','/')=='tools/validate_ui_hidden.py' for n in diff)
 assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items() if n.replace('\\','/')!='tools/validate_ui_hidden.py')
 for p in root.glob('*.png'):
  assert p.stem not in frames;frames[p.stem]={'stage':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
 for p in root.glob('*'):
  if p.is_file() and p.suffix in ('.json','.jsonl','.log'):copy(p,Path('UI')/name/p.name)
 checks+=len(review['checks']);reports[name]={'frames':len(review['frames']),'checks':len(review['checks']),'only_source_difference_from_AR':diff,'resource_reserve_GiB':6 if name==stages[0] else 2}
assert len(frames)==396 and checks==34374
viewed={
stages[0]:['ar_960_claim_cosmetics_owned.png','ar_1280_claim_cosmetics_middle.png'],
stages[1]:['en_1920_claim_cosmetics_owned.png','zh-CN_1280_claim_rewards_confirm.png','en_960_claim_rewards_claimed.png'],
stages[2]:['ja_960_claim_cosmetics_tail.png','ko_1280_claim_rewards_class_menu.png'],
stages[3]:['hi_960_claim_cosmetics_middle.png','fr_1280_claim_rewards_confirm.png','ru_960_claim_cosmetics_tail.png'],
stages[4]:['es_960_claim_rewards_pending.png','pt_960_claim_rewards_tail.png','id_960_claim_rewards_unavailable.png','id_1280_claim_cosmetics_empty.png','es_1280_claim_deck_equipped.png','id_1920_claim_hall_equipped.png']}
for name,images in viewed.items():
 for image in images:copy(base/name/image,Path('viewed')/name/image)

runtime=base/'runtime-r109';audit=json.loads((runtime/'collection-audit.json').read_bytes());assert audit['counts']['passed']=='56' and audit['counts']['failed']=='0' and audit['counts']['notExecuted']=='0' and audit['exit_code']==0 and not audit['oom_killed']
assert hashlib.sha256((runtime/'public-evidence.tar.gz').read_bytes()).hexdigest()==audit['public_archive_sha256']
assert all(hashlib.sha256((runtime/'public'/n).read_bytes()).hexdigest()==h for n,h in audit['files'].items())
groups={}
for test in ET.fromstring((runtime/'public/results/xunit.original.xml').read_bytes()).iter('test'):
 name=test.attrib['type'].split('.')[-1];groups[name]=groups.get(name,0)+1;assert test.attrib['result']=='Pass'
assert groups['PostgresMailPermanentCopyTests']==8 and groups['PostgresAdminPermanentCopyTests']==2 and sum(groups.values())==56
for p in runtime.rglob('*'):
 if not p.is_file() or p.name.startswith(('payload','transport-stream')) or any(n in p.relative_to(runtime).parts for n in ['input','build']):continue
 if p.suffix in ('.json','.log','.py','.trx','.xml','.bin','.gz'):copy(p,Path('runtime-r109')/p.relative_to(runtime))
for name in ['source-pin.json','result.json','unchanged-dependency-reuse.json','build-and-tests.original.log','results/mail-local.trx']:
 copy(base/'mail-permanent-local-r6'/name,Path('local-r6')/name)
copy(base/'resource-policy-local2GiB-20261105.json',Path('resource-policy-local2GiB-20261105.json'))
copy(base/'runtime-r107/input-retirement-verified-local-r1.original.json',Path('retirement/runtime107-expanded-copy.original.json'))
for name in ['run-mail-permanent-local-r6.py','augment-runtime109-provenance.py','prepare-runtime109-control.py','setup-mail-runtime109-file-transfer.py','transfer-r109-stream-sftp.py','verify-r109-complete-stream.py','start-r109-from-verified-file.py','observe-mail-runtime-r109.py','collect-mail-runtime-r109.py','prepare-runtime-dictionary-delta.py','runtime_dictionary_delta.py','retire-runtime107-expanded-input-r1.py','run-journey-client-ui-r4.py','package-C15-final-and-runtime109-r1.py']:
 copy(base/name,Path('drivers')/name)

old=json.loads((base/'runtime-r108/public/proof/source-pin.json').read_bytes())
journey=[n for n in old if n.startswith('server/src/') and 'SeasonJourney' in n and n.endswith('.cs')]
assert journey and all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==old[n] for n in journey)
budget=json.loads((repo/'docs/season-balance-20261102/evidence/C15-client-control-r1/budget/verification.json').read_bytes());assert budget['ok'] and len(budget['checks'])==14
result={'status':'C15_requirements_verified','C15_complete':True,'whole_goal_complete':False,'overall_completed_items_after_C15':21,'configuration':'season-v1-config-14','current_local_contract_and_encoding_passed':25,'current_isolated_runtime_passed':56,'current_runtime_groups':groups,'current_runtime_failed':0,'current_runtime_skipped':0,'current_native_controller_passed':17,'earlier_actual_CSharp_HTTP_native_model_passed':29,'newest_actual_authenticated_CSharp_HTTP_checks':1,'Godot_native_public_HTTP_claimed':False,'current_UI_final_unique_frames':396,'current_UI_checks':34374,'locales':11,'widths':[960,1280,1920],'new_UI_states':12,'directly_viewed_current_representatives':sum(map(len,viewed.values())),'prior_experience_UI_frames':330,'prior_domain_experience_checks':92,'prior_server_experience_union':130,'old_journey_production_source_current_unchanged':journey,'independent_journey_budget_checks':14,'data_budget':{'EquipmentFragments':80,'WarriorSoul':24,'ClassSoul_all_choices_combined':8,'CardPack':4,'actual_permanent_card_copies':12},'cosmetic_budget':{'AvatarFrame':3,'CardBack':2,'Collection':2,'Title':3},'resource_policy':'AR36 under historical6GiB; remaining360 and current local compilation under user-authorized2GiB reserve+1GiB startup; cloud guards unchanged','all_original_failures_retained':True,'new_full_routes':0,'new_balance_encounters':0,'B05_total':291,'C16_total':121,'capacity100_retest':False,'production_deployed':False,'production_restarted':False,'A03_A04_E02_whole_acceptance_not_inferred':True}
(target/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(target/'UI-final-frame-manifest.json').write_text(json.dumps(frames,indent=2)+'\n',encoding='utf-8')
(target/'UI-batch-reports.json').write_text(json.dumps(reports,indent=2)+'\n',encoding='utf-8')
(target/'raw-text-manifest.json').write_text(json.dumps(raws,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
(target/'manifest.json').write_text(json.dumps({'files':files,'full_original_directory':str(base),'full_binary_payloads_retained_in_G':True},indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'runtime_passed':56,'final_frames':396,'UI_checks':34374,'C15_complete':True}))
