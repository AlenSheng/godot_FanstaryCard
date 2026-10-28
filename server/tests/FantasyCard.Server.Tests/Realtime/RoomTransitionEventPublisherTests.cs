using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class RoomTransitionEventPublisherTests
{
    [Fact]
    public async Task Duel_death_publishes_ended_to_both_and_died_to_loser_once()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        var store = new RealtimeEventStore(TimeProvider.System);
        var matchId = Guid.NewGuid();
        var publisher = new RoomTransitionEventPublisher(room.Capture(), store, matchId: matchId);

        room.EndDuelWithDeath(duel.DuelId, lateId);
        var terminal = room.Capture();
        await publisher.ObserveAsync(terminal);
        await publisher.ObserveAsync(terminal);

        var winnerEvents = store.ReadAfter(firstId, 0).Events;
        var loserEvents = store.ReadAfter(lateId, 0).Events;
        var winnerEnded = Assert.IsType<DuelEndedEventPayload>(Assert.Single(winnerEvents).Payload);
        Assert.Equal((duel.DuelId, "death", firstId), (winnerEnded.DuelId, winnerEnded.Reason, winnerEnded.WinnerId));
        Assert.Collection(
            loserEvents,
            message => Assert.IsType<DuelEndedEventPayload>(message.Payload),
            message =>
            {
                var died = Assert.IsType<PlayerDiedEventPayload>(message.Payload);
                Assert.Equal((lateId, "PvpDeath", duel.DuelId), (died.PlayerId, died.Cause, died.DuelId));
                Assert.Equal((room.RoomId, matchId), (died.RoomId, died.MatchId));
            });
        Assert.All(winnerEvents.Concat(loserEvents), message => Assert.Equal(terminal.Revision, message.RoomRevision));
    }

    [Fact]
    public async Task Mutual_leave_publishes_a_non_death_duel_end()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        var store = new RealtimeEventStore(TimeProvider.System);
        var publisher = new RoomTransitionEventPublisher(room.Capture(), store);

        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        await publisher.ObserveAsync(room.Capture());

        foreach (var playerId in new[] { firstId, lateId })
        {
            var payload = Assert.IsType<DuelEndedEventPayload>(Assert.Single(store.ReadAfter(playerId, 0).Events).Payload);
            Assert.Equal("mutual_leave", payload.Reason);
            Assert.Null(payload.WinnerId);
            Assert.True(payload.SnapshotRequired);
        }
    }

    [Fact]
    public async Task Escape_attempt_transition_publishes_failed_to_both_players()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = CreateRoom(firstId, lateId);
        var duel = room.StartDuel(firstId, lateId, DateTimeOffset.UnixEpoch);
        room.RequestDuelEscape(duel.DuelId, firstId);
        var before = room.Capture();
        var attempt = Assert.Single(before.Duels).EscapeAttempt!;
        var after = before with
        {
            Revision = before.Revision + 1,
            Duels = [before.Duels[0] with
            {
                EscapeAttempt = null,
                EscapeCooldowns = [new DuelCooldownSnapshot(firstId, TimeSpan.FromSeconds(12))]
            }]
        };
        var store = new RealtimeEventStore(TimeProvider.System);
        var publisher = new RoomTransitionEventPublisher(before, store);

        await publisher.ObserveAsync(after);

        foreach (var playerId in new[] { firstId, lateId })
        {
            var message = Assert.Single(store.ReadAfter(playerId, 0).Events);
            Assert.Equal("duel.escape_failed", message.Type);
            var payload = Assert.IsType<DuelEscapeEventPayload>(message.Payload);
            Assert.Equal((duel.DuelId, attempt.Probability, "Failed"),
                (payload.DuelId, payload.Probability, payload.Status));
        }
    }

    [Fact]
    public async Task Extraction_transition_publishes_completion_once()
    {
        var playerId = Guid.NewGuid();
        var room = CreateRoom(playerId, Guid.NewGuid());
        var snapshot = room.Capture();
        var player = snapshot.Players.Single(value => value.PlayerId == playerId);
        var before = snapshot with
        {
            Players = snapshot.Players.Select(value => value.PlayerId == playerId
                ? value with { ExtractionRemaining = TimeSpan.FromSeconds(1) }
                : value).ToArray()
        };
        var after = before with
        {
            Revision = before.Revision + 1,
            Players = before.Players.Select(value => value.PlayerId == playerId
                ? value with { ExtractionRemaining = null, Phase = RoomPlayerPhase.Extracted }
                : value).ToArray()
        };
        var store = new RealtimeEventStore(TimeProvider.System);
        var publisher = new RoomTransitionEventPublisher(before, store);

        await publisher.ObserveAsync(after);
        await publisher.ObserveAsync(after);

        var message = Assert.Single(store.ReadAfter(playerId, 0).Events);
        Assert.Equal("action.extract_completed", message.Type);
        Assert.Equal("Completed", Assert.IsType<ActionExtractEventPayload>(message.Payload).Status);
    }

    private static BattleRoom CreateRoom(Guid firstId, Guid lateId)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 97);
        var cards = Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray();
        room.AddPlayer(new BattleRoomPlayerSetup(firstId, HeroClass.Mage, cards, null));
        room.AddPlayer(new BattleRoomPlayerSetup(lateId, HeroClass.Priest, cards, null));
        return room;
    }
}
