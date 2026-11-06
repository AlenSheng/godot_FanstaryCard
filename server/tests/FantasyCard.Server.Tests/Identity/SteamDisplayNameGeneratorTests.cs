using System.Globalization;
using System.Text;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Tests.Identity;

public sealed class SteamDisplayNameGeneratorTests
{
    [Fact]
    public void Steam_persona_prefix_and_four_digit_suffix_are_preserved() =>
        Assert.Equal("Unity#1193", new SteamDisplayNameGenerator(() => 1193).RandomName("Unity"));

    [Fact]
    public void Name_normalization_and_unicode_truncation_preserve_the_complete_suffix()
    {
        var names = new SteamDisplayNameGenerator(() => 1193);
        Assert.Equal("Unity#1193", names.RandomName(" \tＵｎｉｔｙ\n "));
        var longName = string.Concat(Enumerable.Repeat("😀", 30));
        var candidate = names.RandomName(longName);
        Assert.Equal(PlayerProfile.MaxDisplayNameLength, candidate.EnumerateRunes().Count());
        Assert.EndsWith("#1193", candidate, StringComparison.Ordinal);
        Assert.Equal(candidate, PlayerProfile.NormalizeDisplayName(candidate));
        Assert.Throws<DomainValidationException>(() => names.RandomName("\t\r\n"));
    }

    [Fact]
    public void Timestamp_fallback_uses_current_unix_milliseconds_and_distinguishes_same_tick()
    {
        var now = new DateTimeOffset(2026, 10, 28, 0, 0, 0, TimeSpan.Zero);
        var names = new SteamDisplayNameGenerator();
        Assert.Equal("Unity#" + now.ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture), names.TimestampName("Unity", now));
        Assert.Equal("Unity#" + (now.ToUnixTimeMilliseconds() + 1).ToString(CultureInfo.InvariantCulture), names.TimestampName("Unity", now));
    }

    [Fact]
    public void Timestamp_fallback_truncates_only_the_persona_prefix()
    {
        var now = DateTimeOffset.UtcNow;
        var name = new SteamDisplayNameGenerator().TimestampName("A very long Steam persona name", now);
        Assert.Equal(PlayerProfile.MaxDisplayNameLength, name.EnumerateRunes().Count());
        Assert.EndsWith("#" + now.ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture), name, StringComparison.Ordinal);
    }
}
