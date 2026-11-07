namespace FantasyCard.Contracts.Configuration;

public sealed record PublishedConfigurationResponse(string ConfigVersion, string ContentHash, byte[] Bundle);
