from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();folder=base/'d04-lifecycle-cloud-r1-file';public=folder/'public'
build=json.loads((base/'d04-lifecycle-build-r2/result.json').read_bytes());assert build['exit']==0 and build['source_unchanged']
assert json.loads((base/'d04-lifecycle-build-r1/result.json').read_bytes())['exit']!=0
result=json.loads((folder/'result.json').read_bytes());assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
archive=folder/'public-evidence.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(archive) as bundle:
    for item in bundle.getmembers():assert bundle.extractfile(item).read()==(public/item.name).read_bytes()
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'};cases=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns)
assert len(cases)==4 and all(c.attrib['outcome']=='Passed' for c in cases)
proofs={row['kind']:row for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (row:=json.loads(line))}
destroy=proofs['actual-destruction-events'];r=destroy['report'];assert len(r['Events'])==2 and r['SourcesComplete']
assert all(e['EventName']=='item_destroyed' and e['PhysicalFlow']=='Destroy' and e['Quality']=='Purple' and e['Dimensions']['DifficultyId'] is None and e['Dimensions']['CellType']=='Lobby' for e in r['Events'])
assert sum(g['Items'] for g in r['PhysicalFlows'])==2 and destroy['replayOnce'] and destroy['mainItemNotDestroyed'] and destroy['queryFingerprintUnchanged']
incomplete=destroy['incomplete'];c=next(c for c in incomplete['Sources'] if c['Source']=='inventory_movements');assert c['UnclassifiedRows']==c['MissingRealmRows']==1 and not incomplete['SourcesComplete']
arch=proofs['actual-equipment-archive-events'];r=arch['report'];assert len(r['Events'])==2 and r['SourcesComplete']
assert all(e['EventName']=='season_asset_archived' and e['PhysicalFlow']=='Archive' and e['Dimensions']['DifficultyId'] is None for e in r['Events'])
assert {e['ToLocation'] for e in r['Events']}=={'Recycled','SeasonArchive'} and sum(g['Items'] for g in r['PhysicalFlows'])==2 and arch['alreadyDestroyedNotDestroyedAgain'] and arch['originalDefinitionImmutable'] and arch['queryFingerprintUnchanged']
diff=proofs['actual-difficulty-events'];r=diff['report'];assert r['SourcesComplete'] and len(r['Events'])==1 and r['PhysicalFlows']==[]
e=r['Events'][0];d=e['Dimensions'];assert e['EventName']=='difficulty_cleared' and d['DifficultyId']=='D0' and d['HeroClass']=='Mage' and d['PlayerKind']=='Human' and d['CellType']=='RunSummary' and d['Result']=='Extracted'
assert d['BuildType'] is None and d['GrowthStage'] is None and diff['deathAndReplayNotClears'] and diff['queryFingerprintUnchanged'] and diff['declaredTerminalCheckpointFixture'] and diff['completedGameplayEncounters']==diff['gameplayCasts']==0
api=proofs['actual-lifecycle-events-admin-HTTP'];assert api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['privateNoStore'] and api['report']['events']==[]
rows=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()];starts=[r['evidence']['Id'] for r in rows if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in rows if r['caseId']=='process-stop'];assert len(starts)==1 and starts==stops
assert len(result['owned_schemas'])==4 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
pin=json.loads((base/'d04-lifecycle-build-r2/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items())
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(row['source']).read_bytes()).hexdigest()==row['sha256'] for row in context['D03_latest_banks'])
proof=dict(lifecycle_event_subchain_verified=True,compile_passed=True,original_fixture_compile_failure_retained=True,PG_and_actualHTTP_passed=4,named_event_sources=['difficulty_cleared','item_destroyed','season_asset_archived'],equipment_archive_only_not_wallet_recipe=True,destruction_not_archive=True,main_enhanced_item_not_destroyed=True,lobby_D0_placeholder_not_played_difficulty=True,original_run_difficulty_hero_human_proven=True,death_and_replay_not_add_clear=True,unknown_history_not_invented=True,missing_combat_dimensions_explicit=True,read_only_fingerprints_unchanged=True,actual_program_processes=1,all_resources_cleaned=True,source_unchanged=True,capital_banks_unchanged=True,new_gameplay_campaign_cases=0,D04_complete=False,progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'])
target=base/'d04-lifecycle-independent-audit-r1.derived.json';assert not target.exists();target.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
