from pathlib import Path
import hashlib,json,io,tarfile
base=Path(__file__).parent;repo=Path.cwd();out=base/'d04-crafting-cloud-input-r1';assert not out.exists()
assert json.loads((base/'d04-crafting-build-r1/result.json').read_bytes())['exit']==0
out.mkdir();binary=base/'d04-crafting-build-r1/build/bin/FantasyCard.Server.Tests/debug';files={};expanded=0
with tarfile.open(out/'payload.tar.gz','w:gz') as bundle:
    for path in sorted(binary.rglob('*')):
        if not path.is_file():continue
        data=path.read_bytes();name='bin/'+path.relative_to(binary).as_posix();files[name]=hashlib.sha256(data).hexdigest();expanded+=len(data)
        info=tarfile.TarInfo(name);info.size=len(data);bundle.addfile(info,io.BytesIO(data))
    path=repo/'server/src/FantasyCard.Server/FantasyCard.Server.csproj';data=path.read_bytes();name=path.relative_to(repo).as_posix();files[name]=hashlib.sha256(data).hexdigest();expanded+=len(data)
    info=tarfile.TarInfo(name);info.size=len(data);bundle.addfile(info,io.BytesIO(data))
data=(out/'payload.tar.gz').read_bytes();manifest=dict(payload_sha256=hashlib.sha256(data).hexdigest(),payload_bytes=len(data),expanded_bytes=expanded,files=files)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
source=(base/'start-d04-playtime-cloud-r1.py').read_text(encoding='utf-8').replace('d04-playtime-r1','d04-crafting-r1')
old=['FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.PersistedTerminalClocksDriveNetHourlyPercentilesIncludingDeathsZeroAndUnlocatedFinancialRows','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts']
new=['FantasyCard.Server.Tests.Persistence.PostgresCraftingEventTelemetryTests.DurablePityFactsSurviveReplayAndLaterWishChangesWhileHistoricalMissingFactsStayUnknown','FantasyCard.Server.Tests.Persistence.PostgresCraftingEventTelemetryTests.KnownRecipeDoesNotEmitAnotherLearningAndReforgeObservesOneRetainedBodyInsteadOfMintOrDestruction','FantasyCard.Server.Tests.Persistence.PostgresCraftingEventTelemetryTests.ObservationInsertFailureRollsBackPaymentItemWishAndActionAndOriginalKeyCanRetryOnce','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary']
needle=','.join("'-method',"+repr(x) for x in old);assert source.count(needle)==1
source=source.replace(needle,','.join("'-method',"+repr(x) for x in new)).replace('planned_report_cases=3','planned_report_cases=4')
path=base/'start-d04-crafting-cloud-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
source=(base/'run-d04-playtime-file-r1.py').read_text(encoding='utf-8').replace('d04-playtime-r1','d04-crafting-r1').replace('d04-playtime-cloud-r1','d04-crafting-cloud-r1').replace('d04-playtime-cloud-input-r1','d04-crafting-cloud-input-r1').replace('d04-playtime-server-r5','d04-crafting-build-r1').replace('fc-d04-playtime-upload','fc-d04-crafting-upload')
path=base/'run-d04-crafting-file-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
print(json.dumps(dict(prepared_cases=4,payload_bytes=len(data),expanded_bytes=expanded,remote_execution=False)))
