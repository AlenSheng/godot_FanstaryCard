using System.Diagnostics.Metrics;

namespace FantasyCard.Server.Common;

public sealed class ServerMetrics : IDisposable
{
    public const string MeterName = "FantasyCard.Server";

    private readonly Meter _meter = new(MeterName);
    private readonly UpDownCounter<long> _activeRealtimeConnections;
    private readonly Counter<long> _realtimeMessages;
    private readonly Histogram<long> _realtimeMessageBytes;
    private readonly Counter<long> _realtimeResumes;
    private readonly Counter<long> _realtimeRejectedCommands;
    private readonly Counter<long> _realtimeRateLimitedCommands;
    private readonly Counter<long> _realtimeStreamsExpired;
    private readonly Counter<long> _roomSnapshotFailures;
    private readonly Counter<long> _settlementFailures;
    private readonly Counter<long> _settlementCommittedHolds;
    private readonly Histogram<long> _settlementPendingHolds;
    private readonly Counter<long> _economyReconciliationViolations;
    private readonly Counter<long> _expiredSessionsDeleted;
    private readonly Counter<long> _expiredIdempotencyRecordsDeleted;
    private readonly Counter<long> _expiredRoomEventsDeleted;
    private readonly Counter<long> _expiredPreparations;
    private readonly Counter<long> _expiredMatchTickets;
    private readonly Counter<long> _identitySignInSuccesses;
    private readonly Counter<long> _identitySignInFailures;
    private readonly Counter<long> _identityTokenRejections;
    private readonly Counter<long> _identityExpiredTokens;
    private readonly Histogram<double> _matchmakingQueueDuration;
    private readonly Histogram<double> _matchLaunchPhaseDuration;
    private readonly Counter<long> _matchLaunchFailures;
    private readonly UpDownCounter<long> _activeRooms;
    private readonly Histogram<long> _roomPlayerCount;
    private readonly UpDownCounter<long> _activeHumanRoomPlayers;
    private readonly Histogram<long> _roomActorQueueLength;
    private readonly Histogram<double> _roomActorCommandWait;
    private readonly Histogram<double> _roomActorTickDelay;
    private readonly Histogram<double> _realtimeCommandDuration;
    private readonly Histogram<double> _roomSnapshotDuration;
    private readonly Histogram<double> _pveDuration;
    private readonly Histogram<double> _pvpDuration;
    private readonly Counter<long> _pveAbnormalEnds;
    private readonly Counter<long> _pvpAbnormalEnds;
    private readonly Counter<long> _migrationAttemptsFailed;
    private readonly Counter<long> _migrationsApplied;
    private readonly Histogram<long> _databaseSchemaVersion;
    private readonly Histogram<double> _migrationDuration;
    private readonly Counter<long> _migrationRuns;
    private readonly Counter<long> _settlementsCreated;
    private readonly Counter<long> _settlementIdempotencyHits;

    internal Meter SourceMeter => _meter;

