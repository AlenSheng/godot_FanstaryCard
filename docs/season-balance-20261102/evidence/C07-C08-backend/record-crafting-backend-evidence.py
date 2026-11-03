from pathlib import Path
import hashlib,json,shutil,subprocess,xml.etree.ElementTree as ET,importlib.util
base=Path(__file__).parent;repo=Path.cwd();out=repo/'docs/season-balance-20261102/evidence/C07-C08-backend'
assert not out.exists()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};root=ET.parse(p)
 defs={u.attrib['id']:u.find('t:TestMethod',ns).attrib['className'] for u in root.findall('.//t:UnitTest',ns)}
 return {defs[r.attrib['testId']]+'/'+r.attrib['testName']:r.attrib['outcome'] for r in root.findall('.//t:UnitTestResult',ns)}
hashes={59:'96597a9e54a835955a6fd4177a13af18a0b6d102aa9fc79ee06f02712979ccb3',60:'8be30ba52acfa3aa57243c339bd9b494d55930ecf4b96f48e81b453ae2ddb88e',
61:'2971891829e4d332acb1700aa89a3f954bed8f519811ea34ff864383135028ea',62:'94ae7ead10eea233af59628781929c012042227e9bb6b4cb65834e82de5af0bd',
63:'6f8fd87efb97583aa526431e504fc09f92ae4dfd349cac0f5dc2e30d9c0ece8f',64:'7f8213cee87fff760f3b1ec3327a9ce3429782919a85e551b92b47f5982b1922',
65:'6651fb96249e605c784ada11f8c9e3c2a2b69feeefc872595cdc1d760fe65df0'}
for n,h in hashes.items():
 p=base/f'storage-r{n}';assert sha(p/'public-evidence.tar.gz')==h
 a=read(p/'public/audit.json');assert a['state']=='exited' and not a['oom_killed']
 for name,digest in a['files'].items():assert sha(p/'public'/name)==digest
domain61=cases(base/'storage-r61/public/season-crafting-domain.trx')
domain62=cases(base/'storage-r62/public/season-crafting-domain.trx')
domain={k:v for k,v in domain61.items() if v=='Passed'};domain.update(domain62)
assert len(domain)==561 and set(domain.values())=={'Passed'}
server64=cases(base/'storage-r64/public/season-crafting-server.trx')
server65=cases(base/'storage-r65/public/season-crafting-publisher.trx')
server={k:v for k,v in server64.items() if v=='Passed'};server.update(server65)
assert len(server)==259 and set(server.values())=={'Passed'}
new={k:v for k,v in server.items() if any(part in k for part in ['PostgresSeasonBlueprintTests/','PostgresSeasonCraftingTests/','PostgresSeasonRecipeTests/','SeasonCraftingEncodingTests/'])}
assert len(new)==20
assert sum('FiveRealBodiesReforgeForSixThenActuallyEnhanceForTheCombinedRebuildBudget' in k for k in new)==2
man65=read(base/'storage-r65/input-manifest.json');runtime={n:h for n,h in man65['files'].items() if n.startswith('server/src/') and n.endswith(('.cs','.sql'))}
assert all(sha(repo/name)==h for name,h in runtime.items())
man64=read(base/'storage-r64/input-manifest.json');assert all(man64['files'].get(name)==h for name,h in runtime.items())
native=read(base/'crafting-native-r3/checks.json');assert native['ok'] and native['checks']==138
assert read(base/'crafting-native-r3/result.json')['source_unchanged']
for name,h in read(base/'crafting-native-r3/source-pin.json').items():assert sha(repo/name)==h
wb=base/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/crafting'
preserve=read(wb/'preservation-proof.json');assert sha(repo/'config/FantasyCard_Config.xlsx')==preserve['after_sha256']
sp=importlib.util.spec_from_file_location('catalog',repo/'tools/export_client_catalog.py');module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)
old=module.fields((repo/'server/config/archive/season-v1-config-3/fantasycard.config.bytes').read_bytes())
current=module.fields((repo/'server/config/generated/fantasycard.config.bytes').read_bytes())
tables=lambda v:{module.fields(t)[1][0].decode():t for t in v[3]}
before=tables(old);after=tables(current);assert len(before)==22 and len(after)==24 and all(after[k]==v for k,v in before.items())
for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
 assert (repo/'server/config/generated'/name).read_bytes()==(repo/'client/data/generated'/name).read_bytes()
 assert (repo/'server/config/archive/season-v1-config-3'/name).read_bytes()==subprocess.check_output(['git','show','HEAD:server/config/generated/'+name])
out.mkdir(parents=True)
for n in hashes:
 shutil.copytree(base/f'storage-r{n}/public',out/f'r{n}')
 shutil.copy2(base/f'storage-r{n}/input-manifest.json',out/f'r{n}/input-manifest.json')
