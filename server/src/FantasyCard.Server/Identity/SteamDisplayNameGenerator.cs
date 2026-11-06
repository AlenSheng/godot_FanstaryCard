using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Players;

namespace FantasyCard.Server.Identity;

public sealed class SteamDisplayNameGenerator
{
    public const int RandomAttempts = 10;
    public const int TimestampAttempts = 64;
    private readonly Func<int> _nextRandom;
    private long _lastTimestamp;

    public SteamDisplayNameGenerator() : this(() => RandomNumberGenerator.GetInt32(1000, 10000)) { }

    internal SteamDisplayNameGenerator(Func<int> nextRandom) => _nextRandom = nextRandom;

    public string RandomName(string personaName)
    {
        var number = _nextRandom();
        if (number is < 1000 or > 9999) throw new InvalidOperationException("Steam name suffix must contain four digits.");
        return Compose(personaName, number.ToString(CultureInfo.InvariantCulture));
    }

    public string TimestampName(string personaName, DateTimeOffset now)
    {
        // Keep same-millisecond requests and clock rollback distinct inside this process.
        long previous;
        long next;
        do
        {
            previous = Volatile.Read(ref _lastTimestamp);
            next = Math.Max(now.ToUnixTimeMilliseconds(), checked(previous + 1));
        } while (Interlocked.CompareExchange(ref _lastTimestamp, next, previous) != previous);
        return Compose(personaName, next.ToString(CultureInfo.InvariantCulture));
    }

    private static string Compose(string personaName, string suffix)
    {
        ArgumentNullException.ThrowIfNull(personaName);
        var bounded = string.Concat(personaName.EnumerateRunes().Take(128).Select(rune => rune.ToString()));
        var normalized = bounded.Normalize(NormalizationForm.FormKC);
        var visible = string.Concat(normalized.EnumerateRunes().Where(rune => !Rune.IsControl(rune)).Select(rune => rune.ToString())).Trim();
        if (string.IsNullOrWhiteSpace(visible)) throw new DomainValidationException("Steam persona name is empty.");
        var available = PlayerProfile.MaxDisplayNameLength - suffix.Length - 1;
        if (available < 1) throw new DomainValidationException("Steam name suffix exceeds the supported length.");
        var prefix = string.Concat(visible.EnumerateRunes().Take(available).Select(rune => rune.ToString()));
        return PlayerProfile.NormalizeDisplayName(prefix + "#" + suffix);
    }
}
