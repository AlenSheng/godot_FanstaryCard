using System.Text.Json;

namespace FantasyCard.Contracts.Matchmaking;

public sealed record SettlementResponse(
    Guid SettlementId,
    Guid MatchId,
    Guid PlayerId,
    string Result,
    JsonElement Details,
    DateTimeOffset CreatedAt);

public sealed record SettlementAcknowledgementResponse(
    Guid SettlementId,
    DateTimeOffset AcknowledgedAt);
