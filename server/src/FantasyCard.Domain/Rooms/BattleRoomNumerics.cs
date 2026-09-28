using FantasyCard.Domain.Players;
using FantasyCard.Domain.Combat;

namespace FantasyCard.Domain.Rooms;

public sealed partial class BattleRoom
{
    public long DecideMonsterCard(Guid playerId, Guid candidateId, bool accept, Guid? replaceId,
        string requestId, long expectedRevision)
    {
        var player = GetPlayer(playerId);
        if (!Numerics.OptionalMonsterPool)
            throw new DomainValidationException("Optional monster cards are disabled for this room.");
        if (player.MonsterPool.IsReplay(requestId, candidateId, accept, replaceId)) return Revision;
        if (expectedRevision > Revision)
            throw new DomainValidationException("The room changed; refresh the monster choices.");
        if (player.Phase is not (RoomPlayerPhase.Choice or RoomPlayerPhase.ActionBar) ||
            _extractions.ContainsKey(playerId) || _springDrinks.ContainsKey(playerId) ||
            _disconnects.ContainsKey(playerId))
            throw new DomainValidationException("Monster choices are available only after combat and outside channeling.");
        // Candidate ownership, active replacement identity and receipts guard stale requests; ticks alone do not invalidate a choice.
        var candidate = player.MonsterPool.Pending.SingleOrDefault(card => card.InstanceId == candidateId)
            ?? throw new DomainValidationException("The monster candidate no longer exists.");
        _ = _catalog.Get(candidate.CardId, candidate.Level, candidate.ElementOverride);
        player.MonsterPool.Decide(player.Combat.Deck, Numerics.MonsterCapacity, requestId, candidateId, accept, replaceId);
        Revision++;
        return Revision;
    }
}
