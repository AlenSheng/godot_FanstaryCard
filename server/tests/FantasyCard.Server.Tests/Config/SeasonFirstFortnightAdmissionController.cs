using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Rooms;
using Npgsql;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Actual preparation/queue/Ready path, gated before any backend action. Not executed by the preflight.</summary>
internal sealed class SeasonFirstFortnightAdmissionController(
    NpgsqlDataSource dataSource,
    MatchmakingRepository matchmaking,
    RoomReadyCoordinator ready,
    RoomRegistry rooms,
    SeasonFirstFortnightPreparedController prepared,
    SeasonFirstFortnightTimeProvider clock,
    SeasonFirstFortnightExecutionPermit permit,
    SeasonFirstFortnightAttemptJournal journal)
{
    internal sealed record Admitted(Guid MatchId, Guid RoomId, int ActualSeed, RoomActor Actor,
        SeasonFirstFortnightActorClock Frames, BattleRoomSnapshot InitialState);

    internal async Task<Admitted> AdmitAsync(string caseId, SeasonFirstFortnightInputsTests.Actor actor,
        Guid playerId, Guid preparationId, DateTimeOffset scheduledAtUtc, CancellationToken cancellationToken)
    {
        // Require the recorded independent-item authorization before reads, queue mutation or journal creation.
        permit.RequireRealLaunch();
        if (permit.Maximum != journal.Maximum || !caseId.StartsWith(actor.Id + "-", StringComparison.Ordinal))
            throw new InvalidOperationException("F01 case actor or journal maximum differs from the confirmed plan.");
        var input = await prepared.BindAsync(actor, playerId, preparationId, scheduledAtUtc, 0, cancellationToken);
        journal.Reserve(caseId, actor.Id, preparationId, scheduledAtUtc, syntheticLedgerOnly: false);
        Guid? ticketId = null;
        Guid? matchId = null;
        Guid? roomId = null;
        var stage = "enqueue";
        try
        {
            var ticket = await matchmaking.EnqueueAsync(playerId, caseId + "-queue", new(preparationId), cancellationToken);
            ticketId = ticket.TicketId;
            journal.Phase(caseId, "queued", new { ticketId, preparationId });
            stage = "match";
            var pending = await matchmaking.TryCreateMatchAsync(cancellationToken)
                ?? throw new InvalidOperationException("F01 has no admitted pending match; retain its queued handle, never start another case.");
            matchId = pending.MatchId;
            roomId = pending.RoomId;
            journal.Phase(caseId, "pending", new { ticketId, matchId, roomId });
            if (pending.PlayerIds.Count != 1 || pending.PlayerIds[0] != playerId)
                throw new InvalidOperationException("F01 normal sequential scenario unexpectedly includes another controlled human.");
            stage = "ready";
            await matchmaking.MarkReadyAsync(playerId, clock.GetUtcNow(), cancellationToken);
            // This is the actual map launch boundary. The durable started record already exists.
            if (!await ready.ProcessNextAsync(clock.GetUtcNow(), cancellationToken))
                throw new InvalidOperationException("F01 Ready has not launched; retain the same match and do not retry automatically.");
            stage = "verify-running";
            if (!rooms.TryGetForPlayer(playerId, out var actorHandle, out var registeredMatch)
                || actorHandle is null || registeredMatch != pending.MatchId)
                throw new InvalidOperationException("F01 actual registry does not bind the expected admitted match.");
            await using var query = dataSource.CreateCommand("SELECT seed,status,room_id FROM matches WHERE match_id=$1");
            query.Parameters.AddWithValue(pending.MatchId);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken) || reader.GetString(1) != "Running" || reader.GetGuid(2) != actorHandle.RoomId)
                throw new InvalidOperationException("F01 actual match is not the original admitted Running room.");
            var actualSeed = reader.GetInt32(0);
            var frames = await SeasonFirstFortnightActorClock.BindAsync(actorHandle, clock, pending.RoomId,
                input.Context, scheduledAtUtc, TimeSpan.FromSeconds(1200), cancellationToken);
            var snapshot = await frames.CaptureStableAsync(cancellationToken);
            if (snapshot.Map is null || snapshot.Players.Count != 4 || snapshot.Players.Count(value => value.IsBot) != 3
                || snapshot.Players.Count(value => !value.IsBot) != 1)
                throw new InvalidOperationException("F01 normal match/map participant shape differs; do not remove or freeze bots.");
            var human = snapshot.Players.Single(value => value.PlayerId == playerId && !value.IsBot);
            var actualCards = human.Combat.Deck.Hand.Concat(human.Combat.Deck.Library).Concat(human.Combat.Deck.Discard).ToArray();
            if (!actualCards.Select(value => value.CardId).Order(StringComparer.Ordinal).SequenceEqual(input.Snapshot.CardIds.Order(StringComparer.Ordinal))
                || human.Combat.WeaponLevel != input.Snapshot.ClassWeaponLevel || human.Combat.MaximumHp != input.Snapshot.MaximumHp)
                throw new InvalidOperationException("F01 actual launched player differs from its prepared cards or weapon.");
            var levels = input.Snapshot.CardIds.Select((id, index) => (id, level: input.Snapshot.CardLevels![index]))
                .ToDictionary(value => value.id, value => value.level, StringComparer.Ordinal);
            if (actualCards.Any(card => card.Level != levels[card.CardId])
                || human.WornArmor is null
                || !human.WornArmor.Select(item => item.ItemId).Order(StringComparer.Ordinal).SequenceEqual(
                    input.Snapshot.EquipmentIds.OfType<Guid>().Select(id => id.ToString("D")).Order(StringComparer.Ordinal)))
                throw new InvalidOperationException("F01 actual levels or armor IDs differ from the prepared inputs.");
            journal.Phase(caseId, "admitted", new { ticketId, matchId, roomId, actualSeed, snapshot.ConfigVersion,
                snapshot.Season, snapshot.StartedAtUtc, participants = snapshot.Players.Count, bots = 3 });
            return new(pending.MatchId, pending.RoomId, actualSeed, actorHandle, frames, snapshot);
        }
        catch (Exception exception)
        {
            // Keep all known handles. A lost response may already have committed or launched.
            try { journal.Phase(caseId, "interrupted", new { stage, ticketId, matchId, roomId, errorType = exception.GetType().Name }); }
            catch (Exception journalException) { throw new AggregateException("F01 admission and its evidence write both failed; preserve the original handles.", exception, journalException); }
            throw;
        }
    }
}
