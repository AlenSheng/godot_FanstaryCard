namespace FantasyCard.Contracts.Players;

public enum HeroClassDto
{
    Priest = 1,
    Mage = 2,
    Guardian = 3
}

public sealed record PlayerProfileResponse(
    Guid UserId,
    string DisplayName,
    HeroClassDto? SelectedClass,
    long Version,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

public sealed record UpdatePlayerProfileRequest(
    string? DisplayName,
    HeroClassDto? SelectedClass,
    long ExpectedVersion);
