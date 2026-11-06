from pathlib import Path
import json,hashlib,subprocess,re,datetime
repo=Path.cwd();base=Path(__file__).parent;docs=repo/'docs/season-balance-20261102';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sem=json.loads((base/'e02-semantic-inputs-r3.derived.json').read_bytes());symbols=json.loads((base/'e02-function-closure-precheck-r1.json').read_bytes());historic=json.loads((base/'e02-historical-frames-r1.derived.json').read_bytes())
assert historic['verified_PNG_entries']==5269 and len(historic['groups'])==17 and historic['integrity_not_additional_passing_test_count']
for group,rows in sem['groups'].items():
 for r in rows:
  assert sha(repo/r['path'])==r['current_sha256']
  if '/locales/' in r['path']:assert not r['removed_keys'] and not r['changed_values'] and r['pack_metadata_same']
  if 'old_field_changes' in r:assert r['old_field_changes']==[]
  if 'old_endpoint_rows_preserved' in r:assert r['old_endpoint_rows_preserved'] and r['protocol_version_same'] and r['media_type_same'] and r['error_same']
  if r['path'].endswith('.import'):assert r['normalized_same']
def funcs(s):
 starts=list(re.finditer(r'^(?:static )?func (\w+)\(',s,re.M));out={'__header__':s[:starts[0].start()] if starts else s}
 for i,m in enumerate(starts):out[m.group(1)]=s[m.start():starts[i+1].start() if i+1<len(starts) else len(s)]
 return out
