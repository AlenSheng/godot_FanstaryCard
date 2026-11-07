from pathlib import Path
import gzip,hashlib,json,re,shutil,subprocess
import xml.etree.ElementTree as E

repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/C15-journey/core'
assert not e.exists();e.mkdir(parents=True)
def copy(relative,dest=None):
    src=b/relative;target=e/(dest or relative);assert src.is_file(),src
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
for stage in ['storage-r88','storage-r89']:
    for p in (b/stage).iterdir():
        if p.is_file() and p.suffix in ['.json','.log','.py']:copy(stage+'/'+p.name)
    shutil.copytree(b/stage/'public',e/stage/'public')
    manifest=json.loads((b/stage/'input-manifest.json').read_text(encoding='utf-8'))
    for n,h in manifest['files'].items():
        if stage=='storage-r88' and n=='server/tests/FantasyCard.Server.Tests/Persistence/PostgresSeasonJourneyTests.cs':continue
        assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h,n
for folder in ['local-config-r11']+[f'local-journey-domain-r{i}' for i in range(1,5)]+[f'local-journey-server-build-r{i}' for i in range(1,5)]:
    for p in (b/folder).iterdir():
        if p.is_file() and p.suffix in ['.json','.jsonl','.log']:copy(folder+'/'+p.name)
    for p in (b/folder/'results').glob('*.trx'):copy(folder+'/results/'+p.name)
for folder in ['journey-native-r1','journey-native-r2','journey-native-r3','journey-actual-wire-r1','journey-actual-wire-r2','journey-protocol-r1']:
    for p in (b/folder).iterdir():
        if p.is_file() and p.suffix in ['.json','.log','.gd','.bin']:copy(folder+'/'+p.name)
for name in ['run-journey-native.py','run-journey-actual-wire-r1.py','run-journey-actual-wire-r2.py','journey-wire.gd','journey-protocol-r2.original.log','journey-localization-r1.json','journey-localization-r2.json','journey-localization-r3.json',
             'run-journey-workbook.py','run-journey-workbook-r2.py','export-journey-config-r11.py','retire-activity-pagination-expanded-v16.py','retire-journey-expanded-v17.py','archive-market-expanded-v16.py','archive-market-expanded-v17.py','ended-expanded-inputs-v16.json','ended-expanded-inputs-v17.json','v16-local-verification.json','v17-local-verification.json']:
    if (b/name).is_file():copy(name)
for stage in [88,89]:
    for kind in ['prepare','ship','observe','collect']:copy(f'{kind}-season-journey-r{stage}.py')
for version in [16,17]:
    for mode in ['prepare','download','retire','offload']:
        if (b/f'v{version}-{mode}.original.log').exists():copy(f'v{version}-{mode}.original.log')
copy('workbook/season-journey.mjs','workbook/season-journey.mjs');copy('workbook/season-journey-r2.mjs','workbook/season-journey-r2.mjs')
copy('workbook/verify-journey-workbook.py','workbook/verify-journey-workbook.py');copy('workbook/verify-journey-workbook-r2.py','workbook/verify-journey-workbook-r2.py')
for label in ['season-journey','season-journey-r2']:
    root=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79'/label
    for p in root.iterdir():
        if p.is_file() and p.suffix in ['.json','.ndjson','.png']:copy(p.relative_to(b).as_posix(),'workbook/'+label+'/'+p.name)
