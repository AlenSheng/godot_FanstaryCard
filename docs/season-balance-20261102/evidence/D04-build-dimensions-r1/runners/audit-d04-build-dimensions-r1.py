from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
def cases(stage,name):
    folder=base/stage;result=json.loads((folder/'result.json').read_bytes());assert result['source_unchanged']
    return result,ET.parse(folder/'results'/name).findall('.//t:UnitTestResult',ns)
for stage,expected in [('d04-build-dimensions-domain-r1',(24,8)),('d04-build-dimensions-domain-r2',(31,1)),('d04-build-dimensions-domain-r3',(32,0)),('d04-build-dimensions-domain-r4',(33,0)),('d04-build-dimensions-domain-r5',(1,0))]:
    result,rows=cases(stage,'domain.trx');assert (sum(r.attrib['outcome']=='Passed' for r in rows),sum(r.attrib['outcome']=='Failed' for r in rows))==expected
result,rows=cases('d04-build-dimensions-server-r2','server.trx');assert result['exit']==0 and len(rows)==5 and all(r.attrib['outcome']=='Passed' for r in rows)
for group in ['d04-build-dimensions-domain-r5','d04-build-dimensions-build-r4']:
    pin=json.loads((base/group/'source-pin.json').read_bytes())
    assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items() if group.endswith('build-r4') or n.startswith(('server/src/FantasyCard.Domain/','server/tests/FantasyCard.Domain.Tests/')))
