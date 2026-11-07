from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
native=base/'d04-currency-native-r2';nresult=json.loads((native/'result.json').read_bytes());assert nresult['exit']==0 and nresult['source_unchanged']
ntests=ET.parse(native/'results/contracts.trx').findall('.//t:UnitTestResult',ns);assert len(ntests)==15 and all(t.attrib['outcome']=='Passed' for t in ntests)
stages=['d04-currency-cloud-r1','d04-currency-cloud-r3-file'];union={};proofs=[];resources=[]
for stage in stages:
 folder=base/stage;result=json.loads((folder/'result.json').read_bytes());public=folder/'public'
 assert result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
 if stage==stages[1]:assert result['exit']==0 and result['input_received_from_verified_SFTP_file']
 assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
 with tarfile.open(folder/'public-evidence.tar.gz') as archive:
  for member in archive.getmembers():assert archive.extractfile(member).read()==(public/member.name).read_bytes()
 tests=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns)
 if stage==stages[0]:assert len(tests)==5 and sum(t.attrib['outcome']=='Passed' for t in tests)==4
 else:assert len(tests)==1 and tests[0].attrib['outcome']=='Passed'
 for t in tests:union[t.attrib['testName']]=t.attrib['outcome']
 proofs.extend(json.loads(s) for s in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines())
 resources.extend(json.loads(s) for s in (public/'resources.original.jsonl').read_text().splitlines())
 for name in ['cleanup.original.json','input-cache-cleanup.original.json']:
  c=json.loads((public/name).read_bytes());assert all(c[k] for k in (['owned_container_removed','private_env_removed'] if name=='cleanup.original.json' else ['tmpfs_unmounted','input_files_removed']))
assert len(union)==5 and all(v=='Passed' for v in union.values())
markets=[p for p in proofs if p['kind']=='actual-market-report'];assert len(markets)==2
for p in markets:
 total=next(t for t in p['report']['Totals'] if t['Currency']==p['currency']);assert total['SystemMint']=='0' and int(total['SystemBurn'])==p['fee'] and int(total['Transfer'])==p['price']-p['fee']
 assert int(total['LedgerDelta'])==-p['fee'] and total['ReconciliationDifference']=='0' and p['report']['RecognizedCurrencyCoverageComplete'] and p['report']['UnmatchedMarketTransactions']==0
 assert p['readOnlyFingerprintUnchanged'] and p['queryReplayDoesNotMint']
gold=next(p for p in markets if p['currency']=='Gold');assert gold['price']==gold['fee']==1
old=next(p for p in proofs if p['kind']=='historical-gaps-retained');assert old['noHistoricalBackfill'] and old['readOnlyFingerprintUnchanged'] and old['report']['AppliedRefreshesWithoutOriginalTime']==1 and not old['report']['RecognizedCurrencyCoverageComplete']
ambiguous=next(t for t in old['report']['Totals'] if t['Currency']=='ClassSoul');assert ambiguous['SystemMint']=='0' and ambiguous['UnclassifiedMagnitude']=='4'
applied=next(p for p in proofs if p['kind']=='immutable-applied-time');assert applied['emptyReplayWindow'] and applied['readOnlyFingerprintUnchanged']
a=applied['applied']['Totals'][0];r=applied['refunded']['Totals'][0]
assert a['SystemBurn']==a['EscrowReserved']==a['EscrowConsumed']=='7' and a['LedgerDelta']=='-7' and a['ReconciliationDifference']=='0'
assert r['SystemMint']==r['SystemBurn']==r['LedgerDelta']=='0' and r['EscrowReserved']==r['EscrowReturned']=='5'
api=next(p for p in proofs if p['kind']=='actual-admin-HTTP');assert api['loopbackJSON'] and not api['realTLSHandshakeClaimed'] and api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['privateNoStore']
assert all(not p['report']['PerAttemptPlaytimeRatesAvailable'] for p in markets) and not api['report']['perAttemptPlaytimeRatesAvailable']
log=next((base/stages[0]/'public/process-logs').glob('d04-admin-report-*.log')).read_text(encoding='utf-8');assert any('"Version":53' in s for s in log.splitlines())
pin=json.loads((base/'d04-currency-build-r4/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
prior=json.loads((base/'d04-currency-build-r3/source-pin.json').read_bytes());assert [n for n in pin if pin[n]!=prior.get(n)]==['server/tests/FantasyCard.Server.Tests/Persistence/PostgresEconomyTelemetryTests.cs']
unitpin=json.loads((native/'source-pin.json').read_bytes());assert all(pin.get(n)==h for n,h in unitpin.items() if n.startswith('server/src/') or n.endswith('/EconomyFlowTests.cs'))
assert all(r['guard_ok'] for r in resources) and min(r['available_ram'] for r in resources)>=500*1024**2 and min(r['free_disk'] for r in resources)>=3*1024**3 and min(r['disk_fraction'] for r in resources)>=.05
upload=json.loads((base/stages[1]/'upload-cleanup.original.json').read_bytes());assert upload['upload_tmpfs_unmounted']
stopped=json.loads((base/'d04-currency-r2-owned-transfer-stop-r1/result.original.json').read_bytes())['proof'];assert stopped['remote_runtime_never_started'] and stopped['exact_launcher_argument_SHA256'] and not stopped['other_projects_modified']
d=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(b['source']).read_bytes()).hexdigest()==b['sha256'] for b in d['D03_latest_banks'])
result=dict(currency_projection_subchain_verified=True,native_unique_passed=15,PG_and_actualHTTP_unique_passed=5,PG_union_not_one_fresh_all_green_batch=True,first_runtime_passed=4,first_runtime_fixture_failed=1,targeted_retest_passed=1,actual_market_transactions=2,minimum_tax_zero_seller_net_verified=True,only_tax_changes_currency_supply=True,first_applied_time_immutable_across_replay=True,old_applied_time_not_invented=True,read_only_repeatable_read_reports_verified=True,large_integer_amounts_are_exact_strings=True,operational_meter_only_bounded_outcome_label=True,admin_existing_auth_private_no_store_boundary_verified=True,real_public_TLS_claimed=False,migration_53_fresh_runtime_verified=True,F02_affected_observation_metadata_scope_revalidated=True,original_runtime_schemas_cleaned=5,retest_schema_cleaned=1,actual_test_containers_env_and_input_tmpfs_cleaned=2,stale_input_worker_only_SIGINTed_by_exact_digest=True,stale_input_attempt_started_tests=False,verified_file_transfer_upload_tmpfs_cleaned=True,min_cloud_RAM=min(r['available_ram'] for r in resources),min_cloud_disk=min(r['free_disk'] for r in resources),min_cloud_disk_fraction=min(r['disk_fraction'] for r in resources),source_unchanged=True,capital_banks_unchanged=True,new_B05_D03_D02_encounters=0,D04_complete=False,remaining_D04=['11event named projections','physical items/escrow/destruction/archive','actual per-attempt playtime and P10/P50/P90','combat draw/control/overflow observations','cohort and market depth/48h/zero-balance/activity diagnostics'],progress='30/35',whole_goal_complete=False,production_modified=False)
p=base/'d04-currency-independent-audit-r1.derived.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