for run in ['crafting-native-r1','crafting-native-r2','crafting-native-r3','enhancement-native-r6']:
 dest=out/run;dest.mkdir()
 for p in (base/run).glob('*'):
  if p.is_file() and p.suffix in ['.json','.log','.gd']:shutil.copy2(p,dest/p.name)
dest=out/'workbook';dest.mkdir()
for name in ['before.png','SeasonCrafting.png','SeasonMarkRules.png','crafting-rows.json','preservation-proof.json','FantasyCard_Config.xlsx.inspect.ndjson']:
 shutil.copy2(wb/name,dest/name)
for name in ['season-crafting.mjs','verify-crafting-workbook.py']:shutil.copy2(base/'workbook'/name,dest/name)
for name in ['ended-expanded-inputs-v2.json','ended-expanded-inputs-v3.json','ended-expanded-inputs-v4.json']:
 assert (base/name).is_file();shutil.copy2(base/name,out/name)
shutil.copy2(base/'run-crafting-native.py',out/'run-crafting-native.py')
proof={'status':'C07_C08_backend_verified_UI_still_pending_C06_combined_budget_verified','C06_combined_budget_verified':True,
 'C07_complete':False,'C08_complete':False,'whole_goal_complete':False,
 'configuration_version':'season-v1-config-4','configuration_content_hash':(repo/'server/config/generated/fantasycard.config.sha256').read_text().strip(),
 'configuration_binary_sha256':sha(repo/'server/config/generated/fantasycard.config.bytes'),'published_tables':24,'published_rows':1741,'old_table_bodies_unchanged':22,
 'workbook_preservation':preserve,'domain_targeted_union_passed':561,'domain_union_not_one_full_run':True,
 'unchanged_monster_pool_9000_control_not_rerun':True,'server_targeted_union_passed':259,'server_union_not_one_full_run':True,'new_backend_controls':20,
 'publisher_r65_passed':46,'native_checks_passed':138,'new_UI_rendered_frames':0,
 'retained_skips':[{'stage':'r64','cases':2,'category':'A05 process settlement fault','reason':'Dedicated process test switch was not enabled; F02 remains pending; not counted as a pass'}],
 'retained_failures':[{'stage':'r60','reason':'CA1861 constant-array allocation; no tests executed'},
 {'stage':'r61','passed':559,'failed':2,'reason':'Finishing-control fixture omitted required combatActionId; expected current version was still3'},
 {'stage':'r62','domain_passed':2,'server_executed':0,'reason':'CA1822 stateless wallet reader needed static modifier'},
 {'stage':'r63','reason':'CA1861 test expected-array allocation; no server tests executed'},
 {'stage':'r64','passed':250,'failed':1,'skipped':2,'reason':'Published table-count assertion still22; actual24'},
 {'stage':'crafting-native-r1','reason':'Overview route registry retained trailing slash; canonical path corrected; first failed result retained'}],
 'actual_combined_rebuilds':[{'real_bodies':5,'reforge_fragments':6,'to_level':3,'total_fragments':66,'extra_material_bodies':0},
 {'real_bodies':5,'reforge_fragments':6,'to_level':5,'total_fragments':786,'extra_material_bodies':10}],
 'runtime_sources_byte_identical_since_actual_r64_transactions':len(runtime),
 'still_required':['C07/C08 actual UI entry, current typed balances, wishes, sample states and before/after reforge confirmation',
 'All new UI surfaces in eleven locales and three resolutions','Live HTTP session interoperability for the five new routes',
 'Additional recipe escrow/concurrency/boundary/failure controls as needed for final F02','C09 natural preferred-element weights and remaining RNG stream migration',
 'C11 red mint/quota, C12 market, C14 activity pure-material provenance and remaining D/E/F gates'],
 'source_semantics':['Legacy opaque ChallengeMarks remain unchanged; new blueprint types start zero',
 'D1 blueprints and D2+ orange blueprints only from own unique elite/boss clears and extracted settlement, cap4',
 'Crafted item selection is slot/element exact; effect pity is account/season/quality/slot/element/wish scoped',
 'Legal unaffixed Purple can teach; Orange must have an effect; template freezes the sample shoe trait',
 'Reforge keeps original item ID and binding/origin/history, resets level0, clears equipped references and returns to inventory',
 'In-place rebuild cannot duplicate equipment or teach from a transformed sample'],
 'public_archive_sha256':hashes,'production_deployed':False,'production_restarted':False,'capacity_retested':False,
 'B05_routes_used':291,'B05_routes_remaining':9}
(out/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'runtime-files.json').write_text(json.dumps(runtime,indent=2)+'\n')
(out/'server-case-union.json').write_text(json.dumps(server,indent=2)+'\n')
(out/'domain-case-union.json').write_text(json.dumps(domain,indent=2)+'\n')
print(json.dumps({'domain_union':561,'server_union':259,'new_controls':20,'native':138,'runtime_sources':len(runtime),'new_UI_frames':0}))

