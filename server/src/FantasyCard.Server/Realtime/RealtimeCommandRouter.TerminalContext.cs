using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Realtime;

public sealed partial class RealtimeCommandRouter
{
    private async ValueTask<IReadOnlyList<ServerEvent>> RouteContextualCoreAsync(
        PlayerProfile player, ClientCommand command, string traceId, CancellationToken cancellationToken)
    {
        if ((command.RoomId is null) != (command.MatchId is null) ||
            command.RoomId == Guid.Empty || command.MatchId == Guid.Empty)
            return [Reject(player.UserId, traceId, command.RequestId, "INVALID_ROOM_CONTEXT", "Room and match IDs must be supplied together.")];
        try
        {
            return await RouteCoreAsync(player, command, traceId, cancellationToken);
        }
        catch (RoomAlreadyEndedException ended)
        {
            // The serialized actor checked terminal phase before invoking the
            // mutation. Its result therefore cannot be mistaken for an ACK.
            if (command.RoomId == ended.State.Snapshot.RoomId && command.MatchId is { } matchId)
                return CancelTerminalCommand(player.UserId, command, traceId, ended.State, matchId);
            return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", ended.Message)];
        }
        catch (RoomActorClosedException)
        {
            return await ResolveTerminalCommandAsync(player, command, traceId, cancellationToken);
        }
    }

    private static bool MatchesRequestedRoom(ClientCommand command, RoomActor actor, Guid? matchId) =>
        command.RoomId is null || (command.RoomId == actor.RoomId && command.MatchId == matchId);

    private async ValueTask<IReadOnlyList<ServerEvent>> ResolveTerminalCommandAsync(
        PlayerProfile player, ClientCommand command, string traceId, CancellationToken cancellationToken)
    {
        if (_roomSnapshotRepository is not null && command.RoomId is { } roomId && command.MatchId is { } matchId)
        {
            var checkpoint = await _roomSnapshotRepository.GetOwnedTerminalAsync(player.UserId, roomId, matchId, cancellationToken);
            if (checkpoint is not null)
            {
                // This temporary domain projection has no actor, ticker,
                // observer, persistence writer or asset/settlement side effects.
                var room = BattleRoom.Restore(checkpoint.Snapshot, CombatCardCatalog.CreatePrototype(), checkpoint.Seed);
                var state = new GetRoomClientStateCommand(player.UserId).Execute(room);
                if (command.Type == "room.snapshot.read")
                    return [CreateRoomSnapshot(player.UserId, traceId, command.RequestId, state, matchId)];
                return CancelTerminalCommand(player.UserId, command, traceId, state, matchId);
            }
        }
        return [Reject(player.UserId, traceId, command.RequestId, "NOT_IN_ROOM", "The player is not assigned to the requested room.")];
    }

    private IReadOnlyList<ServerEvent> CancelTerminalCommand(
        Guid playerId, ClientCommand command, string traceId, RoomClientState state, Guid matchId) =>
        [
            _eventStore.Create(playerId, "room.command_cancelled", traceId,
                new RoomCommandCancelledEventPayload(state.Snapshot.RoomId, matchId, command.Type, "RoomEndedBeforeApply"),
                command.RequestId, state.Snapshot.Revision),
            CreateRoomSnapshot(playerId, traceId, command.RequestId, state, matchId)
        ];
}
