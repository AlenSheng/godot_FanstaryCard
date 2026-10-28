using System.Diagnostics.Metrics;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Tests.Common;

public sealed class ServerMetricsTests
{
    [Fact]
    public void Core_operational_measurements_are_published()
    {
        var measurements = new Dictionary<string, List<long>>(StringComparer.Ordinal);
        var doubleMeasurements = new Dictionary<string, List<double>>(StringComparer.Ordinal);
        using var metrics = new ServerMetrics();
        using var listener = new MeterListener();
        listener.InstrumentPublished = (instrument, currentListener) =>
        {
            if (ReferenceEquals(instrument.Meter, metrics.SourceMeter))
                currentListener.EnableMeasurementEvents(instrument);
        };
        listener.SetMeasurementEventCallback<long>((instrument, measurement, _, _) =>
        {
            if (!measurements.TryGetValue(instrument.Name, out var values))
                measurements[instrument.Name] = values = [];
            values.Add(measurement);
        });
        listener.SetMeasurementEventCallback<double>((instrument, measurement, _, _) =>
        {
            if (!doubleMeasurements.TryGetValue(instrument.Name, out var values))
                doubleMeasurements[instrument.Name] = values = [];
            values.Add(measurement);
        });
        listener.Start();

        metrics.RealtimeConnectionOpened();
        metrics.RealtimeConnectionClosed();
        metrics.RealtimeMessageReceived();
        metrics.ObserveRealtimeMessageBytes(512);
        metrics.RealtimeResumed();
        metrics.RealtimeCommandRejected("INVALID_PAYLOAD");
        metrics.RealtimeCommandRateLimited();
        metrics.RealtimeStreamsExpired(2);
        metrics.RoomSnapshotFailed();
        metrics.SettlementFailed();
        metrics.SettlementHoldsCommitted(3);
        metrics.ObserveSettlementPendingHolds(4);
        metrics.EconomyReconciliationViolated(5);
        metrics.ExpiredDataDeleted(6, 7, 8, 9, 10);
        metrics.IdentitySignInSucceeded("steam");
        metrics.IdentitySignInFailed("steam", "invalid_ticket");
        metrics.IdentityTokenRejected();
        metrics.IdentityTokenExpired();
        metrics.ObserveMatchmakingQueueDuration(TimeSpan.FromSeconds(11.5));
        metrics.ObserveMatchLaunchPhase("register", TimeSpan.FromMilliseconds(12.5));
        metrics.MatchLaunchFailed("register");
        metrics.RoomOpened(4);
        metrics.RoomClosed();
        metrics.ObserveRoomActorQueueLength(3);
        metrics.ObserveRoomActorCommandWait("GetCombatInfoCommand", TimeSpan.FromMilliseconds(9.5));
        metrics.ObserveRoomActorTickDelay(TimeSpan.FromMilliseconds(12.5));
        metrics.ObserveRealtimeCommandDuration("battle.play_cards", TimeSpan.FromMilliseconds(18.5));
        metrics.ObserveRoomSnapshotDuration(TimeSpan.FromMilliseconds(7.5));
        metrics.ObservePveDuration(TimeSpan.FromSeconds(30), "cleared");
        metrics.ObservePvpDuration(TimeSpan.FromSeconds(8), "survived");
        metrics.PveEndedAbnormally("room_closed");
        metrics.PvpEndedAbnormally("room_closed");
        metrics.DatabaseMigrationAttemptFailed();
        metrics.DatabaseMigrationApplied();
        metrics.ObserveDatabaseSchemaVersion(7);
        metrics.DatabaseMigrationFinished(TimeSpan.FromSeconds(1.25), succeeded: true);
        metrics.SettlementCreated();
        metrics.SettlementIdempotencyHit();

        Assert.Equal([1, -1], measurements["fantasycard.realtime.connections.active"]);
        Assert.Equal([3], measurements["fantasycard.settlement.holds.committed"]);
        Assert.Equal([2], measurements["fantasycard.realtime.streams.expired"]);
        Assert.Equal([4], measurements["fantasycard.settlement.holds.pending"]);
        Assert.Equal([5], measurements["fantasycard.economy.reconciliation.violations"]);
        Assert.Equal([6], measurements["fantasycard.identity.sessions.expired_deleted"]);
        Assert.Equal([7], measurements["fantasycard.persistence.idempotency.expired_deleted"]);
        Assert.Equal([8], measurements["fantasycard.persistence.room_events.expired_deleted"]);
        Assert.Equal([9], measurements["fantasycard.matchmaking.preparations.expired"]);
        Assert.Equal([10], measurements["fantasycard.matchmaking.tickets.expired"]);
        Assert.Equal([512], measurements["fantasycard.realtime.message.size"]);
        Assert.Equal([1], measurements["fantasycard.realtime.resumes"]);
        Assert.Equal([1], measurements["fantasycard.realtime.commands.rejected"]);
        Assert.Equal([1], measurements["fantasycard.identity.signins.succeeded"]);
        Assert.Equal([1], measurements["fantasycard.identity.signins.failed"]);
        Assert.Equal([1], measurements["fantasycard.match_launch.failures"]);
        Assert.Equal([12.5], doubleMeasurements["fantasycard.match_launch.phase.duration"]);
        Assert.Equal([1], measurements["fantasycard.identity.tokens.rejected"]);
        Assert.Equal([1], measurements["fantasycard.identity.tokens.expired"]);
        Assert.Equal([11.5], doubleMeasurements["fantasycard.matchmaking.queue.duration"]);
        Assert.Equal([1, -1], measurements["fantasycard.rooms.active"]);
        Assert.Equal([4], measurements["fantasycard.rooms.players"]);
        Assert.Equal([3], measurements["fantasycard.room_actor.queue.length"]);
        Assert.Equal([9.5], doubleMeasurements["fantasycard.room_actor.command.wait"]);
        Assert.Equal([12.5], doubleMeasurements["fantasycard.room_actor.tick.delay"]);
        Assert.Equal([18.5], doubleMeasurements["fantasycard.realtime.command.duration"]);
        Assert.Equal([7.5], doubleMeasurements["fantasycard.room.snapshot.duration"]);
        Assert.Equal([30], doubleMeasurements["fantasycard.combat.pve.duration"]);
        Assert.Equal([8], doubleMeasurements["fantasycard.combat.pvp.duration"]);
        Assert.Equal([1], measurements["fantasycard.combat.pve.abnormal_ends"]);
        Assert.Equal([1], measurements["fantasycard.combat.pvp.abnormal_ends"]);
        Assert.Equal([1], measurements["fantasycard.database.migration.attempts_failed"]);
        Assert.Equal([1], measurements["fantasycard.database.migrations.applied"]);
        Assert.Equal([7], measurements["fantasycard.database.schema.version"]);
        Assert.Equal([1.25], doubleMeasurements["fantasycard.database.migration.duration"]);
        Assert.Equal([1], measurements["fantasycard.database.migration.runs"]);
        Assert.Equal([1], measurements["fantasycard.settlement.created"]);
        Assert.Equal([1], measurements["fantasycard.settlement.idempotency_hits"]);
    }
}
