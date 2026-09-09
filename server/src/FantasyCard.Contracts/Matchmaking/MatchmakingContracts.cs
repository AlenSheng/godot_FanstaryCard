namespace FantasyCard.Contracts.Matchmaking;

public sealed record EnqueueMatchRequest(Guid PreparationId);

public sealed record MatchTicketResponse(
    Guid TicketId,
    Guid PreparationId,
    string Status,
    DateTimeOffset QueuedAt,
    Guid? MatchId);
