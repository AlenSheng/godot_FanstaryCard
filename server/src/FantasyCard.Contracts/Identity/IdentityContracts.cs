using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Bootstrap;
using System.Text.Json.Serialization;

namespace FantasyCard.Contracts.Identity;

public sealed record LocalSignInRequest(string? DeviceId, string? DisplayName, string? ConfigVersion = null, bool IncludeBootstrap = false);

public sealed record SteamSignInRequest(string? Ticket, string? DisplayName, string? ConfigVersion = null, bool IncludeBootstrap = false);

public sealed record GoogleSignInRequest(string? IdToken, string? DisplayName, string? ConfigVersion = null, bool IncludeBootstrap = false);

public sealed record LocalSignInResponse(
    string AccessToken,
    DateTimeOffset ExpiresAt,
    PlayerProfileResponse Player)
{
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public BootstrapResponse? Bootstrap { get; init; }

    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public object? ClientInfo { get; init; }
}
