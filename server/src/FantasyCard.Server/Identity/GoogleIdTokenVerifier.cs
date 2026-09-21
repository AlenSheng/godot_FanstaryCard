using System.Globalization;
using System.Text.Json;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Identity;

public sealed record GoogleIdentity(string Subject);

public sealed class GoogleIdTokenVerifier(HttpClient httpClient, IOptions<GoogleAuthOptions> options)
{
    private static readonly Uri TokenInfoEndpoint = new("https://oauth2.googleapis.com/tokeninfo");
    private readonly GoogleAuthOptions _options = options.Value;

    public async Task<GoogleIdentity?> VerifyAsync(string? idToken, CancellationToken cancellationToken)
    {
        var normalized = idToken?.Trim();
        if (!_options.Enabled || string.IsNullOrWhiteSpace(normalized) || normalized.Length > 8192)
            return null;

        var url = QueryHelpers.AddQueryString(TokenInfoEndpoint.ToString(), "id_token", normalized);
        using var response = await httpClient.GetAsync(url, cancellationToken);
        if (!response.IsSuccessStatusCode)
            return null;

        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);
        var root = document.RootElement;
        var issuer = ReadString(root, "iss");
        if (issuer is not ("accounts.google.com" or "https://accounts.google.com"))
            return null;

        var audience = ReadString(root, "aud");
        if (audience is null || !_options.GetAudiences().Contains(audience))
            return null;

        var subject = ReadString(root, "sub");
        if (subject is null || subject.Length is < 1 or > 256)
            return null;

        if (!long.TryParse(ReadString(root, "exp"), NumberStyles.None, CultureInfo.InvariantCulture, out var expiry) ||
            expiry <= DateTimeOffset.UtcNow.ToUnixTimeSeconds())
            return null;
        if (long.TryParse(ReadString(root, "iat"), NumberStyles.None, CultureInfo.InvariantCulture, out var issuedAt) &&
            issuedAt > DateTimeOffset.UtcNow.AddMinutes(1).ToUnixTimeSeconds())
            return null;

        if (_options.RequireEmailVerified &&
            (!root.TryGetProperty("email_verified", out var verified) ||
             !string.Equals(verified.GetString(), "true", StringComparison.OrdinalIgnoreCase)))
            return null;

        return new GoogleIdentity(subject);
    }

    private static string? ReadString(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
}
