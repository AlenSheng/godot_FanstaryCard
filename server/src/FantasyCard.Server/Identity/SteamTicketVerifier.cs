using System.Globalization;
using System.Text.Json;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Identity;

public sealed class SteamTicketVerifier : IDisposable
{
    private static readonly Uri Endpoint = new(
        "https://partner.steam-api.com/ISteamUserAuth/AuthenticateUserTicket/v1/");
    private readonly HttpClient _httpClient;
    private readonly SteamAuthOptions _options;

    [ActivatorUtilitiesConstructor]
    public SteamTicketVerifier(IOptions<SteamAuthOptions> options)
        : this(new HttpClient { Timeout = TimeSpan.FromSeconds(10) }, options)
    {
    }

    public SteamTicketVerifier(HttpClient httpClient, IOptions<SteamAuthOptions> options)
    {
        _httpClient = httpClient;
        _options = options.Value;
    }

    public async Task<string?> VerifyAsync(string? ticket, CancellationToken cancellationToken)
    {
        var normalizedTicket = ticket?.Trim();
        if (!_options.Enabled || string.IsNullOrEmpty(normalizedTicket) ||
            normalizedTicket.Length is < 2 or > 8192 ||
            normalizedTicket.Length % 2 != 0 ||
            normalizedTicket.Any(character => !Uri.IsHexDigit(character)))
            return null;

        var url = QueryHelpers.AddQueryString(Endpoint.ToString(), new Dictionary<string, string?>
        {
            ["key"] = _options.PublisherKey,
            ["appid"] = _options.AppId.ToString(CultureInfo.InvariantCulture),
            ["ticket"] = normalizedTicket,
            ["identity"] = _options.Identity
        });
        using var response = await _httpClient.GetAsync(url, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException("Steam ticket verification returned a non-success status.", null, response.StatusCode);
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken);
        return ParseSteamId(document.RootElement);
    }

    internal static string? ParseSteamId(JsonElement root)
    {
        if (!root.TryGetProperty("response", out var responseElement) ||
            !responseElement.TryGetProperty("params", out var parameters) ||
            !parameters.TryGetProperty("result", out var result) ||
            !string.Equals(result.GetString(), "OK", StringComparison.Ordinal) ||
            !parameters.TryGetProperty("steamid", out var steamId))
            return null;
        var steamIdText = steamId.ValueKind == JsonValueKind.String
            ? steamId.GetString()
            : steamId.GetRawText();
        if (!ulong.TryParse(steamIdText, NumberStyles.None, CultureInfo.InvariantCulture, out var parsedSteamId))
            return null;
        return parsedSteamId.ToString(CultureInfo.InvariantCulture);
    }

    public void Dispose() => _httpClient.Dispose();
}
