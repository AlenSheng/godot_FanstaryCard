using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Seasons;

namespace FantasyCard.Contracts.Matchmaking;

public sealed record SettlementResponse(
    Guid SettlementId,
    Guid MatchId,
    Guid PlayerId,
    string Result,
    JsonElement Details,
    DateTimeOffset CreatedAt,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] SeasonContextResponse? Season = null);

public sealed record SettlementAcknowledgementResponse(
    Guid SettlementId,
    DateTimeOffset AcknowledgedAt);
