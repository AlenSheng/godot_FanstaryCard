using FantasyCard.Domain.Configuration;

namespace FantasyCard.Server.Rooms;

/// <summary>Loads a room's exact published bundle without changing the active lobby configuration.</summary>
public sealed class PublishedConfigCatalogs
{
    private readonly ConfigCatalogRegistry _registry;
    private readonly string? _archiveDirectory;

    public PublishedConfigCatalogs(GameConfigCatalog current, string? archiveDirectory = null)
    {
        _registry = new ConfigCatalogRegistry(current);
        _archiveDirectory = string.IsNullOrWhiteSpace(archiveDirectory) ? null : Path.GetFullPath(archiveDirectory);
    }

    public GameConfigCatalog Resolve(string version)
    {
        if (_registry.TryResolve(version, out var retained)) return retained;
        if (_archiveDirectory is null)
            throw new InvalidDataException($"Published configuration '{version}' is not loaded and no archive is configured.");
        if (version.Length > 128 || version is "." or ".." ||
            version.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not ('.' or '-' or '_')))
            throw new InvalidDataException("Archived configuration version is not a valid directory name.");
        var directory = Path.Combine(_archiveDirectory, version);
        var declaredVersion = File.ReadAllText(Path.Combine(directory, "fantasycard.config.version.txt")).Trim();
        if (declaredVersion != version)
            throw new InvalidDataException("Archived configuration directory and published version differ.");
        var hash = File.ReadAllText(Path.Combine(directory, "fantasycard.config.sha256")).Trim();
        var bytes = File.ReadAllBytes(Path.Combine(directory, "fantasycard.config.bytes"));
        return _registry.Register(version, hash, bytes);
    }
}
