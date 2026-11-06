from pathlib import Path
import hashlib,json,io,tarfile
base=Path(__file__).parent;repo=Path.cwd();out=base/'d04-playtime-cloud-input-r1';assert not out.exists();out.mkdir()
binary=base/'d04-playtime-server-r5/build/bin/FantasyCard.Server.Tests/debug';assert json.loads((base/'d04-playtime-server-r5/result.json').read_bytes())['exit']==0
files={};expanded=0
with tarfile.open(out/'payload.tar.gz','w:gz') as bundle:
 for p in sorted(binary.rglob('*')):
  if not p.is_file():continue
  raw=p.read_bytes();name='bin/'+p.relative_to(binary).as_posix();files[name]=hashlib.sha256(raw).hexdigest();expanded+=len(raw);info=tarfile.TarInfo(name);info.size=len(raw);bundle.addfile(info,io.BytesIO(raw))
 for name in ['server/src/FantasyCard.Server/FantasyCard.Server.csproj']+['server/config/archive/season-v1-config-16/fantasycard.config.'+suffix for suffix in ['bytes','sha256','version.txt']]:
  raw=(repo/name).read_bytes();files[name]=hashlib.sha256(raw).hexdigest();expanded+=len(raw);info=tarfile.TarInfo(name);info.size=len(raw);bundle.addfile(info,io.BytesIO(raw))
payload=(out/'payload.tar.gz').read_bytes();manifest=dict(payload_sha256=hashlib.sha256(payload).hexdigest(),payload_bytes=len(payload),expanded_bytes=expanded,files=files)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
s=(base/'start-d04-currency-cloud-r1.py').read_text(encoding='utf-8').replace('d04-currency-r1','d04-playtime-r1').replace('fc-d04-currency-cloud-r1','fc-d04-playtime-cloud-r1')
old=['FantasyCard.Server.Tests.Persistence.PostgresSeasonMarketTests.ActualMarketReportSeparatesTransferAndTaxWithoutDoubleCountingOrMutation','FantasyCard.Server.Tests.Persistence.PostgresEconomyTelemetryTests.ActualReserveRefundAndAppliedReplayHaveDistinctImmutableObservationTimesAndSupplyEffects','FantasyCard.Server.Tests.Persistence.PostgresEconomyTelemetryTests.HistoricalAppliedTimeIsNotInventedOnReplayAndUnknownCurrenciesRemainVisible','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary']
new=['FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.PersistedTerminalClocksDriveNetHourlyPercentilesIncludingDeathsZeroAndUnlocatedFinancialRows','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts']
needle=','.join("'-method',"+repr(x) for x in old);assert s.count(needle)==1;s=s.replace(needle,','.join("'-method',"+repr(x) for x in new)).replace('planned_report_cases=5','planned_report_cases=3')
needle="p=public/'owned-schemas.original.jsonl'; schemas=[json.loads(line)['schema'] for line in p.read_text().splitlines()] if p.exists() else []";assert s.count(needle)==1
s=s.replace(needle,needle+"\n    q=public/'process-logs/receipts.jsonl'; schemas+=([row['evidence']['schema'] for line in q.read_text().splitlines() if (row:=json.loads(line))['caseId']=='SEASON17-schema'] if q.exists() else []);schemas=sorted(set(schemas))")
p=base/'start-d04-playtime-cloud-r1.py';assert not p.exists();compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
s=(base/'run-d04-currency-file-r3.py').read_text(encoding='utf-8').replace("out=base/'d04-currency-cloud-r3-file'","out=base/'d04-playtime-cloud-r1-file'").replace("source=base/'d04-currency-cloud-r2'","source=base/'d04-playtime-cloud-input-r1'")
s=s.replace("base/'start-d04-currency-cloud-r2.py'","base/'start-d04-playtime-cloud-r1.py'")
s=s.replace(".replace('d04-currency-r2','d04-currency-r3').replace('fc-d04-currency-cloud-r2','fc-d04-currency-cloud-r3')",'')
s=s.replace('season-balance-20261106-d04-currency-r3','season-balance-20261106-d04-playtime-r1').replace('fc-d04-currency-upload','fc-d04-playtime-upload').replace("base/'d04-currency-build-r4/build/bin/FantasyCard.Server.Tests/debug'","base/'d04-playtime-server-r5/build/bin/FantasyCard.Server.Tests/debug'")
p=base/'run-d04-playtime-file-r1.py';assert not p.exists();compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print(json.dumps(dict(prepared_cases=3,payload_bytes=len(payload),expanded_bytes=expanded,source_build='d04-playtime-server-r5',no_remote_execution_yet=True)))
