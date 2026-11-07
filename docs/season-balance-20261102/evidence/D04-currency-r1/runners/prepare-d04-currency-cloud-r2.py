from pathlib import Path
base=Path(__file__).parent;p=base/'start-d04-currency-cloud-r2.py';assert not p.exists()
s=(base/'start-d04-currency-cloud-r1.py').read_text(encoding='utf-8').replace('d04-currency-r1','d04-currency-r2').replace('fc-d04-currency-cloud-r1','fc-d04-currency-cloud-r2')
methods=['FantasyCard.Server.Tests.Persistence.PostgresSeasonMarketTests.ActualMarketReportSeparatesTransferAndTaxWithoutDoubleCountingOrMutation','FantasyCard.Server.Tests.Persistence.PostgresEconomyTelemetryTests.ActualReserveRefundAndAppliedReplayHaveDistinctImmutableObservationTimesAndSupplyEffects','FantasyCard.Server.Tests.Persistence.PostgresEconomyTelemetryTests.HistoricalAppliedTimeIsNotInventedOnReplayAndUnknownCurrenciesRemainVisible','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary']
needle=','.join("'-method',"+repr(m) for m in methods);assert s.count(needle)==1
s=s.replace(needle,"'-method',"+repr(methods[1])).replace('planned_report_cases=5','planned_report_cases=1')
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
p=base/'run-d04-currency-cloud-r2.py';assert not p.exists()
s=(base/'run-d04-currency-cloud-r1.py').read_text(encoding='utf-8').replace('d04-currency-cloud-r1','d04-currency-cloud-r2').replace('d04-currency-r1','d04-currency-r2').replace('d04-currency-build-r3','d04-currency-build-r4')
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Only one failed timestamp fixture selected; four original runtime passes retained. No production changes since the first runtime batch.')
