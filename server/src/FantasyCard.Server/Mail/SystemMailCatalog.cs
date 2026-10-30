using System.Collections.Frozen;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace FantasyCard.Server.Mail;

public sealed record SystemMailText(string Title, string Body, string TitleEn, string BodyEn);

/// <summary>Generated display copy only; amounts, grants and identity remain authoritative elsewhere.</summary>
public sealed partial class SystemMailCatalog
{
    private static readonly Lazy<SystemMailCatalog> Embedded = new(LoadEmbedded);
    private static readonly string[] TemplateIds =
    [
        "seed_gold", "seed_souls", "seed_white_fire", "seed_green_water", "seed_blue_earth",
        "seed_purple_wood", "seed_orange_metal", "seed2_mixed_set", "seed2_fragments", "item_reclamation"
    ];
    private readonly FrozenDictionary<string, FrozenDictionary<string, string>> _locales;

    private SystemMailCatalog(FrozenDictionary<string, FrozenDictionary<string, string>> locales) => _locales = locales;

    public static SystemMailCatalog Current => Embedded.Value;

    public static SystemMailCatalog Load(Stream stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        using var document = JsonDocument.Parse(stream);
        var root = document.RootElement;
        if (root.GetProperty("schema_version").GetInt32() != 1)
            throw new InvalidDataException("Unsupported system mail locale schema.");
        var locales = root.GetProperty("locales").EnumerateObject().ToFrozenDictionary(
            locale => locale.Name,
            locale => locale.Value.EnumerateObject().ToFrozenDictionary(
                entry => entry.Name,
                entry => entry.Value.GetString() ?? throw new InvalidDataException("System mail copy must be a string."),
                StringComparer.Ordinal),
            StringComparer.Ordinal);
        var catalog = new SystemMailCatalog(locales);
        foreach (var locale in new[] { "zh-CN", "en" })
        {
            foreach (var templateId in TemplateIds)
            {
                _ = catalog.Text(locale, "mail_" + templateId + "_title");
                _ = catalog.Text(locale, "mail_" + templateId + "_body");
            }
            foreach (var key in new[] { "system_sender", "admin_sender", "traveler_default_name" })
                _ = catalog.Text(locale, key);
        }
        return catalog;
    }

    public SystemMailText Render(string templateId, IReadOnlyDictionary<string, string>? arguments = null)
    {
        if (!TemplateIds.Contains(templateId, StringComparer.Ordinal))
            throw new InvalidDataException("Unknown system mail template ID.");
        string Field(string locale, string field) => Format(Text(locale, "mail_" + templateId + "_" + field), arguments);
        return new(Field("zh-CN", "title"), Field("zh-CN", "body"), Field("en", "title"), Field("en", "body"));
    }

    public string Sender(string role) => Text("en", role switch
    {
        "system" => "system_sender",
        "admin" => "admin_sender",
        _ => throw new InvalidDataException("Unknown system mail sender role.")
    });

    public string TravelerFallback => Text("zh-CN", "traveler_default_name");

    /// <summary>Matches only the original template. Inserted reason text is never scanned a second time.</summary>
    public static string Format(string template, IReadOnlyDictionary<string, string>? arguments)
    {
        ArgumentNullException.ThrowIfNull(template);
        return Placeholder().Replace(template, match =>
            arguments is not null && arguments.TryGetValue(match.Groups[1].Value, out var value)
                ? value
                : throw new InvalidDataException("Missing system mail template argument."));
    }

    private string Text(string locale, string key) =>
        _locales.TryGetValue(locale, out var entries) && entries.TryGetValue(key, out var text) && text.Length > 0
            ? text
            : throw new InvalidDataException($"Missing generated system mail copy: {locale}/{key}.");

    [GeneratedRegex(@"\{([A-Za-z_][A-Za-z0-9_]*)\}", RegexOptions.CultureInvariant)]
    private static partial Regex Placeholder();

    private static SystemMailCatalog LoadEmbedded()
    {
        using var stream = typeof(SystemMailCatalog).Assembly.GetManifestResourceStream("FantasyCard.SystemMailLocales.json")
            ?? throw new InvalidDataException("Missing generated system mail locale resource.");
        return Load(stream);
    }
}
