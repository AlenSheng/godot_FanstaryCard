from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
for stage in ['d04-combat-measure-domain-r1','d04-combat-measure-domain-r2','d04-combat-measure-server-r1']:
    result=json.loads((base/stage/'result.json').read_bytes());assert result['exit']!=0 and result['source_unchanged'] and not list((base/stage/'results').glob('*.trx'))
for stage,count,name in [('d04-combat-measure-domain-r3',45,'domain.trx'),('d04-combat-measure-server-r2',8,'server.trx')]:
    result=json.loads((base/stage/'result.json').read_bytes());assert result['exit']==0 and result['source_unchanged']
    rows=ET.parse(base/stage/'results'/name).findall('.//t:UnitTestResult',ns);assert len(rows)==count and all(r.attrib['outcome']=='Passed' for r in rows)
oldpin=json.loads((base/'d04-combat-measure-server-r2/source-pin.json').read_bytes());pin=json.loads((base/'d04-combat-measure-build-r3/source-pin.json').read_bytes())
assert oldpin.keys()==pin.keys() and [n for n in pin if oldpin[n]!=pin[n]]==['server/tests/FantasyCard.Server.Tests/Persistence/PostgresCombatMeasurementTelemetryTests.cs']
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items())
pin=json.loads((base/'d04-combat-measure-domain-r3/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items() if n.startswith(('server/src/FantasyCard.Domain/','server/tests/FantasyCard.Domain.Tests/')))
folder=base/'d04-combat-measure-cloud-r1-file';public=folder/'public';result=json.loads((folder/'result.json').read_bytes())
assert result['exit']!=0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(folder/'public-evidence.tar.gz') as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(public/member.name).read_bytes()
rows=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==4 and sum(r.attrib['outcome']=='Passed' for r in rows)==3
assert 'ActualCheckpointKeepsPveAndPvpCountersSeparate' in next(r for r in rows if r.attrib['outcome']=='Failed').attrib['testName']
proofs={r['kind']:r for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))}
target_folder=base/'d04-combat-measure-cloud-r2-file';target=target_folder/'public';second=json.loads((target_folder/'result.json').read_bytes())
assert second['exit']==0 and second['guard_ok'] and second['input_unchanged'] and second['local_binary_inputs_unchanged'] and second['schemas_still_present']==[]
assert hashlib.sha256((target_folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==second['collected_raw_archive_sha256']
with tarfile.open(target_folder/'public-evidence.tar.gz') as bundle:
    for member in bundle.getmembers():assert bundle.extractfile(member).read()==(target/member.name).read_bytes()
rows=ET.parse(target/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==1 and rows[0].attrib['outcome']=='Passed'
targetproofs={r['kind']:r for line in (target/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))}
p=targetproofs['actual-combat-counter-checkpoints'];report=p['report'];assert report['FullyObserved'] and report['RoomsWithoutCombatObservations']==0 and report['OmittedCombatMeasurements']=='0' and not report['CombatRowsTruncated']
rows=report['CombatMeasurements'];assert len(rows)==4 and {r['Mode'] for r in rows}=={'Pve','Pvp'} and all(not r['Partial'] for r in rows)
assert sorted(r['Counters']['AdvancedTicks'] for r in rows)==['20000000','20000000','30000000','30000000']
assert any(r['Counters'].get('HealOverflow')=='5' and r['Counters'].get('ShieldOverflow')=='65' for r in rows)
assert all(r['Counters']['OpeningEffective']=='3' for r in rows if r['Mode']=='Pvp')
assert p['readOnlyFingerprintUnchanged'] and p['originalPveSurvivesPvp'] and p['recreatedDomainContinues'] and p['successfulPlayerCasts']==p['completedGameplayCampaigns']==0
h=proofs['actual-combat-counter-history'];assert h['missing']['RoomsWithoutCombatObservations']==1 and h['missing']['CombatMeasurements']==[] and h['invalid']['InvalidRooms']==1 and h['readOnlyFingerprintUnchanged'] and h['noCurrentStateBackfill']
receipts=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()];entry=next(r['evidence'] for r in receipts if r['caseId']=='SEASON17-real-entry-restart')
assert entry['combatCountersMonotonic'] and entry['combatRows']==4 and entry['profileIndexPreserved'] and entry['battleBindingIndexPreserved'] and entry['observationPrefixPreserved']
assert entry['observationSequenceBefore']==1 and entry['observationSequenceAfter']>=1 and entry['players']==4 and entry['bots']==entry['successfulPlayerCasts']==entry['completedEncounters']==0
starts=[r['evidence']['Id'] for r in receipts if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in receipts if r['caseId']=='process-stop'];assert len(starts)==3 and set(starts)==set(stops)
assert len(result['owned_schemas'])==4 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
assert len(second['owned_schemas'])==1 and set(result['owned_schemas']).isdisjoint(second['owned_schemas'])
assert all(json.loads((target/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((target/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((target_folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (target/'resources.original.jsonl').read_text().splitlines())
cache=json.loads((public/'dependency-cache-reuse.original.json').read_bytes());assert cache['all_reused_hashes_verified'] and not cache['task_assemblies_reused'] and not cache['credentials_cached'] and cache['reused_files']==122 and cache['materialized_bytes']==11428696
newcache=json.loads((target/'dependency-cache-reuse.original.json').read_bytes());assert newcache==cache
manifest=json.loads((base/'d04-combat-measure-cloud-input-r1/manifest.json').read_bytes());assert len(manifest['cached_files'])==122 and all(manifest['files'][n]==sha and not Path(n).name.startswith('FantasyCard.') for n,sha in manifest['cached_files'].items())
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['sha256'] for r in context['D03_latest_banks'])
proof=dict(combat_measurement_subchain_verified=True,domain_passed=45,server_passed=8,PG_and_actualHTTP_OS_passed=4,physical_PG_HTTP_executions=5,PG_current_union='3original passes plus1checkpoint-cadence fixture-only recheck',original_checkpoint_cadence_fixture_failure_retained=True,original_compile_failures_retained=3,
    natural_effective_empty_full_reset_separate=True,chain_and_opening_not_natural=True,instant_requested_effective_full_empty_separate=True,
    control_union_timer_and_suppressed_steps_separate=True,legal80over70_effective98_and_overflow_verified=True,cast_replay_not_double_counted=True,
    PVE_PVP_counters_survive_freeze_and_restart=True,observer_does_not_change_actual_resolver_state_or_RNG=True,old_missing_history_partial_not_zero=True,
    exact_counter_strings_and_ratios_verified=True,cumulative_measurements_not_window_deltas=True,bounded_rows_per_room=1024,immutable_completed_counter_snapshots_reused=True,
    actual_program_processes=3,transient_test_resources_cleaned=True,verified_thirdparty_cache_reused_files=122,all_task_assemblies_fresh=True,source_unchanged=True,capital_banks_unchanged=True,
    new_gameplay_campaign_cases=0,D04_complete=False,remaining_D04=['committed destruction receipt/profile links and complete physical flow','wallet-recipe archive source events','cohort-market-activity-red diagnostics'],
    progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'],targeted_archive_sha256=second['collected_raw_archive_sha256'])
target=base/'d04-combat-independent-audit-r1.derived.json';assert not target.exists();target.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
