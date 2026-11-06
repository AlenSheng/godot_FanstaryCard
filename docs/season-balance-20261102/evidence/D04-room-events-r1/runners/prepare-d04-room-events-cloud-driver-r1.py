from pathlib import Path
base=Path(__file__).parent
text=(base/'prepare-d04-lifecycle-cloud-r1.py').read_text(encoding='utf-8').replace('d04-lifecycle','d04-room-events').replace('d04-room-events-build-r2','d04-room-events-server-r2')
old=['FantasyCard.Server.Tests.Persistence.PostgresLifecycleEventTelemetryTests.ActualDiscardAndEnhancementConsumptionAreOnceOnlyWithLobbyDifficultyUnknownAndUnclassifiedHistoryVisible','FantasyCard.Server.Tests.Persistence.PostgresLifecycleEventTelemetryTests.ActualPagedArchiveHasOriginalSeasonAndIdentityAndNeverCountsAlreadyConsumedItemsAsDestroyedAgain','FantasyCard.Server.Tests.Persistence.PostgresLifecycleEventTelemetryTests.OriginalDifficultyReceiptHasRunSummaryHeroAndHumanKindWhileDeathAndReplayDoNotInventAnotherClear','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary']
new=['FantasyCard.Server.Tests.Persistence.PostgresRoomEventTelemetryTests.NewestCheckpointPreservesCumulativeEventsAndRestartContinuesOriginalIdsWithoutChangingAssetsOnQuery','FantasyCard.Server.Tests.Persistence.PostgresRoomEventTelemetryTests.OldMissingAndCorruptObservationsRemainExplicitGapsAndReadQueriesDoNotRepairThem','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts']
needle='new='+repr(old)
# The source list is compact; replace its complete line without altering old template matching.
lines=text.splitlines();matches=[i for i,line in enumerate(lines) if line.startswith('new=')];assert len(matches)==1
lines[matches[0]]='new='+repr(new);text='\n'.join(lines)+'\n'
# Four 32KiB SFTP requests bound the transport window to128KiB. Full-file
# length/SHA validation remains mandatory before the unchanged worker launch.
needle="path=base/'run-d04-room-events-file-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')"
assert text.count(needle)==1
text=text.replace(needle,"source=source.replace(\"'-R','1','-B','8192'\",\"'-R','4','-B','32768'\")\n"+needle)
target=base/'prepare-d04-room-events-cloud-r1.py';assert not target.exists();compile(text,str(target),'exec');target.write_text(text,encoding='utf-8')
print('Prepared four scoped cloud scenarios, bounded128KiB transport window; not launched.')