def disposition(path,symbol):
 if path=='client/data/catalog_index.gd' or path=='client/data/config_bundle.gd':return {'scope':'Verified original refresh price visibility; published values preserved','evidence':['evidence/C01-refresh-price-ui/result.json','evidence/A04-client-preparation-config-r1/result.json']}
 if path=='client/state/game_store.gd':
  if symbol=='_calculate_combat_preview':return {'scope':'New rate-budgeted rhythm preview only; not combat authority','evidence':['evidence/C01-config17-r1/result.json']}
  return {'scope':'Added module/session/preparation/original-catalog state; original API fields preserved; original-source and stale-context branches remain separately tested','evidence':['evidence/A04-client-preparation-config-r1/result.json','evidence/C15-final-r1/result.json','evidence/E01-season-archive-r1/result.json']}
 if path=='client/ui/battle_details.gd':return {'scope':'New/old rhythm wording and numerical details','evidence':['evidence/C01-config17-r1/result.json']}
 if path=='client/ui/confirmation_modal.gd':return {'scope':'Opt-in scroll path; ordinary options unchanged. Fresh-instance close and once-only callback directly checked','evidence':['evidence/C01-config17-r1/result.json'],'current_bridge':'e02_confirm_plain'}
 if path=='client/ui/codex_view.gd':return {'scope':'Original catalog ownership/source and MAG10 new/old description; other draw geometry unchanged','evidence':['evidence/A04-client-preparation-config-r1/result.json','evidence/C01-config17-r1/result.json']}
 if path=='client/ui/deck_builder_view.gd':return {'scope':'Cosmetic card back display and original preparation deck','evidence':['evidence/C15-final-r1/result.json','evidence/A04-client-preparation-config-r1/result.json']}
 if path=='client/ui/exploration_view.gd':
  if symbol in ['_battle','_passive']:return {'scope':'Rhythm HUD/details and original passive wording','evidence':['evidence/C01-config17-r1/result.json']}
  return {'scope':'Original reward-value/replacement and theme backdrop dispatch','evidence':['evidence/E01-final-r1/result.json','evidence/C16-themes/core/result.json']}
 if path=='client/ui/inventory_view.gd':return {'scope':'Public replacement-capacity model, same visible inventory layout','evidence':['evidence/E01-final-r1/result.json']}
 if path=='client/ui/layered_backdrop.gd':return {'scope':'Exploration-only declared theme tint; non-exploration paths preserve palette','evidence':['evidence/C16-themes/core/result.json']}
 if path=='client/ui/numerical_details.gd':return {'scope':'Original-catalog/class providers and opt-in preparation deck caption. Default blank caption and rendering geometry unchanged','evidence':['evidence/A04-client-preparation-config-r1/result.json','evidence/E01-season-archive-r1/result.json']}
 if path=='client/ui/reference_ui.gd':
  if symbol=='_header':return {'scope':'Added names/selected title/frame; prior branch names unchanged','evidence':['evidence/C15-final-r1/result.json'],'current_bridge':'e02_market_header'}
  if symbol=='_gear':return {'scope':'Management entry and shorter scroll region; bottom reachable','evidence':['evidence/E01-inventory-management-ui-r1/result.json'],'current_bridge':'e02_gear_entry'}
  if 'shop' in symbol:return {'scope':'Original seasonal shop quotes/copy materials/current UI callbacks','evidence':['evidence/C13-shop/result.json'],'current_native_suites':['test_season_shop_model.gd','test_season_shop_controller.gd']}
  if symbol in ['_preparation','_loadout','_equipment_attribute_lines','_equipment_set_lines','_season_selector_style','_enhance']:return {'scope':'Original catalog/class providers, preparation projection/availability and tooltips; equipment/caps/price tables unchanged, drawing paths retain prior geometry','evidence':['evidence/A04-client-preparation-config-r1/result.json','evidence/C05-integration/result.json','evidence/C06-enhancement/result.json']}
  return {'scope':'Additive screen dispatch/hall entries/preloads; prior market body and generic text/art helpers unchanged','evidence':['evidence/C13-shop/result.json','evidence/C14-activities/result.json','evidence/C15-final-r1/result.json','evidence/E01-season-archive-r1/result.json']}
 if path=='client/ui/main.gd':
  if symbol in ['_show_battle_details','card_description']:return {'scope':'Opt-in current rhythm details and MAG10 original/new description','evidence':['evidence/C01-config17-r1/result.json']}
  if symbol in ['_claim','_rewards']:return {'scope':'Public reward value, original IDs, guarded replacement/confirmation','evidence':['evidence/E01-final-r1/result.json']}
  if symbol in ['_apply_account_mutation','_mutate','_equipment','_show_inventory_management']:return {'scope':'Added inventory/discard branch and entry. Existing loadout/market branches retain original code','evidence':['evidence/E01-inventory-management-ui-r1/result.json','evidence/E01-inventory-native-wire-r1/result.json'],'current_bridge':'e02_gear_entry'}
  if 'shop' in symbol or symbol=='_apply_shop_purchase':return {'scope':'Seasonal shop source/receipt/cache flows; same current callback paths exercised','evidence':['evidence/C13-shop/result.json'],'current_native_suites':['test_season_shop_model.gd','test_season_shop_controller.gd']}
  if symbol in ['display_catalog_index','display_hero_class','_show_equipment_details','_show_preparation_deck','_preparation','_card_action_block_reason','_card_text','_card_button','_card_action','_set_codex_action_busy']:return {'scope':'Original preparation/deck/codex source and availability. Providers same as A04 verified functions; values and original-version behavior retain their scoped evidence','evidence':['evidence/A04-client-preparation-config-r1/result.json','evidence/E01-season-archive-r1/result.json','evidence/C15-final-r1/result.json']}
  return {'scope':'Additive archive/navigation/account-reset/controller wiring; old screen branches not removed','evidence':['evidence/C15-final-r1/result.json','evidence/E01-season-archive-r1/result.json']}
 raise AssertionError((path,symbol))
coverage=[]
for group,rows in symbols.items():
 for r in rows:
  current=funcs((repo/r['path']).read_text(encoding='utf-8-sig').replace('\r\n','\n'))
  assert current==r['after'],r['path']
  actual=[s for s in sorted(set(r['before'])|set(current)) if r['before'].get(s)!=current.get(s)];assert actual==r['changed_symbols']
  for symbol in actual:
   d=disposition(r['path'],symbol)
   for e in d['evidence']:assert (docs/e).is_file()
   coverage.append({'baseline':group,'path':r['path'],'symbol':symbol,'original_commit':r['original_commit'],'original_pin_sha256':r['original_pin_sha256'],'before_symbol_sha256':hashlib.sha256(r['before'].get(symbol,'').encode()).hexdigest(),'after_symbol_sha256':hashlib.sha256(current.get(symbol,'').encode()).hexdigest(),'review':d})
