from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
for group,count in [('domain',20),('server',1)]:
    folder=base/f'd04-room-events-{group}-r2';r=json.loads((folder/'result.json').read_bytes());assert r['exit']==0 and r['source_unchanged']
    cases=ET.parse(folder/'results'/f'{group}.trx').findall('.//t:UnitTestResult',ns);assert len(cases)==count and all(c.attrib['outcome']=='Passed' for c in cases)
folder=base/'d04-room-events-cloud-r1-file';public=folder/'public';result=json.loads((folder/'result.json').read_bytes())
assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
archive=folder/'public-evidence.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(archive) as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(public/member.name).read_bytes()
cases=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(cases)==4 and all(c.attrib['outcome']=='Passed' for c in cases)
proofs={row['kind']:row for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (row:=json.loads(line))}
p=proofs['actual-room-event-checkpoints'];r=p['report'];assert r['FullyObserved'] and len(r['Events'])==6 and len({e['EventId'] for e in r['Events']})==6
assert [e['Event']['Sequence'] for e in r['Events']]==[1,2,3,4,5,6] and r['DroppedEvents']=='0' and r['OmittedItems']==0
assert p['originalPrefixSurvivesNewestOnlySave'] and p['restartSequenceContinues'] and p['queryFingerprintUnchanged'] and p['successfulPlayerCasts']==p['completedGameplayEncounters']==0
loss=next(e['Event'] for e in r['Events'] if e['Event']['Items']);assert loss['Result']=='RelicCustodyPendingSettlement' and loss['Items'][0]['Quantity']==9
g=proofs['actual-room-event-history-gaps'];assert g['missing']['LegacyUnobservedRooms']==1 and g['invalid']['InvalidRooms']==1 and not g['missing']['FullyObserved'] and not g['invalid']['FullyObserved'] and g['queryFingerprintUnchanged'] and g['noHistoryBackfill']
api=proofs['actual-room-events-admin-HTTP'];assert api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['privateNoStore'] and api['report']['events']==[]
receipts=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()]
entry=next(row['evidence'] for row in receipts if row['caseId']=='SEASON17-real-entry-restart')
assert entry['startedAtPreserved'] and entry['observationPrefixPreserved'] and entry['observationSequenceAfter']>=entry['observationSequenceBefore']
assert entry['observationSequenceBefore']==entry['observationSequenceAfter']==0
assert entry['players']==4 and entry['bots']==entry['successfulPlayerCasts']==entry['completedEncounters']==0 and entry['firstPid']!=entry['secondPid']
starts=[row['evidence']['Id'] for row in receipts if row['caseId']=='process-start'];stops=[row['evidence']['ProcessId'] for row in receipts if row['caseId']=='process-stop'];assert len(starts)==3 and set(starts)==set(stops)
assert len(result['owned_schemas'])==4 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
domainpin=json.loads((base/'d04-room-events-domain-r2/source-pin.json').read_bytes())
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in domainpin.items() if n.startswith(('server/src/FantasyCard.Domain/','server/tests/FantasyCard.Domain.Tests/')))
oldpin=json.loads((base/'d04-room-events-server-r2/source-pin.json').read_bytes());newpin=json.loads((base/'d04-room-events-build-r3/source-pin.json').read_bytes())
assert oldpin.keys()==newpin.keys() and [n for n in newpin if oldpin[n]!=newpin[n]]==['server/tests/FantasyCard.Server.Tests/EndToEnd/ProcessLifecycleSeasonCreditTests.cs']
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in newpin.items())
assert json.loads((base/'d04-room-events-build-r3/result.json').read_bytes())['exit']==0
target=base/'d04-room-events-cloud-r2-file';extra=target/'public';second=json.loads((target/'result.json').read_bytes())
assert second['exit']==0 and second['guard_ok'] and second['input_unchanged'] and second['local_binary_inputs_unchanged'] and second['schemas_still_present']==[]
assert hashlib.sha256((target/'public-evidence.tar.gz').read_bytes()).hexdigest()==second['collected_raw_archive_sha256']
with tarfile.open(target/'public-evidence.tar.gz') as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(extra/member.name).read_bytes()
cases=ET.parse(extra/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(cases)==1 and cases[0].attrib['outcome']=='Passed'
rows=[json.loads(line) for line in (extra/'process-logs/receipts.jsonl').read_text().splitlines()]
nonempty=next(row['evidence'] for row in rows if row['caseId']=='SEASON17-real-entry-restart')
assert nonempty['observationSequenceBefore']==1 and nonempty['observationSequenceAfter']>=1 and nonempty['observationPrefixPreserved'] and nonempty['startedAtPreserved']
assert nonempty['declaredObservationMarkerAfterOldProcessExit'] and nonempty['gameplayFieldsUnchangedByMarker']
assert nonempty['players']==4 and nonempty['bots']==nonempty['successfulPlayerCasts']==nonempty['completedEncounters']==0
newstarts=[row['evidence']['Id'] for row in rows if row['caseId']=='process-start'];newstops=[row['evidence']['ProcessId'] for row in rows if row['caseId']=='process-stop'];assert len(newstarts)==2 and set(newstarts)==set(newstops)
first_container=json.loads((public/'runtime-handle.original.json').read_bytes())['container_id'];second_container=json.loads((extra/'runtime-handle.original.json').read_bytes())['container_id']
assert first_container!=second_container and len({(first_container,pid) for pid in starts}|{(second_container,pid) for pid in newstarts})==5
assert len(second['owned_schemas'])==1 and set(result['owned_schemas']).isdisjoint(second['owned_schemas'])
assert all(json.loads((extra/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((extra/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((target/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (extra/'resources.original.jsonl').read_text().splitlines())
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(b['source']).read_bytes()).hexdigest()==b['sha256'] for b in context['D03_latest_banks'])
proof=dict(room_event_subchain_verified=True,domain_passed=20,server_coalescing_passed=1,PG_and_actualHTTP_entry_passed=4,physical_PG_HTTP_executions=5,current_union='3unaffected original cases plus1enhanced nonempty actualOS case',original_empty_prefix_case_retained=True,actual_program_processes=5,
    named_event_hooks=['battle_finished','loot_generated','loot_chosen','loot_extracted','loot_lost'],maximum_events_per_room=4096,maximum_items_per_event=128,
    explicit_capacity_gaps_verified=True,cumulative_history_survives_coalescing=True,refresh_replay_does_not_add_events=True,zero_heal_choice_retained=True,
    interrupted_frozen_PVE_observed=True,old_missing_not_invented=True,invalid_new_observations_rejected_or_reported=True,
    gameplay_state_prices_randomness_unchanged_in_paired_fixture=True,original_event_identity_prefix_recovers=True,actual_READY_nonempty_declared_observation_survives_process_restart=True,nonempty_marker_not_claimed_as_organic_gameplay_event=True,
    room_exit_and_relic_custody_not_claimed_as_asset_commit=True,private_admin_boundary_verified=True,all_test_resources_cleaned=True,source_unchanged=True,
    capital_banks_unchanged=True,new_gameplay_campaign_cases=0,D04_complete=False,remaining_D04=['full build/growth dimensions','wallet/recipe archive events and complete physical flows','combat draw/control/overflow observations','cohort-market-activity diagnostics'],
    progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'],nonempty_archive_sha256=second['collected_raw_archive_sha256'])
path=base/'d04-room-events-independent-audit-r1.derived.json';assert not path.exists();path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
