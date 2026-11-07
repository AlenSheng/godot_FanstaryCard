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
        catch (CombatActionAlreadyAppliedException)
        {
            if (_roomRegistry is not null && _roomRegistry.TryGetForPlayer(player.UserId, out var actor, out var matchId) &&
                actor is not null && matchId is { } current && MatchesRequestedRoom(command, actor, matchId))
            {
                var state = await actor.ExecuteAsync(new GetRoomClientStateCommand(player.UserId), cancellationToken);
                return CancelTerminalCommand(player.UserId, command, traceId, state, current, "CombatActionAlreadyApplied");
            }
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
                FantasyCard.Domain.Configuration.GameConfigCatalog configuration;
                try
                {
                    configuration = _configurations.Resolve(checkpoint.Snapshot.ConfigVersion);
                }
                catch (IOException)
                {
                    return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", "The room's published configuration is unavailable.")];
                }
                var room = BattleRoom.Restore(checkpoint.Snapshot, CombatCardCatalog.Create(configuration), checkpoint.Seed);
                var state = new GetRoomClientStateCommand(player.UserId).Execute(room);
                if (command.Type == "room.snapshot.read")
                    return [CreateRoomSnapshot(player.UserId, traceId, command.RequestId, state, matchId)];
                if (command.Type == "battle.play_cards" && command.Payload is BattlePlayCardsCommandPayload play &&
                    room.IsHistoricalCombatAction(player.UserId, play.CombatActionId))
                {
                    try
                    {
                        var resolution = room.ReplayCombatAction(player.UserId, play.CombatActionId, play.BattleId, play.TargetId, play.CardInstanceIds);
                        return [CombatResponse(player.UserId, command, traceId, resolution, play.CardInstanceIds),
                            CreateRoomSnapshot(player.UserId, traceId, command.RequestId, state, matchId)];
                    }
                    catch (CombatActionAlreadyAppliedException)
                    {
                        return CancelTerminalCommand(player.UserId, command, traceId, state, matchId, "CombatActionAlreadyApplied");
                    }
                    catch (DomainValidationException exception)
                    {
                        return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
                    }
                }
                return CancelTerminalCommand(player.UserId, command, traceId, state, matchId);
            }
        }
        return [Reject(player.UserId, traceId, command.RequestId, "NOT_IN_ROOM", "The player is not assigned to the requested room.")];
    }

    private IReadOnlyList<ServerEvent> CancelTerminalCommand(
        Guid playerId, ClientCommand command, string traceId, RoomClientState state, Guid matchId, string reason = "RoomEndedBeforeApply") =>
        [
            _eventStore.Create(playerId, "room.command_cancelled", traceId,
                new RoomCommandCancelledEventPayload(state.Snapshot.RoomId, matchId, command.Type, reason),
                command.RequestId, state.Snapshot.Revision),
            CreateRoomSnapshot(playerId, traceId, command.RequestId, state, matchId)
        ];
}
