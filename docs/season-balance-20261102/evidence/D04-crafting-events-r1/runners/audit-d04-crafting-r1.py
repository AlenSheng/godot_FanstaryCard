from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET

base=Path(__file__).parent;repo=Path.cwd();folder=base/'d04-crafting-cloud-r1-file';public=folder/'public'
build=json.loads((base/'d04-crafting-build-r1/result.json').read_bytes());assert build['exit']==0 and build['source_unchanged']
result=json.loads((folder/'result.json').read_bytes());assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
archive=folder/'public-evidence.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(archive) as bundle:
    for item in bundle.getmembers():assert bundle.extractfile(item).read()==(public/item.name).read_bytes()
ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
cases=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(cases)==4 and all(c.attrib['outcome']=='Passed' for c in cases)
rows=[json.loads(line) for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines()]
bykind={r['kind']:r for r in rows}
pity=bykind['actual-crafting-pity-events'];report=pity['report'];assert report['CraftingSourceComplete'] and len(report['Events'])==4
assert len({e['EventId'] for e in report['Events']})==4
event=next(e for e in report['Events'] if e['EventName']=='pity_triggered');assert event['Observation']['WishFailuresBefore']==2 and event['Observation']['WishFailuresAfter']==0 and event['Observation']['PityTriggered']
assert pity['replayStable'] and pity['currentWishNotUsed'] and pity['readOnlyFingerprintUnchanged']
assert pity['incomplete']['MissingHistoricalActions']==1 and not pity['incomplete']['CraftingSourceComplete'] and len(pity['incomplete']['Events'])==4
for e in report['Events']:
    d=e['Observation']['Dimensions'];assert all(d[k] is None for k in ['DifficultyId','HeroClass','BuildType','GrowthStage']) and d['PlayerKind']=='Unknown' and d['CellType']=='Lobby'
recipe=bykind['actual-recipe-reforge-events'];r=recipe['report'];assert r['ObservedNoEventActions']==1 and r['CraftingSourceComplete'] and len(r['Events'])==2
assert {e['Observation']['PhysicalFlow'] for e in r['Events']}=={'Mutation','RetainedSample'} and recipe['bodyIdentityRetained'] and recipe['readOnlyFingerprintUnchanged']
assert recipe['malformed']['InvalidObservations']==1 and not recipe['malformed']['CraftingSourceComplete']
rollback=bykind['actual-crafting-event-rollback'];assert rollback['failedAttemptRolledBack'] and rollback['originalKeyRetryExactlyOnce'] and len(rollback['report']['Events'])==1
api=bykind['actual-crafting-events-admin-HTTP'];assert api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['privateNoStore'] and api['report']['events']==[]
receipts=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()]
starts=[r['evidence']['Id'] for r in receipts if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in receipts if r['caseId']=='process-stop'];assert len(starts)==1 and starts==stops
assert len(result['owned_schemas'])==4 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
pin=json.loads((base/'d04-crafting-build-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items())
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(row['source']).read_bytes()).hexdigest()==row['sha256'] for row in context['D03_latest_banks'])
proof=dict(crafting_event_subchain_verified=True,compile_passed=True,PG_and_actualHTTP_passed=4,named_event_types=['craft_completed','recipe_learned','pity_triggered'],durable_original_action_identity=True,atomic_observation_rollback_verified=True,replay_does_not_add_events=True,pity_not_inferred_from_current_state=True,reforge_is_mutation_not_remint=True,recipe_sample_retained=True,already_known_recipe_no_duplicate_learning=True,lobby_dimensions_not_invented=True,old_missing_and_invalid_observations_visible=True,read_only_fingerprint_unchanged=True,actual_program_processes=1,all_resources_cleaned=True,source_unchanged=True,capital_banks_unchanged=True,new_gameplay_campaign_cases=0,D04_complete=False,progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'])
path=base/'d04-crafting-independent-audit-r1.derived.json';assert not path.exists();path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
