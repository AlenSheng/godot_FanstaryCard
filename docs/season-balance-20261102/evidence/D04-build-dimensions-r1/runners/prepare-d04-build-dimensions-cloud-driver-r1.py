from pathlib import Path
base=Path(__file__).parent
source=(base/'prepare-d04-room-events-cloud-r1.py').read_text(encoding='utf-8').replace('d04-room-events','d04-build-dimensions').replace('d04-build-dimensions-server-r2','d04-build-dimensions-server-r1')
methods=['FantasyCard.Server.Tests.Persistence.PostgresBuildDimensionTelemetryTests.OriginalEventAndZeroAssetDifficultyReceiptKeepFrozenBuildDimensionsWhileOldReceiptReplayDoesNotBackfill','FantasyCard.Server.Tests.Persistence.PostgresBuildDimensionTelemetryTests.MissingOriginalEventReferencesStayUnknownEvenWithAProfileAndPlayerSnapshotAvailable','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts']
lines=source.splitlines();at=[i for i,line in enumerate(lines) if line.startswith('new=')];assert len(at)==1;lines[at[0]]='new='+repr(methods)
source='\n'.join(lines)+'\n';target=base/'prepare-d04-build-dimensions-cloud-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
print('Prepared four scoped build-dimension PG/HTTP/realOS scenarios; no execution.')
