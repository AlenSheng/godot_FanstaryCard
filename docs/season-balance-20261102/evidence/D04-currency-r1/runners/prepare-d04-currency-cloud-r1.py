from pathlib import Path
base=Path(__file__).parent
p=base/'start-d04-currency-cloud-r1.py';assert not p.exists()
s=(base/'start-f02-season-asset-fault-cloud-r2.py').read_text(encoding='utf-8').replace('f02-season-asset-fault-r2','d04-currency-r1').replace('fc-f02-season-asset-fault-cloud-r2','fc-d04-currency-cloud-r1')
s=s.replace('FANTASYCARD_F02_ASSET_MODES=hold-before-commit,notification-before-mark\\n','FANTASYCARD_D04_SCHEMA_EVIDENCE=/results/owned-schemas.original.jsonl\\nFANTASYCARD_D04_REPORT_EVIDENCE=/results/currency-reports.original.jsonl\\n')
needle="'-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_season_asset_fault_boundaries_preserve_domains_and_once_only_receipts'";assert s.count(needle)==1
methods=['FantasyCard.Server.Tests.Persistence.PostgresSeasonMarketTests.ActualMarketReportSeparatesTransferAndTaxWithoutDoubleCountingOrMutation','FantasyCard.Server.Tests.Persistence.PostgresEconomyTelemetryTests.ActualReserveRefundAndAppliedReplayHaveDistinctImmutableObservationTimesAndSupplyEffects','FantasyCard.Server.Tests.Persistence.PostgresEconomyTelemetryTests.HistoricalAppliedTimeIsNotInventedOnReplayAndUnknownCurrenciesRemainVisible','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary']
s=s.replace(needle,','.join("'-method',"+repr(m) for m in methods))
old="p=public/'process-logs/receipts.jsonl'; schemas=[row['evidence']['schema'] for line in p.read_text().splitlines() if (row:=json.loads(line))['caseId']=='SEASON-ASSET-schema'] if p.exists() else []";assert old in s
s=s.replace(old,"p=public/'owned-schemas.original.jsonl'; schemas=[json.loads(line)['schema'] for line in p.read_text().splitlines()] if p.exists() else []")
s=s.replace('declared_settlement_fixture_rows=2,selected_test_modes=["hold-before-commit","notification-before-mark"]','planned_report_cases=5')
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
p=base/'run-d04-currency-cloud-r1.py';assert not p.exists()
s=(base/'run-f02-season-asset-fault-cloud-r2.py').read_text(encoding='utf-8').replace('f02-season-asset-fault-cloud-r2','d04-currency-cloud-r1').replace('f02-season-asset-fault-r2','d04-currency-r1').replace('f02-season-asset-fault-build-r3','d04-currency-build-r3')
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Prepared5new currency projection cases only; original guarded private PG/runtime reused, SDKnotstarted remotely, input128MiBtmpfs.')
