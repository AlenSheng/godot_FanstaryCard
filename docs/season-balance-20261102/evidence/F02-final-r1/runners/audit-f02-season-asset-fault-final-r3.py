from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
stages=['f02-season-asset-fault-cloud-r1','f02-season-asset-fault-cloud-r2','f02-season-asset-fault-cloud-r3-retry1'];data={};all_starts=[];all_stops=[];resources=[]
for stage in stages:
 folder=base/stage;result=json.loads((folder/'result.json').read_bytes());public=folder/'public'
 assert result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
 if stage!=stages[0]:assert result['exit']==0
 assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
 with tarfile.open(folder/'public-evidence.tar.gz') as bundle:
  for m in bundle.getmembers():assert bundle.extractfile(m).read()==(public/m.name).read_bytes()
 cases=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);rows=[json.loads(s) for s in (public/'process-logs/receipts.jsonl').read_text(encoding='utf-8').splitlines()]
 def group(name):return [x['evidence'] for x in rows if x['caseId']==name]
 starts=group('process-start');stops=group('process-stop');assert {s['Id'] for s in starts}=={s['ProcessId'] for s in stops}
 assert all(s['ExitCode']==137 and s['termination']=='Process.Kill(entireProcessTree:true)' for s in stops)
 all_starts.extend((stage,s['Id']) for s in starts);all_stops.extend((stage,s['ProcessId']) for s in stops)
 for name in ['cleanup.original.json','input-cache-cleanup.original.json']:
  clean=json.loads((public/name).read_bytes());assert all(clean[k] for k in (['owned_container_removed','private_env_removed'] if name=='cleanup.original.json' else ['tmpfs_unmounted','input_files_removed']))
 resources.extend(json.loads(s) for s in (public/'resources.original.jsonl').read_text().splitlines())
 data[stage]=dict(result=result,cases=cases,rows=rows,final=group('SEASON-ASSET-final'))
assert len(data[stages[0]]['cases'])==3 and sum(c.attrib['outcome']=='Passed' for c in data[stages[0]]['cases'])==1
assert len(data[stages[1]]['cases'])==2 and all(c.attrib['outcome']=='Passed' for c in data[stages[1]]['cases'])
assert len(data[stages[2]]['cases'])==1 and data[stages[2]]['cases'][0].attrib['outcome']=='Passed'
finals=[(stage,f) for stage,d in data.items() for f in d['final']];modes={f['mode'] for stage,f in finals}
assert modes=={'hold-before-commit','notification-before-mark','notification-mark-rollback','ack-committed-response-lost'} and len(finals)==4
passed_processes=[]
for stage,f in finals:
 assert len(f['pids'])==len(set(f['pids']))==3 and f['gold']==23 and f['fragments']==7 and f['warriorSoul']==3 and f['mageSoul']==4
 assert f['ledgerRows']==4 and f['physicalItems']==1 and f['duplicateAckSameReceipt'] and f['successfulPlayerCasts']==f['completedEncounters']==0
 assert f['sourceConfig']==('season-v1-config-16' if f['mode']=='hold-before-commit' else 'season-v1-config-17')
 passed_processes.extend((stage,pid) for pid in f['pids'])