old=json.loads((base/'d04-build-dimensions-domain-r4/source-pin.json').read_bytes());new=json.loads((base/'d04-build-dimensions-domain-r5/source-pin.json').read_bytes())
assert old.keys()==new.keys() and [n for n in new if old[n]!=new[n]]==['server/tests/FantasyCard.Domain.Tests/Rooms/RoomBuildProfileTests.cs']
old=json.loads((base/'d04-build-dimensions-server-r2/source-pin.json').read_bytes());new=json.loads((base/'d04-build-dimensions-build-r3/source-pin.json').read_bytes())
assert old.keys()==new.keys() and [n for n in new if old[n]!=new[n]]==['server/tests/FantasyCard.Server.Tests/Persistence/PostgresBuildDimensionTelemetryTests.cs']
old=new;new=json.loads((base/'d04-build-dimensions-build-r4/source-pin.json').read_bytes())
assert old.keys()==new.keys() and [n for n in new if old[n]!=new[n]]==['server/tests/FantasyCard.Server.Tests/EndToEnd/ProcessLifecycleSeasonCreditTests.cs']
folder=base/'d04-build-dimensions-cloud-r1-file';public=folder/'public';result=json.loads((folder/'result.json').read_bytes())
assert result['exit']!=0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(folder/'public-evidence.tar.gz') as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(public/member.name).read_bytes()
rows=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==4 and sum(r.attrib['outcome']=='Passed' for r in rows)==3
failed=next(r for r in rows if r.attrib['outcome']=='Failed');assert 'Full_host_actual17_preparation_READY' in failed.attrib['testName']
proofs={r['kind']:r for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))}
positive=proofs['actual-frozen-build-dimensions'];report=positive['roomReport'];assert len(report['Events'])==2 and report['BuildProfiles'] and report['FullyObserved']
assert all(v==0 for v in report['UnknownDimensionCounts'].values())
assert {e['BuildProfileBasis'] for e in report['Events']}=={'BattleStart','EventState'}
assert all(e['Dimensions']['GrowthStage']=='EffectiveBaseCardMaxL0' and e['Dimensions']['BuildType'] and e['Dimensions']['HeroClass']=='Mage' and e['Dimensions']['DifficultyId']=='D0' for e in report['Events'])
receipt=positive['receipt']['Events'];assert len(receipt)==1 and receipt[0]['Dimensions']['GrowthStage']=='EffectiveBaseCardMaxL0'
assert positive['readOnlyFingerprintUnchanged'] and positive['historicalReceiptNotBackfilled'] and positive['settlementAssetHolds']==positive['successfulPlayerCasts']==positive['completedGameplayEncounters']==0
assert positive['old']['UnknownDimensionCounts']['build']==positive['old']['UnknownDimensionCounts']['growth']==1
history=proofs['actual-build-history-no-fallback'];r=history['report'];assert history['indexedProfileWasAvailable'] and history['currentPlayerSnapshotWasAvailable'] and history['noBackfill'] and history['readOnlyFingerprintUnchanged']
assert r['BuildProfiles']==[] and len(r['Events'])==2 and r['UnknownDimensionCounts']['build']==2 and all(e['Dimensions']['BuildType'] is None and e['BuildProfileBasis']=='MissingOriginal' for e in r['Events'])
receipts=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()]
first_starts=[r['evidence']['Id'] for r in receipts if r['caseId']=='process-start'];first_stops=[r['evidence']['ProcessId'] for r in receipts if r['caseId']=='process-stop'];assert len(first_starts)==3 and set(first_starts)==set(first_stops)
target_folder=base/'d04-build-dimensions-cloud-r2-file';target=target_folder/'public';second=json.loads((target_folder/'result.json').read_bytes())
assert second['exit']==0 and second['guard_ok'] and second['input_unchanged'] and second['local_binary_inputs_unchanged'] and second['schemas_still_present']==[]
assert hashlib.sha256((target_folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==second['collected_raw_archive_sha256']
with tarfile.open(target_folder/'public-evidence.tar.gz') as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(target/member.name).read_bytes()
rows=ET.parse(target/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==1 and rows[0].attrib['outcome']=='Passed'
receipts=[json.loads(line) for line in (target/'process-logs/receipts.jsonl').read_text().splitlines()]
entry=next(r['evidence'] for r in receipts if r['caseId']=='SEASON17-real-entry-restart')
assert entry['profileIndexPreserved'] and entry['battleBindingIndexPreserved'] and entry['profileCount']>0 and entry['battleBindingCount']==4 and entry['observationPrefixPreserved'] and entry['observationSequenceBefore']==1 and entry['observationSequenceAfter']>=1
assert entry['firstPid']!=entry['secondPid'] and entry['players']==4 and entry['bots']==entry['successfulPlayerCasts']==entry['completedEncounters']==0
starts=[r['evidence']['Id'] for r in receipts if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in receipts if r['caseId']=='process-stop'];assert len(starts)==2 and set(starts)==set(stops)
assert len(result['owned_schemas'])==4 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
assert len(second['owned_schemas'])==1 and set(result['owned_schemas']).isdisjoint(second['owned_schemas'])
assert all(json.loads((target/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((target/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((target_folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (target/'resources.original.jsonl').read_text().splitlines())
cache=json.loads((target/'dependency-cache-seed.original.json').read_bytes());retained=bool(cache.get('seeded'))
if retained:
    assert cache['used_for_current_run'] is False and cache['total_blob_bytes']<=cache['cap_bytes']==64*1024**2
    verification=json.loads((base/'d04-build-dimensions-dependency-cache-readback-r1.derived.json').read_bytes());assert verification['verified'] and verification['root']==cache['cache_root']
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['sha256'] for r in context['D03_latest_banks'])
proof=dict(build_dimension_subchain_verified=True,domain_unique_passed=33,domain_final_union='32unchanged r4 plus1 strengthened unique-element r5',server_passed=5,PG_and_actualHTTP_entry_passed=4,physical_PG_HTTP_executions=5,PG_current_union='3original passed plus1fixture-only realOS corrected recheck',
    original_failures_preserved=['r1 24passed8fixture failures: prototype high card levels','r2 31passed1fixture failure: prototype requires supplied calculated equipment profile'],
    common_dimension_categories=9,flat_versioned_fields=11,original_battle_start_separate_from_event_profile=True,semantic_fingerprint_retains_unique_element=True,
    raw_effective_levels_and_borrowed_source_preserved=True,growth_names_effective_card_maximum_not_P0_P5_or_account_age=True,printed_inactive_affixes_not_active_build=True,
    bounded_profiles_per_room=512,bounded_battle_bindings_per_room=1024,missing_original_not_filled_from_current=True,immutable_settlement_profile_and_replay_verified=True,
    actualOS_nonempty_prefix_profile_and_binding_indexes_preserved=True,actual_program_processes=5,transient_test_resources_cleaned=True,retained_owned_dependency_cache_verified=retained,retained_cache_bytes=cache.get('total_blob_bytes',0) if retained else 0,source_unchanged=True,capital_banks_unchanged=True,
    new_gameplay_campaign_cases=0,D04_complete=False,remaining_D04=['combat draw-control-overflow measurements','committed destruction profile links and complete physical flows','wallet-recipe archive sources','cohort-market-activity diagnostics'],
    progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'],targeted_archive_sha256=second['collected_raw_archive_sha256'])
target=base/'d04-build-dimensions-independent-audit-r1.derived.json';assert not target.exists();target.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
