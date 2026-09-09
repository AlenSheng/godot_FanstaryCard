namespace FantasyCard.Server.Identity;

public sealed class IdentityOptions
{
    public const string SectionName = "Identity";

    public int SessionLifetimeDays { get; init; } = 30;

    public bool EnableLocalAuth { get; init; }
}

public sealed class SteamAuthOptions
{
    public const string SectionName = "Identity:Steam";

    public bool Enabled { get; init; }
    public uint AppId { get; init; }
    public string PublisherKey { get; init; } = string.Empty;
    public string Identity { get; init; } = string.Empty;
}