assert len(passed_processes)==len(set(passed_processes))==12 and len(all_starts)==len(all_stops)==14
def entries(stage,kind):return [r['evidence'] for r in data[stage]['rows'] if r['caseId']==kind]
uncommitted=entries(stages[1],'SEASON-ASSET-uncommitted-gate');assert len(uncommitted)==1 and uncommitted[0]['earlyAckStatus']==409 and uncommitted[0]['pending']==5 and uncommitted[0]['visibleWalletsUnchanged']
committed=entries(stages[1],'SEASON-ASSET-notification-drained');assert len(committed)==1 and committed[0]['publishedAfterDeadClientDrain'] is True
rolled=entries(stages[2],'SEASON-ASSET-notification-drained');assert len(rolled)==1 and rolled[0]['publishedAfterDeadClientDrain'] is False and rolled[0]['priorActualFrameObserved']
owned=entries(stages[2],'SEASON-ASSET-owned-notification-backends-stopped');assert len(owned)==1
o=owned[0];assert o['appAlreadyKilled'] and o['onlyUniqueOwnedGateAndApplicationNameMatched'] and o['ApplicationName'].startswith('fc-f02-notify-') and o['signaledBackends']
assert set(o['gateBackends'])<=set(o['ownedBackends']) and set(o['signaledBackends'])<=set(o['ownedBackends'])
initial=entries(stages[2],'SEASON-ASSET-notification-before-mark');redelivered=entries(stages[2],'SEASON-ASSET-ready-recovered')
assert len(initial)==len(redelivered)==1 and initial[0]['ready']['SettlementId']==redelivered[0]['delivered']['SettlementId']
ack=entries(stages[0],'SEASON-ASSET-ACK-lost-response');assert len(ack)==1 and len(ack[0]['attempts'])==2
assert ack[0]['attempts'][0]['Dropped'] and not ack[0]['attempts'][1]['Dropped'] and all(a['Forwarded'] and a['BackendStatus']==200 for a in ack[0]['attempts'])
assert ack[0]['attempts'][0]['ResponseSha256']==ack[0]['attempts'][1]['ResponseSha256']
pin=json.loads((base/'f02-season-asset-fault-build-r6/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
prior=json.loads((base/'f02-season-asset-fault-build-r2/source-pin.json').read_bytes());changed=[n for n in pin if pin[n]!=prior.get(n)]
assert changed==['server/tests/FantasyCard.Server.Tests/EndToEnd/ProcessLifecycleSeasonAssetFaultTests.cs']
legacy=repo/'docs/season-balance-20261102/evidence/A03-A04-final-r1';manifest=json.loads((legacy/'manifest.json').read_bytes())['files']
assert all((legacy/n).is_file() and hashlib.sha256((legacy/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
union={};retained_failures=0
for name in ['runtime-r115/public/results/group-a.trx','runtime-r115/public/results/group-b.trx','runtime-r115/public/results/group-c.trx','runtime-r116/public/results/group-a.trx']:
 for c in ET.parse(legacy/name).findall('.//t:UnitTestResult',ns):
  retained_failures+=c.attrib['outcome']!='Passed';union[c.attrib['testName']]=c.attrib['outcome']
assert len(union)==121 and all(v=='Passed' for v in union.values()) and retained_failures==5
assert all(r['guard_ok'] for r in resources)
assert min(r['available_ram'] for r in resources)>=500*1024**2 and min(r['free_disk'] for r in resources)>=3*1024**3 and min(r['disk_fraction'] for r in resources)>=.05
d=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(b['source']).read_bytes()).hexdigest()==b['sha256'] for b in d['D03_latest_banks'])
proof=dict(fault_scenarios_union_passed=4,pass_selection={'r1':['ack-committed-response-lost'],'r2':['hold-before-commit','notification-before-mark'],'r3_retry1':['notification-mark-rollback']},one_fresh_four_case_green_batch=False,raw_prior_two_deadlock_failures_retained=True,successful_path_process_identities=12,all_process_identities_including_failures=14,PG_backend_signals=len(o['signaledBackends']),only_owned_unique_application_and_gate_sessions_signaled=True,autocommit_notification_both_outcomes_actually_observed=True,same_receipt_actual_redelivery_after_marker_rollback=True,explicit_mixed_asset_transaction_rolled_back=True,committed_ACK_response_loss_then_restart_replay_same_bytes=True,schemas_removed=6,containers_env_tmpfs_cleaned=3,prior_A03_manifest_files_verified=len(manifest),prior_PG_unique_passed_rederived=121,prior_PG_failures_not_overwritten=retained_failures,prior_ACK_reuse_limit='Old passing ACK assertions and unchanged production bytes reused. Current extra outbox-wait statement is not claimed to have run in that old ACK case.',production_sources_unchanged=True,current_test_source_pinned=True,capital_banks_unchanged=True,min_cloud_RAM=min(r['available_ram'] for r in resources),min_cloud_disk=min(r['free_disk'] for r in resources),min_cloud_disk_fraction=min(r['disk_fraction'] for r in resources),new_completed_gameplay_encounters=0,new_B05_encounters=0,new_D03_encounters=0,production_modified=False,F02_composite_status='Pending final requirement mapping, not set by this fault-only audit',whole_goal_complete=False)
p=base/'f02-season-asset-fault-final-independent-r3.derived.json';assert not p.exists();p.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
