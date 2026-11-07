from pathlib import Path
base=Path(__file__).parent
text=(base/'prepare-d04-crafting-cloud-r1.py').read_text(encoding='utf-8').replace('d04-crafting','d04-lifecycle').replace('d04-lifecycle-build-r1','d04-lifecycle-build-r2')
old=['DurablePityFactsSurviveReplayAndLaterWishChangesWhileHistoricalMissingFactsStayUnknown','KnownRecipeDoesNotEmitAnotherLearningAndReforgeObservesOneRetainedBodyInsteadOfMintOrDestruction','ObservationInsertFailureRollsBackPaymentItemWishAndActionAndOriginalKeyCanRetryOnce']
new=['ActualDiscardAndEnhancementConsumptionAreOnceOnlyWithLobbyDifficultyUnknownAndUnclassifiedHistoryVisible','ActualPagedArchiveHasOriginalSeasonAndIdentityAndNeverCountsAlreadyConsumedItemsAsDestroyedAgain','OriginalDifficultyReceiptHasRunSummaryHeroAndHumanKindWhileDeathAndReplayDoNotInventAnotherClear']
for a,b in zip(old,new):
    needle='PostgresCraftingEventTelemetryTests.'+a
    assert text.count(needle)==1
    text=text.replace(needle,'PostgresLifecycleEventTelemetryTests.'+b)
target=base/'prepare-d04-lifecycle-cloud-r1.py';assert not target.exists();compile(text,str(target),'exec');target.write_text(text,encoding='utf-8')
print('Prepared isolated lifecycle4case driver; no execution.')