    public ServerMetrics()
    {
        _activeRealtimeConnections = _meter.CreateUpDownCounter<long>(
            "fantasycard.realtime.connections.active", unit: "{connection}");
        _realtimeMessages = _meter.CreateCounter<long>(
            "fantasycard.realtime.messages.received", unit: "{message}");
        _realtimeMessageBytes = _meter.CreateHistogram<long>(
            "fantasycard.realtime.message.size", unit: "By");
        _realtimeResumes = _meter.CreateCounter<long>(
            "fantasycard.realtime.resumes", unit: "{resume}");
        _realtimeRejectedCommands = _meter.CreateCounter<long>(
            "fantasycard.realtime.commands.rejected", unit: "{command}");
        _realtimeRateLimitedCommands = _meter.CreateCounter<long>(
            "fantasycard.realtime.commands.rate_limited", unit: "{command}");
        _realtimeStreamsExpired = _meter.CreateCounter<long>(
            "fantasycard.realtime.streams.expired", unit: "{stream}");
        _roomSnapshotFailures = _meter.CreateCounter<long>(
            "fantasycard.room.snapshot.failures", unit: "{failure}");
        _settlementFailures = _meter.CreateCounter<long>(
            "fantasycard.settlement.failures", unit: "{failure}");
        _settlementCommittedHolds = _meter.CreateCounter<long>(
            "fantasycard.settlement.holds.committed", unit: "{hold}");
        _settlementPendingHolds = _meter.CreateHistogram<long>(
            "fantasycard.settlement.holds.pending", unit: "{hold}");
        _economyReconciliationViolations = _meter.CreateCounter<long>(
            "fantasycard.economy.reconciliation.violations", unit: "{violation}");
        _expiredSessionsDeleted = _meter.CreateCounter<long>(
            "fantasycard.identity.sessions.expired_deleted", unit: "{session}");
        _expiredIdempotencyRecordsDeleted = _meter.CreateCounter<long>(
            "fantasycard.persistence.idempotency.expired_deleted", unit: "{record}");
        _expiredRoomEventsDeleted = _meter.CreateCounter<long>(
            "fantasycard.persistence.room_events.expired_deleted", unit: "{event}");
        _expiredPreparations = _meter.CreateCounter<long>(
            "fantasycard.matchmaking.preparations.expired", unit: "{preparation}");
        _expiredMatchTickets = _meter.CreateCounter<long>(
            "fantasycard.matchmaking.tickets.expired", unit: "{ticket}");
        _identitySignInSuccesses = _meter.CreateCounter<long>(
            "fantasycard.identity.signins.succeeded", unit: "{signin}");
        _identitySignInFailures = _meter.CreateCounter<long>(
            "fantasycard.identity.signins.failed", unit: "{signin}");
        _identityTokenRejections = _meter.CreateCounter<long>(
            "fantasycard.identity.tokens.rejected", unit: "{token}");
        _identityExpiredTokens = _meter.CreateCounter<long>(
            "fantasycard.identity.tokens.expired", unit: "{token}");
        _matchmakingQueueDuration = _meter.CreateHistogram<double>(
            "fantasycard.matchmaking.queue.duration", unit: "s");
        _matchLaunchPhaseDuration = _meter.CreateHistogram<double>(
            "fantasycard.match_launch.phase.duration", unit: "ms");
        _matchLaunchFailures = _meter.CreateCounter<long>(
            "fantasycard.match_launch.failures", unit: "{failure}");
        _activeRooms = _meter.CreateUpDownCounter<long>(
            "fantasycard.rooms.active", unit: "{room}");
        _roomPlayerCount = _meter.CreateHistogram<long>(
            "fantasycard.rooms.players", unit: "{player}");
        _activeHumanRoomPlayers = _meter.CreateUpDownCounter<long>(
            "fantasycard.rooms.humans.active", unit: "{player}");
        _roomActorQueueLength = _meter.CreateHistogram<long>(
            "fantasycard.room_actor.queue.length", unit: "{command}");
        _roomActorCommandWait = _meter.CreateHistogram<double>(
            "fantasycard.room_actor.command.wait", unit: "ms");
        _roomActorTickDelay = _meter.CreateHistogram<double>(
            "fantasycard.room_actor.tick.delay", unit: "ms");
        _realtimeCommandDuration = _meter.CreateHistogram<double>(
            "fantasycard.realtime.command.duration", unit: "ms");
        _roomSnapshotDuration = _meter.CreateHistogram<double>(
            "fantasycard.room.snapshot.duration", unit: "ms");
        _pveDuration = _meter.CreateHistogram<double>(
            "fantasycard.combat.pve.duration", unit: "s");
        _pvpDuration = _meter.CreateHistogram<double>(
            "fantasycard.combat.pvp.duration", unit: "s");
        _pveAbnormalEnds = _meter.CreateCounter<long>(
            "fantasycard.combat.pve.abnormal_ends", unit: "{battle}");
        _pvpAbnormalEnds = _meter.CreateCounter<long>(
            "fantasycard.combat.pvp.abnormal_ends", unit: "{duel}");
        _migrationAttemptsFailed = _meter.CreateCounter<long>(
            "fantasycard.database.migration.attempts_failed", unit: "{attempt}");
        _migrationsApplied = _meter.CreateCounter<long>(
            "fantasycard.database.migrations.applied", unit: "{migration}");
        _databaseSchemaVersion = _meter.CreateHistogram<long>(
            "fantasycard.database.schema.version", unit: "{version}");
        _migrationDuration = _meter.CreateHistogram<double>(
            "fantasycard.database.migration.duration", unit: "s");
        _migrationRuns = _meter.CreateCounter<long>(
            "fantasycard.database.migration.runs", unit: "{run}");
        _settlementsCreated = _meter.CreateCounter<long>(
            "fantasycard.settlement.created", unit: "{settlement}");
        _settlementIdempotencyHits = _meter.CreateCounter<long>(
            "fantasycard.settlement.idempotency_hits", unit: "{settlement}");
    }

