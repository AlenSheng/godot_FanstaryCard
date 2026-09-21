using FantasyCard.Contracts.Players;

namespace FantasyCard.Contracts.Identity;

public sealed record LocalSignInRequest(string? DeviceId, string? DisplayName);

public sealed record SteamSignInRequest(string? Ticket, string? DisplayName);

public sealed record GoogleSignInRequest(string? IdToken, string? DisplayName);

public sealed record LocalSignInResponse(
    string AccessToken,
    DateTimeOffset ExpiresAt,
    PlayerProfileResponse Player);