# The last accepted product pin still covers all current shared resources, fonts and scripts.
index=json.loads((docs/'evidence/E02-source-audit-r1/e02-ui-source-dependencies-r1.derived.json').read_bytes())['sources']['config17-current'];pin=json.loads((repo/index['source']).read_bytes());product={n:h for n,h in pin.items() if n.replace('\\','/').startswith('client/') and not n.replace('\\','/').startswith('client/tests/')}
assert len(product)==116 and all(sha(repo/n)==h for n,h in product.items())
# Current ordinary dialog/controller behavior and all added bridge frames.
native=base/'e02-current-native-r1';n=json.loads((native/'result.json').read_bytes());checks=json.loads((native/'checks.json').read_bytes());assert n['exit']==0 and not n['engine_errors'] and n['source_unchanged'] and checks['ok'] and checks['checks']==50 and len(checks['suites'])==5
assert all(v['ok'] and all(v.get('checks',{}).values()) for v in checks['suites'].values())
for k,v in json.loads((native/'source-pin.json').read_bytes()).items():assert sha(repo/k)==v
ui=base/'e02-bridge-ui-r1';terminal=json.loads((ui/'terminal.original.json').read_bytes());review=json.loads((ui/'review.json').read_bytes());assert terminal['native_exit']==0 and terminal['stop_reason'] is None and terminal['source_unchanged'] and terminal['all_checked_threads_private'] and terminal['input_desktop_unchanged'] and terminal['desktop_switch_calls']==0
assert terminal['render_timeout_seconds']==300 and terminal['seconds']<300 and terminal['PNGs']==99
assert review['render_capture_complete'] and review['screenshots']==99 and len(review['languages'])==11 and review['widths']==[960,1280,1920] and not review['legacy_layout_observations'] and len(review['checks'])==9555 and all(review['checks'].values())
assert review['typography']=={'cards_msdf':True,'cards_msdf_size':96,'ui_hinting':2,'ui_oversampling':2.0}
for k,v in json.loads((ui/'source-pin.original.json').read_bytes()).items():assert sha(repo/k)==v
visual=json.loads((base/'e02-bridge-visual-review-r1.derived.json').read_bytes());assert len(visual['representatives'])==14 and visual['all_11_locales_represented']
for r in visual['representatives']:assert sha(ui/r['name'])==r['sha256'] and r['visual_verdict']=='pass'
registry=json.loads((repo/'client/data/localization_registry.json').read_bytes());locales={}
for code,meta in registry['languages'].items():
 pack=json.loads((repo/'client'/meta['path'].removeprefix('res://')).read_bytes());locales[code]=pack['strings']
assert len(locales)==11 and all(set(v)==set(locales['en']) for v in locales.values())
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),'E02_complete':True,'acceptance_scope':'All affected game UI families covered by original accepted multilingual/resolution module matrices plus exact unchanged dependencies and this99-frame shared-change bridge. Human experience and real gameplay not claimed.','new_frames':99,'new_UI_checks':9555,'current_native_named_checks':49,'current_native_confirmation_suite':1,'direct_new_representatives':14,'languages':sorted(locales),'widths':[960,1280,1920],'keys_per_pack':len(locales['en']),'product_files_identical_to_config17_pin':116,'changed_symbol_coverage':coverage,'semantic_audit':'e02-semantic-inputs-r3.derived.json','historical_integrity_audit':'e02-historical-frames-r1.derived.json','verified_original_PNG_entries':5269,'original_PNG_entries_are_not_new_passing_counts':True,'old_locale_values_and_API_field_tags_retained':True,'old_font_import_differences_are_line_endings_only':True,'card_MAG10_and_rate_changed_UI_already_current231':True,'unreviewed_changed_symbols':[],'old_phase_false_and_failures_retained':True,'new_products_changed':False,'new_gameplay_campaign_cases':0,'new_native_capacity_cases':0,'B05_total':330,'D03_total':284,'D03_remaining':16,'class_efficiency_target':1.15,'production_modified':False,'whole_goal_complete':False,'next_progress':'32/35','remaining_items':['D03','F01','F03']}
p=base/'e02-current-closure-r2.derived.json';assert not p.exists();p.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'E02_complete':True,'changed_symbol_entries':len(coverage),'new_frames':99,'checks':9555,'current_native_named_checks':49,'confirmation_suite':1,'next_progress':'32/35'}))
