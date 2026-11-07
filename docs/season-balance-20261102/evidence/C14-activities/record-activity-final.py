from pathlib import Path
import gzip,hashlib,json,re,shutil,subprocess
import xml.etree.ElementTree as E

repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/C14-activities'
assert not e.exists();e.mkdir()
def copy(relative,dest=None):
    src=b/relative;dst=e/(dest or relative);assert src.is_file(),src
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def top(folder,names):
    for name in names:
        if (b/folder/name).is_file():copy(folder+'/'+name)
for stage in ['storage-r86','storage-r87']:
    for p in (b/stage).iterdir():
        if p.is_file() and p.suffix in ['.json','.log','.py']:
            copy(stage+'/'+p.name)
    shutil.copytree(b/stage/'public',e/stage/'public')
    manifest=json.loads((b/stage/'input-manifest.json').read_text(encoding='utf-8'))
    for n,h in manifest['files'].items():
        if stage=='storage-r86' and n=='server/tests/FantasyCard.Server.Tests/Persistence/PostgresSeasonActivityTests.cs':continue
        assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h,(n,'cloud input changed')
for folder in ['local-config-r10','local-activity-domain-r1']+[f'local-activity-server-build-r{i}' for i in range(1,6)]:
    for p in (b/folder).iterdir():
        if p.is_file() and p.suffix in ['.json','.jsonl','.log']:copy(folder+'/'+p.name)
    for p in (b/folder/'results').glob('*.trx'):copy(folder+'/results/'+p.name)
for folder in ['activity-native-r1','activity-native-r2','activity-native-r3','activity-native-r4','activity-native-r5','activity-native-r6','activity-actual-wire-r1','activity-actual-wire-r2']:
    if not (b/folder).exists():continue
    for p in (b/folder).iterdir():
        if p.is_file() and p.suffix in ['.json','.log','.gd','.bin']:copy(folder+'/'+p.name)
for name in ['prepare-season-activity-r86.py','ship-season-activity-r86.py','observe-season-activity-r86.py','collect-season-activity-r86.py','prepare-season-activity-r87.py','ship-season-activity-r87.py','observe-season-activity-r87.py','collect-season-activity-r87.py','run-activity-native-verbose.py','run-activity-native.py','activity-wire.gd','run-activity-actual-wire-r1.py','run-activity-actual-wire-r2.py','export-activity-config-r10.py','activity-localization-r1.json','retire-activity-accepted-expanded-v15.py','archive-market-expanded-v15.py','resume-activity-expanded-v15.py','resume-activity-expanded-v15-r2.py','ended-expanded-inputs-v15.json','ended-expanded-inputs-v15.before-retirement.json','v15-local-verification.json','v15-prepare.original.log','v15-download.original.log','v15-retire.original.log','v15-resume-state.original.log','v15-resume-retire.original.log','v15-resume-r2.original.log','run-activity-workbook.py']:
    if (b/name).is_file():copy(name)
