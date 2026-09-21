namespace FantasyCard.Server.Identity;

public sealed class IdentityOptions
{
    public const string SectionName = "Identity";

    public int SessionLifetimeDays { get; init; } = 30;

    public bool EnableLocalAuth { get; init; }

    public int AccountDeletionCoolingPeriodDays { get; init; } = 7;

    public int RealtimeTicketLifetimeSeconds { get; init; } = 60;
}

public sealed class SteamAuthOptions
{
    public const string SectionName = "Identity:Steam";

    public bool Enabled { get; init; }
    public uint AppId { get; init; }
    public string PublisherKey { get; init; } = string.Empty;
    public string Identity { get; init; } = string.Empty;
}

public sealed class GoogleAuthOptions
{
    public const string SectionName = "Identity:Google";

    public bool Enabled { get; init; }
    public string WebClientId { get; init; } = string.Empty;
    public string[] AllowedAudiences { get; init; } = [];
    public bool RequireEmailVerified { get; init; } = true;

    public IReadOnlySet<string> GetAudiences() =>
        new HashSet<string>(
            AllowedAudiences.Append(WebClientId).Where(value => !string.IsNullOrWhiteSpace(value)),
            StringComparer.Ordinal);
}
