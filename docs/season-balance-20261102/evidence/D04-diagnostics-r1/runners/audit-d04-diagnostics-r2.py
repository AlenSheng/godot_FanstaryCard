from pathlib import Path
import json,hashlib,tarfile,xml.etree.ElementTree as ET
base=Path(__file__).parent;repo=Path.cwd();ns={'t':'http://microsoft.com/schemas/VisualStudio/TeamTest/2010'}
for stage,name,count in [('d04-diagnostics-domain-r1','domain',36),('d04-diagnostics-server-r2','server',12)]:
 result=json.loads((base/stage/'result.json').read_bytes());assert result['exit']==0 and result['source_unchanged']
 rows=ET.parse(base/stage/'results'/f'{name}.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==count and all(r.attrib['outcome']=='Passed' for r in rows)
pin=json.loads((base/'d04-diagnostics-server-r2/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in pin.items())
old=base/'d04-diagnostics-cloud-r1-file';failed=json.loads((old/'result.json').read_bytes());assert failed['exit']==1 and failed['guard_ok'] and failed['schemas_still_present']==[]
assert hashlib.sha256((old/'public-evidence.tar.gz').read_bytes()).hexdigest()==failed['collected_raw_archive_sha256']
failedRows=ET.parse(old/'public/cases.trx').findall('.//t:UnitTestResult',ns);assert len(failedRows)==5 and all(r.attrib['outcome']=='Failed' for r in failedRows)
domainpin=json.loads((base/'d04-diagnostics-domain-r1/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==sha for n,sha in domainpin.items() if n.startswith(('server/src/FantasyCard.Domain/','server/tests/FantasyCard.Domain.Tests/')))
folder=base/'d04-diagnostics-cloud-r2-file';public=folder/'public';result=json.loads((folder/'result.json').read_bytes())
assert result['exit']==0 and result['guard_ok'] and result['input_unchanged'] and result['local_binary_inputs_unchanged'] and result['schemas_still_present']==[]
assert hashlib.sha256((folder/'public-evidence.tar.gz').read_bytes()).hexdigest()==result['collected_raw_archive_sha256']
with tarfile.open(folder/'public-evidence.tar.gz') as bundle:
 for member in bundle.getmembers():assert bundle.extractfile(member).read()==(public/member.name).read_bytes()
rows=ET.parse(public/'cases.trx').findall('.//t:UnitTestResult',ns);assert len(rows)==5 and all(r.attrib['outcome']=='Passed' for r in rows)
proofs={r['kind']:r for line in (public/'currency-reports.original.jsonl').read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))}
def one(report,kind):
 rows=[r for r in report['Rows'] if r['Kind']==kind];assert len(rows)==1;return rows[0]
market=proofs['actual-diagnostic-market'];cohort=one(market['report'],'Listing48HourCohort')['Measures'];assert [cohort[k] for k in ['listings','matureFull48Hours','matureSoldWithin48','rightCensoredOrShortened','youngSoldWithin48','seasonShortened']]==['5','2','1','3','1','1']
trade=one(market['report'],'EquipmentMaterialTrades');assert trade['Dimensions']['level']=='0' and trade['Dimensions']['recipeExtracted']=='false' and trade['Measures']['priceSum']=='200'
activity=proofs['actual-diagnostic-activity-shop'];spend=one(activity['report'],'ShopSpendAndActivityOverlap')['Measures'];assert spend['goldSpent']=='240' and spend['units']=='2' and spend['postPurchaseBalanceBelow100']=='1'
issue=one(activity['report'],'ActivityBudgetAndPeak');assert issue['Dimensions']['rewardKind']=='bound_fragments' and issue['Measures']['actualRewardAmount']=='10'
run=one(activity['report'],'RunCohorts');assert run['Dimensions']['cohort']=='AccountAgeAtMost7Days' and run['Dimensions']['class']=='Mage' and run['Measures']['extracted']=='1'
extract=proofs['actual-diagnostic-extraction'];assert one(extract['report'],'FirstCommittedEquipmentExtraction')['Measures']['firstCommittedExtractions']=='1' and one(extract['report'],'DeathEquipmentRecovery')['Measures']['sameActorRecovery']=='1'
red=proofs['actual-diagnostic-red-mint-custody'];assert one(red['diagnostics'],'RedQuotaAndAttempts')['Measures']['matchingMint']=='1' and one(red['diagnostics'],'RedMintAttempts')['Dimensions']['status']=='Minted'
for r in [market,activity,extract,red]:assert r['readOnlyFingerprintUnchanged']
api=proofs['actual-diagnostics-admin-HTTP'];assert api['missingKeyStatus']==401 and api['insecureStatus']==403 and api['privateNoStore']
receipts=[json.loads(line) for line in (public/'process-logs/receipts.jsonl').read_text().splitlines()];starts=[r['evidence']['Id'] for r in receipts if r['caseId']=='process-start'];stops=[r['evidence']['ProcessId'] for r in receipts if r['caseId']=='process-stop'];assert len(starts)==1 and set(starts)==set(stops)
assert len(result['owned_schemas'])==5 and not result['schemas_still_present']
assert all(json.loads((public/'cleanup.original.json').read_bytes())[k] for k in ['owned_container_removed','private_env_removed'])
assert json.loads((public/'input-cache-cleanup.original.json').read_bytes())['tmpfs_unmounted'] and json.loads((folder/'upload-cleanup.original.json').read_bytes())['upload_tmpfs_unmounted']
assert all(json.loads(line)['guard_ok'] for line in (public/'resources.original.jsonl').read_text().splitlines())
cache=json.loads((public/'dependency-cache-reuse.original.json').read_bytes());assert cache['all_reused_hashes_verified'] and not cache['task_assemblies_reused'] and cache['reused_files']==122
context=json.loads((base/'current-journey-client-continuation-20261105.json').read_bytes());assert all(hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['sha256'] for r in context['D03_latest_banks'])
proof=dict(diagnostics_subchain_verified=True,original_failed_PG_cases=5,PG_case_executions=10,original_SQL42601_retained=True,first_red_schema_identity_not_recorded_gap_retained=True,domain_passed=36,server_passed=12,actual_PG_HTTP_passed=5,source_unchanged=True,capital_banks_unchanged=True,
 actual_program_processes=1,transient_resources_cleaned=True,thirdparty_cache_reused_files=122,task_assemblies_fresh=True,read_only_fingerprints_unchanged=True,
 mature_listing_conversion_numerator=1,mature_listing_conversion_denominator=2,young_sold_not_added_to_mature_numerator=True,season_shortened_exposure_separate=True,
 immutable_trade_template_not_current_item=True,actual_shop_total_not_quantity_squared=True,activity_shared_budget_and_actual_reward_branch=True,
 exact_committed_hold_item_player_realm=True,unknown_history_not_backfilled=True,legal_over_base_hp_separate=True,
 age_and_prior_season_cohorts_not_skill=True,shop_activity_overlap_not_causal=True,unrecovered_death_right_censored=True,
 red_original_mint_quota_custody_verified=True,new_B05_campaign_cases=0,existing_red_fault_flow_performs_player_casts=True,
 D04_complete=False,remaining_D04=['current-version integrated telemetry requirement audit'],progress='30/35',whole_goal_complete=False,production_modified=False,raw_archive_sha256=result['collected_raw_archive_sha256'])
path=base/'d04-diagnostics-independent-audit-r2.derived.json';assert not path.exists();path.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