copy('workbook/season-activity.mjs','workbook/season-activity.mjs')
draft='workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/limited-activities'
for name in ['preservation-proof.json','activity-rows.json','before-exchanges.png','SeasonActivityCalendar-1.png','SeasonActivityRules-1.png','SeasonActivityRules-2.png']:copy(draft+'/'+name,'workbook/'+name)
ui=e/'ui';ui.mkdir();raw=[]
runs=['activity-ui-en-r1','activity-ui-a-r1','activity-ui-b-r1','activity-ui-a-r2','activity-ui-b-r2','activity-ui-c-r1','activity-ui-b-r3','activity-ui-c-r2']
for run in runs:
    src=b/run;dst=ui/run;dst.mkdir()
    for p in src.iterdir():
        if not p.is_file() or p.suffix=='.png':continue
        if p.name in ['review.json','frames.original.jsonl']:(dst/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
        else:shutil.copy2(p,dst/p.name)
    raw.extend({'run':run,'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in src.glob('*.png'))
(ui/'raw-frame-manifest.json').write_text(json.dumps(raw,indent=2)+'\n',encoding='utf-8')
final=[];runtime=None;checks=0
for run in ['activity-ui-a-r2','activity-ui-b-r3','activity-ui-c-r2']:
    report=json.loads((b/run/'review.json').read_text(encoding='utf-8'));terminal=json.loads((b/run/'terminal.original.json').read_text(encoding='utf-8'))
    assert report['render_capture_complete'] and not report['legacy_layout_observations'] and all(report['checks'].values())
    assert terminal['native_exit']==0 and terminal['source_unchanged'] and terminal['all_checked_threads_private'] and terminal['desktop_switch_calls']==0
    pin=json.loads((b/run/'source-pin.original.json').read_text(encoding='utf-8'));current={n:h for n,h in pin.items() if not n.startswith('client\\tests\\')}
    if runtime is None:runtime=current
    else:assert current==runtime
    assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in current.items())
    final.extend(r for r in raw if r['run']==run);checks+=len(report['checks'])
assert len(final)==297 and len({r['file'] for r in final})==297
(ui/'final-frame-manifest.json').write_text(json.dumps({'frames':final,'checks':checks,'runtime_sources_identical':True,'actual_game_matches':0,'initial_a_b_rejected':'Manual review: Arabic dates separated and reversed by bidi. Complete range LTR-isolated and all final states re-rendered.'},indent=2)+'\n',encoding='utf-8')
representatives={'activity-ui-a-r2':['ar_960_c14_active.png','hi_1280_c14_upcoming.png','zh-CN_1920_c14_hall.png'],'activity-ui-b-r3':['ru_960_c14_late.png','en_960_c14_spent.png'],'activity-ui-c-r2':['fr_1280_c14_exchange_confirm.png','ar_960_c14_claim_confirm.png']}
manual={}
for run,names in representatives.items():
    for name in names:
        target=ui/('final-'+name);shutil.copy2(b/run/name,target);manual[name]={'run':run,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(ui/'manual-review.json').write_text(json.dumps({'reviewer':'assistant visual inspection','accepted':manual,'human_experience_test':False,'notes':['original game panels, borders, fonts and palette retained','ISO dates and start-to-end order inspected in Arabic after complete LTR isolation','original-source pending/claimed state and shared exhausted budget legible','Hindi shaping, translated confirmation text and camp entry inspected','font minimum and local/cloud guards not lowered']},indent=2)+'\n',encoding='utf-8')
packs={p.stem:json.loads(p.read_text(encoding='utf-8'))['strings'] for p in (repo/'client/data/locales').glob('*.json')};keys=[k for k in packs['en'] if k.startswith('activity_')]
assert len(packs)==11 and len(keys)==21
for code,pack in packs.items():
    for key in keys:assert key in pack and re.findall(r'%[sd]',pack[key])==re.findall(r'%[sd]',packs['en'][key]),(code,key)
protocol=subprocess.run(['python','tools/generate_network_protocol.py','--check'],capture_output=True,text=True,check=True)
(e/'protocol-check.original.log').write_text(protocol.stdout+protocol.stderr,encoding='utf-8')
cases={}
for stage in ['storage-r86','storage-r87']:
    for node in E.parse(b/stage/'public/season-activity-server.trx').iter():
        if node.tag.endswith('UnitTestResult'):
            assert node.get('outcome')=='Passed'
            cases[node.get('testName')]={'outcome':'Passed','source':stage,'test_id':node.get('testId')}
assert len(cases)==114
(e/'server-case-union.json').write_text(json.dumps({'count':len(cases),'union_not_one_physical_run':True,'cases':cases},indent=2)+'\n',encoding='utf-8')
native=json.loads((b/'activity-native-r6/checks.json').read_text(encoding='utf-8'));assert native['ok'] and native['checks']==33
wire=json.loads((b/'activity-actual-wire-r2/checks.json').read_text(encoding='utf-8'));assert wire['ok'] and len(wire['checks'])==17
for folder in ['activity-native-r6','activity-actual-wire-r2']:
    proof=json.loads((b/folder/'result.json').read_text(encoding='utf-8'));assert proof['exit']==0 and not proof['engine_errors'] and proof['source_unchanged']
guard=[json.loads(r) for r in (b/'storage-r86/public/resource-guard.original.jsonl').read_text(encoding='utf-8').splitlines()]
result={'status':'C14_current_scope_complete','whole_goal_complete':False,'configuration':'season-v1-config-10','content_hash':'c4e4bf5b9cc425f176c2c4a5568fe05ef4f2bb7a3384dd3d90cdd2e3af20396a','binary_sha256':'068b8c49129d4aa528ad163b368a85017ea6d8055793b374e1663aa302dd37a7','workbook_sha256':'54e8c0c85b1a4a7301fba2a96a85e79e67c155af0843f1fb70c24eff46d22ff0','old_table_messages_identical':28,'new_tables':2,'published_tables':30,'published_rows':1756,'client_public_tables':25,'domain_passed':47,'server_targeted_union_passed':114,'server_r86_passed':113,'server_r87_pagination_passed':1,'server_union_not_one_physical_run':True,'server_failed':0,'server_skipped':0,'native_mechanism_checks':33,'actual_server_wire_files':4,'actual_wire_Godot_checks':17,'direct_Godot_live_connection_claimed':False,'UI':{'final_frames':len(final),'raw_frames_retained':len(raw),'checks':checks,'locales':11,'widths':[960,1280,1920],'private_inactive_desktop':True},'cloud_min_ram':min(r['available_ram'] for r in guard),'cloud_min_disk':min(r['free_disk'] for r in guard),'cloud_min_disk_fraction':min(r['disk_fraction'] for r in guard),'owned_sdk_removed':True,'cloud_original_source_public_retained':True,'expanded_snapshot_v15_sha256':'da4e16b41c4e960a182ebd828cbac2430d2c48f7ddf33209a5b7554e9c1ded13','expanded_snapshot_members':937,'production_deployed':False,'production_restarted':False,'production_season_activated':False,'new_B05_routes':0,'B05_budget':'291/300','capacity100_retest':False,'operator_candidate_parameters':'42-day calendar days12/33,3days each;Extracted4 tokens,cap12;late original-event exchange enabled;not claimed as GDD fixed dates','retained_failures':['local build CA1861','local fixture missing namespace','native negative fixture merged without overwrite','initial Arabic dates bidi manual rejection','pending screenshot fixture omitted redeemed per-rule counts','native abrupt exit with Main ui_open cue still active; fixture muted before final repeat','two SSH cleanup timeouts; full snapshot and members verified first; same exact source resumed safely']}
(e/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(e).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in e.rglob('*') if p.is_file()}
(e/'manifest.json').write_text(json.dumps({'files':manifest,'external_full_evidence_root':str(b),'full_PNGs_retained_with_hashes':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