    public void RealtimeConnectionOpened() => _activeRealtimeConnections.Add(1);
    public void RealtimeConnectionClosed() => _activeRealtimeConnections.Add(-1);
    public void RealtimeMessageReceived() => _realtimeMessages.Add(1);
    public void ObserveRealtimeMessageBytes(long bytes) => _realtimeMessageBytes.Record(bytes);
    public void RealtimeResumed() => _realtimeResumes.Add(1);
    public void RealtimeCommandRejected(string code) =>
        _realtimeRejectedCommands.Add(1, new KeyValuePair<string, object?>("code", code));
    public void RealtimeCommandRateLimited() => _realtimeRateLimitedCommands.Add(1);
    public void RealtimeStreamsExpired(long count) => _realtimeStreamsExpired.Add(count);
    public void RoomSnapshotFailed() => _roomSnapshotFailures.Add(1);
    public void SettlementFailed() => _settlementFailures.Add(1);
    public void SettlementHoldsCommitted(long count) => _settlementCommittedHolds.Add(count);
    public void ObserveSettlementPendingHolds(long count) => _settlementPendingHolds.Record(count);
    public void EconomyReconciliationViolated(long count) => _economyReconciliationViolations.Add(count);
    public void ExpiredSessionsDeleted(long count) => _expiredSessionsDeleted.Add(count);
    public void IdentitySignInSucceeded(string provider) =>
        _identitySignInSuccesses.Add(1, new KeyValuePair<string, object?>("provider", provider));
    public void IdentitySignInFailed(string provider, string reason) =>
        _identitySignInFailures.Add(1,
            new KeyValuePair<string, object?>("provider", provider),
            new KeyValuePair<string, object?>("reason", reason));
    public void IdentityTokenRejected() => _identityTokenRejections.Add(1);
    public void IdentityTokenExpired() => _identityExpiredTokens.Add(1);
    public void ObserveMatchmakingQueueDuration(TimeSpan duration) =>
        _matchmakingQueueDuration.Record(Math.Max(0, duration.TotalSeconds));
    public void ObserveMatchLaunchPhase(string phase, TimeSpan duration) =>
        _matchLaunchPhaseDuration.Record(Math.Max(0, duration.TotalMilliseconds),
            new KeyValuePair<string, object?>("phase", phase));
    public void MatchLaunchFailed(string phase) =>
        _matchLaunchFailures.Add(1, new KeyValuePair<string, object?>("phase", phase));
    public void RoomOpened(long playerCount)
    {
        _activeRooms.Add(1);
        _roomPlayerCount.Record(playerCount);
    }
    public void RoomClosed() => _activeRooms.Add(-1);
    public void RoomHumanPlayersChanged(long delta) => _activeHumanRoomPlayers.Add(delta);
    public void ObserveRoomActorQueueLength(long count) => _roomActorQueueLength.Record(Math.Max(0, count));
    public void ObserveRoomActorCommandWait(string command, TimeSpan wait) =>
        _roomActorCommandWait.Record(
            Math.Max(0, wait.TotalMilliseconds),
            new KeyValuePair<string, object?>("command", command));
    public void ObserveRoomActorTickDelay(TimeSpan delay) =>
        _roomActorTickDelay.Record(Math.Max(0, delay.TotalMilliseconds));
    public void ObserveRealtimeCommandDuration(string command, TimeSpan duration) =>
        _realtimeCommandDuration.Record(
            Math.Max(0, duration.TotalMilliseconds),
            new KeyValuePair<string, object?>("command", command));
    public void ObserveRoomSnapshotDuration(TimeSpan duration) =>
        _roomSnapshotDuration.Record(Math.Max(0, duration.TotalMilliseconds));
    public void ObservePveDuration(TimeSpan duration, string outcome) =>
        _pveDuration.Record(Math.Max(0, duration.TotalSeconds),
            new KeyValuePair<string, object?>("outcome", outcome));
    public void ObservePvpDuration(TimeSpan duration, string outcome) =>
        _pvpDuration.Record(Math.Max(0, duration.TotalSeconds),
            new KeyValuePair<string, object?>("outcome", outcome));
    public void PveEndedAbnormally(string reason) =>
        _pveAbnormalEnds.Add(1, new KeyValuePair<string, object?>("reason", reason));
    public void PvpEndedAbnormally(string reason) =>
        _pvpAbnormalEnds.Add(1, new KeyValuePair<string, object?>("reason", reason));
    public void DatabaseMigrationAttemptFailed() => _migrationAttemptsFailed.Add(1);
    public void DatabaseMigrationApplied() => _migrationsApplied.Add(1);
    public void ObserveDatabaseSchemaVersion(long version) => _databaseSchemaVersion.Record(version);
    public void DatabaseMigrationFinished(TimeSpan duration, bool succeeded)
    {
        _migrationDuration.Record(Math.Max(0, duration.TotalSeconds));
        _migrationRuns.Add(1,
            new KeyValuePair<string, object?>("result", succeeded ? "succeeded" : "failed"));
    }
    public void SettlementCreated() => _settlementsCreated.Add(1);
    public void SettlementIdempotencyHit() => _settlementIdempotencyHits.Add(1);
    public void ExpiredDataDeleted(long sessions, long idempotencyRecords, long roomEvents, long preparations, long matchTickets)
    {
        _expiredSessionsDeleted.Add(sessions);
        _expiredIdempotencyRecordsDeleted.Add(idempotencyRecords);
        _expiredRoomEventsDeleted.Add(roomEvents);
        _expiredPreparations.Add(preparations);
        _expiredMatchTickets.Add(matchTickets);
    }

    public void Dispose() => _meter.Dispose();
}
