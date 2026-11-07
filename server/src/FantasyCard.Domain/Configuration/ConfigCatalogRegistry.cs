using System.Collections.Concurrent;
using System.Diagnostics.CodeAnalysis;

namespace FantasyCard.Domain.Configuration;

/// <summary>Retains immutable published versions; an unknown room version never selects the current version.</summary>
public sealed class ConfigCatalogRegistry
{
    private readonly ConcurrentDictionary<string, GameConfigCatalog> _catalogs = new(StringComparer.Ordinal);

    public ConfigCatalogRegistry(GameConfigCatalog initial)
    {
        ArgumentNullException.ThrowIfNull(initial);
        _catalogs.TryAdd(initial.Version, initial);
    }

    public GameConfigCatalog Resolve(string version)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(version);
        return _catalogs.TryGetValue(version, out var catalog) ? catalog
            : throw new InvalidDataException($"Published configuration '{version}' is not loaded.");
    }

    public bool TryResolve(string version, [NotNullWhen(true)] out GameConfigCatalog? catalog)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(version);
        return _catalogs.TryGetValue(version, out catalog);
    }

    public GameConfigCatalog Register(string expectedVersion, string expectedContentHash, ReadOnlySpan<byte> bytes)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedVersion);
        ArgumentException.ThrowIfNullOrWhiteSpace(expectedContentHash);
        var candidate = GameConfigCatalog.Load(bytes);
        if (candidate.Version != expectedVersion ||
            !string.Equals(candidate.ContentHash, expectedContentHash, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Archived configuration does not match its published version and content hash.");
        var retained = _catalogs.GetOrAdd(candidate.Version, candidate);
        if (retained.ContentHash != candidate.ContentHash)
            throw new InvalidDataException($"Published configuration '{candidate.Version}' cannot be replaced with different data.");
        return retained;
    }
}