ui=e/'ui';ui.mkdir()
runs=['journey-ui-script-r1','journey-ui-en-r1','journey-ui-en-r2','journey-ui-en-r3','journey-ui-a-r1','journey-ui-a-r2','journey-ui-b-r1','journey-ui-ar-r1','journey-ui-a-r3','journey-ui-b-r2','journey-ui-c-r1']
raw=[]
for run in runs:
    dst=ui/run;dst.mkdir()
    for p in (b/run).iterdir():
        if not p.is_file() or p.suffix=='.png':continue
        if p.name in ['review.json','frames.original.jsonl']:(dst/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
        else:shutil.copy2(p,dst/p.name)
    raw.extend({'run':run,'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (b/run).glob('*.png'))
(ui/'raw-frame-manifest.json').write_text(json.dumps(raw,indent=2)+'\n',encoding='utf-8')
final=[];runtime=None;checks=0
for run in ['journey-ui-a-r3','journey-ui-b-r2','journey-ui-c-r1']:
    report=json.loads((b/run/'review.json').read_text(encoding='utf-8'));terminal=json.loads((b/run/'terminal.original.json').read_text(encoding='utf-8'))
    assert report['render_capture_complete'] and not report['legacy_layout_observations'] and all(report['checks'].values())
    assert terminal['native_exit']==0 and terminal['source_unchanged'] and terminal['all_checked_threads_private'] and terminal['desktop_switch_calls']==0
    pin=json.loads((b/run/'source-pin.original.json').read_text(encoding='utf-8'));current={n:h for n,h in pin.items() if not n.startswith('client\\tests\\')}
    if runtime is None:runtime=current
    else:assert current==runtime
    assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in current.items())
    checks+=len(report['checks']);final.extend(row for row in raw if row['run']==run)
assert len(final)==330 and len({r['file'] for r in final})==330
(ui/'final-frame-manifest.json').write_text(json.dumps({'frames':final,'checks':checks,'runtime_sources_identical':True,'actual_full_game_matches':0,'C15_full_requirement_accepted':False,'reason':'Experience/contract UI only. Actual tier rewards remain unimplemented pending selection.'},indent=2)+'\n',encoding='utf-8')
representatives={'journey-ui-a-r3':['ar_960_c15_active.png','es_960_c15_entry.png','en_960_c15_complete.png'],'journey-ui-b-r2':['hi_1280_c15_archive.png','fr_960_c15_upcoming.png'],'journey-ui-c-r1':['ar_960_c15_unavailable.png','en_1920_c15_error.png']}
manual={}
for run,names in representatives.items():
    for name in names:
        target=ui/('final-'+name);shutil.copy2(b/run/name,target);manual[name]={'source':run,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(ui/'manual-review.json').write_text(json.dumps({'reviewer':'assistant visual inspection','accepted_core_UI':manual,'human_experience_test':False,'observations':['all supplied ratios preserve current/total and progress/target order in Arabic','whole ISO dates and static level ranges are isolated in RTL','current level is fully visible after font/container settling','completed scroll position survives rebuild','no missing glyphs or clipped fixed labels in final scope','original title, panels, borders and fonts reused','actual tier rewards are not present and are not accepted by these frames']},indent=2)+'\n',encoding='utf-8')
cases={}
for stage in ['storage-r88','storage-r89']:
    for node in E.parse(b/stage/'public/season-journey-server.trx').iter():
        if node.tag.endswith('UnitTestResult'):
            assert node.get('outcome')=='Passed';cases[node.get('testName')]={'source':stage,'outcome':'Passed','test_id':node.get('testId')}
assert len(cases)==130
(e/'server-case-union.json').write_text(json.dumps({'count':len(cases),'union_not_one_physical_run':True,'r88':129,'r89':1,'cases':cases},indent=2)+'\n',encoding='utf-8')
native=json.loads((b/'journey-native-r3/checks.json').read_text(encoding='utf-8'));assert native['ok'] and native['checks']==59
wire=json.loads((b/'journey-actual-wire-r2/checks.json').read_text(encoding='utf-8'));assert wire['ok'] and len(wire['checks'])==14
for folder in ['journey-native-r3','journey-actual-wire-r2']:
    proof=json.loads((b/folder/'result.json').read_text(encoding='utf-8'));assert proof['exit']==0 and not proof['engine_errors'] and proof['source_unchanged']
domain_pin=json.loads((b/'local-journey-domain-r4/source-pin.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in domain_pin.items() if n.startswith('server/src/FantasyCard.Domain/'))
for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
    assert (repo/'server/config/generated'/name).read_bytes()==(repo/'client/data/generated'/name).read_bytes()
packs={p.stem:json.loads(p.read_text(encoding='utf-8'))['strings'] for p in (repo/'client/data/locales').glob('*.json')};keys=[k for k in packs['en'] if k.startswith('journey_')]
assert len(packs)==11 and len(keys)==29
for code,pack in packs.items():
    for key in keys:assert key in pack and re.findall(r'%[sd]',pack[key])==re.findall(r'%[sd]',packs['en'][key]),(code,key)
protocol=subprocess.run(['python','tools/generate_network_protocol.py','--check'],capture_output=True,text=True,check=True)
(e/'protocol-check.original.log').write_text(protocol.stdout+protocol.stderr,encoding='utf-8')
guard=[json.loads(row) for stage in ['storage-r88','storage-r89'] for row in (b/stage/'public/resource-guard.original.jsonl').read_text(encoding='utf-8').splitlines()]
result={'status':'C15_experience_contract_core_verified_tier_rewards_pending','C15_complete':False,'whole_goal_complete':False,'completed_items':19,'configuration':'season-v1-config-11','content_hash':'88b5b9dab936d3e24e2a2ecd950a0e56e6445b245011f8dd9615d9f08f2a4176','binary_sha256':'102507840f05eff1efc0029a21a9dd858e4027c0f40e8f767d523ebb09f6cc02','workbook_sha256':'4dd9c25dad21c9a459a5463f208fc3d6b3d50f82fadd759466a0f8add9bee209','old_table_messages_identical':30,'published_tables':32,'published_rows':1760,'client_public_tables':27,'domain_passed':92,'server_union_passed':130,'server_union_not_one_physical_run':True,'native_checks':59,'native_includes_activity_regression_checks':33,'actual_HTTP_wire_files':4,'Godot_actual_wire_checks':14,'Godot_direct_live_connection_claimed':False,'UI':{'final_frames':330,'raw_frames_retained':len(raw),'checks':checks,'locales':11,'widths':[960,1280,1920],'private_inactive_desktop':True},'main_reward_requirement':'unfulfilled: no exact per-tier source list; candidate proposed and user preference requested; no item entitlements/claim implementation yet','resource_minting_from_journey_tiers':False,'source_contract_targets':'candidate3extractions/5elites/1boss,oldest open incomplete week first','catchup_reference':'candidate21days to actual original level20 threshold; cleared-cell XP only','cloud_min_ram':min(row['available_ram'] for row in guard),'cloud_min_disk':min(row['free_disk'] for row in guard),'cloud_min_disk_fraction':min(row['disk_fraction'] for row in guard),'owned_SDKs_removed':['r88','r89'],'production_deployed':False,'production_restarted':False,'season_activated':False,'new_full_game_routes':0,'B05_budget':'291/300','capacity100_retest':False,'retained_failures':['Domain fixture missing namespace r3','HTTP registry None instead of Empty r1','draft workbook string/number adjacency','en first source note clipped','level focus measured before final layout','es entry long title clipped','Arabic ratios reversed despite geometry pass; numeric runs explicitly isolated before final captures']}
(e/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
copy('record-journey-core.py','record-journey-core.py')
manifest={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()}
(e/'manifest.json').write_text(json.dumps({'files':manifest,'external_full_evidence_root':str(b),'all_original_PNGs_retained_with_hashes':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
