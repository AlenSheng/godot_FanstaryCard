using System.Security.Cryptography;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSteamDisplayNameTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Requires owned PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Random_collision_is_checked_across_normalized_names_and_relogin_keeps_the_profile()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var ct = TestContext.Current.CancellationToken;
        var existing = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        await existing.SignInLocalAsync("owned-device", "unity#1193", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var calls = 0;
        var names = new SteamDisplayNameGenerator(() => Interlocked.Increment(ref calls) == 1 ? 1193 : 1194);
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService(), names);
        var created = await identity.SignInSteamAsync("verified-one", "Ｕｎｉｔｙ", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal("Unity#1194", created.DisplayName);
        Assert.Equal(2, calls);
        var returning = await identity.SignInSteamAsync("verified-one", "Changed Steam name", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal(created.UserId, returning.UserId);
        Assert.Equal(created.DisplayName, returning.DisplayName);
        Assert.Equal(2, calls);
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
    }

    [Fact(Skip = "Requires owned PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Ten_random_collisions_use_timestamp_and_a_timestamp_collision_is_retried()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = new DateTimeOffset(2026, 10, 28, 0, 0, 0, TimeSpan.Zero);
        var ct = TestContext.Current.CancellationToken;
        var existing = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        await existing.SignInLocalAsync("owned-device", "Unity#1193", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await existing.SignInLocalAsync("owned-device", "Unity#" + now.ToUnixTimeMilliseconds(), RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var calls = 0;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService(), new SteamDisplayNameGenerator(() => { Interlocked.Increment(ref calls); return 1193; }));
        var profile = await identity.SignInSteamAsync("verified-fallback", "Unity", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal("Unity#" + (now.ToUnixTimeMilliseconds() + 1), profile.DisplayName);
        Assert.Equal(SteamDisplayNameGenerator.RandomAttempts, calls);
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM external_identities WHERE provider='steam'"));
    }

    [Fact(Skip = "Requires owned PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_same_persona_accounts_receive_unique_names_and_one_identity_stays_one_account()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var ct = TestContext.Current.CancellationToken;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService(), new SteamDisplayNameGenerator(() => 1193));
        var profiles = await Task.WhenAll(Enumerable.Range(0, 8).Select(i => identity.SignInSteamAsync(
            "verified-concurrent-" + i, "Unity", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct)));
        Assert.Equal(8, profiles.Select(p => p.DisplayName).Distinct(StringComparer.OrdinalIgnoreCase).Count());
        Assert.All(profiles, p => Assert.StartsWith("Unity#", p.DisplayName, StringComparison.Ordinal));
        var returning = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => identity.SignInSteamAsync(
            "verified-concurrent-0", "New persona", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct)));
        Assert.All(returning, p => Assert.Equal(profiles[0].UserId, p.UserId));
        Assert.Equal(8L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
        Assert.Equal(8L, await database.ScalarAsync<long>("SELECT count(*) FROM external_identities WHERE provider='steam'"));
    }
}
