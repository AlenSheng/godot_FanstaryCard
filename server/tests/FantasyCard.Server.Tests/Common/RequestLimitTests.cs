using FantasyCard.Server.Common;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.DependencyInjection;
using FantasyCard.Server.Persistence;
using Npgsql;
using System.Net;

namespace FantasyCard.Server.Tests.Common;

public sealed class RequestLimitTests
{
    [Fact]
    public void Realtime_limiter_rejects_overflow_within_one_second()
    {
        var limiter = new RealtimeCommandRateLimiter(3);
        var now = DateTimeOffset.UnixEpoch;

        Assert.True(limiter.TryAcquire(now));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(100)));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(200)));
        Assert.False(limiter.TryAcquire(now.AddMilliseconds(999)));
    }

    [Fact]
    public void Realtime_limiter_releases_only_expired_entries()
    {
        var limiter = new RealtimeCommandRateLimiter(2);
        var now = DateTimeOffset.UnixEpoch;
        Assert.True(limiter.TryAcquire(now));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(500)));

        Assert.True(limiter.TryAcquire(now.AddSeconds(1)));
        Assert.False(limiter.TryAcquire(now.AddMilliseconds(1499)));
        Assert.True(limiter.TryAcquire(now.AddMilliseconds(1500)));
    }

    [Fact]
    public void Realtime_limiter_requires_a_positive_limit()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new RealtimeCommandRateLimiter(0));
    }

    [Fact]
    public void Owned_test_realtime_bypass_accepts_burst_without_raising_default_limits()
    {
        Assert.False(new RequestLimitOptions().OwnedTestBypass);
        var limiter = new RealtimeCommandRateLimiter(1, ownedTestBypass: true);
        for (var i = 0; i < 10_001; i++) Assert.True(limiter.TryAcquire(DateTimeOffset.UnixEpoch));
    }

    [Theory]
    [InlineData("Production", "http://127.0.0.1:28081", "127.0.0.1", "pr13_tencent_live_0123456789abcdef", "pr13-tencent-20261009")]
    [InlineData("Development", "http://0.0.0.0:28081", "127.0.0.1", "pr13_tencent_live_0123456789abcdef", "pr13-tencent-20261009")]
    [InlineData("Development", "", "127.0.0.1", "pr13_tencent_live_0123456789abcdef", "pr13-tencent-20261009")]
    [InlineData("Development", "http://localhost:28081;http://0.0.0.0:8080", "127.0.0.1", "pr13_tencent_live_0123456789abcdef", "pr13-tencent-20261009")]
    [InlineData("Development", "http://127.0.0.1:28081", "postgres", "pr13_tencent_live_0123456789abcdef", "pr13-tencent-20261009")]
    [InlineData("Development", "http://127.0.0.1:28081", "127.0.0.1", "fantasycard", "pr13-tencent-20261009")]
    [InlineData("Development", "http://127.0.0.1:28081", "127.0.0.1", "pr13_tencent_live_0123456789abcdef", "")]
    public void Unsafe_bypass_configuration_fails_before_host_starts(string environment, string urls, string host, string database, string session)
    {
        var config = TestConfig(urls, host, database, session);
        Assert.Throws<InvalidOperationException>(() => RequestLimitExtensions.ValidateOwnedTestBypass(config, new TestEnvironment(environment)));
    }

    [Fact]
    public void Guard_accepts_owned_test_and_keeps_disabled_production_configuration_valid()
    {
        RequestLimitExtensions.ValidateOwnedTestBypass(TestConfig(), new TestEnvironment("Development"));
        RequestLimitExtensions.ValidateOwnedTestBypass(new ConfigurationBuilder().Build(), new TestEnvironment("Production"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Application_connection_pool_ceiling_is_removed_only_in_owned_test_profile(bool bypass)
    {
        var config = TestConfig();
        config["RequestLimits:OwnedTestBypass"] = bypass.ToString();
        RequestLimitExtensions.ValidateOwnedTestBypass(config, new TestEnvironment("Development"));
        var services = new ServiceCollection();
        services.AddFantasyCardPersistence(config);
        using var provider = services.BuildServiceProvider();
        var connection = new NpgsqlConnectionStringBuilder(provider.GetRequiredService<NpgsqlDataSource>().ConnectionString);
        Assert.Equal(!bypass, connection.Pooling);
        Assert.Equal(16, connection.MaxPoolSize);
    }

    [Fact]
    public void Owned_capacity_profile_retains_reuse_with_a_256_connection_budget()
    {
        var config = TestConfig();
        config["Persistence:OwnedTestPoolReuse"] = "true";
        RequestLimitExtensions.ValidateOwnedTestBypass(config, new TestEnvironment("Development"));
        var services = new ServiceCollection();
        services.AddFantasyCardPersistence(config);
        using var provider = services.BuildServiceProvider();
        var connection = new NpgsqlConnectionStringBuilder(provider.GetRequiredService<NpgsqlDataSource>().ConnectionString);
        Assert.True(connection.Pooling);
        Assert.Equal(256, connection.MaxPoolSize);
        Assert.Equal(1, connection.MinPoolSize);
        Assert.Equal(5, connection.Timeout);
        Assert.Equal(10, connection.CommandTimeout);
    }

    [Fact]
    public void Connection_reuse_override_requires_owned_test_bypass()
    {
        var config = TestConfig();
        config["RequestLimits:OwnedTestBypass"] = "false";
        config["Persistence:OwnedTestPoolReuse"] = "true";
        Assert.Throws<InvalidOperationException>(() => new ServiceCollection().AddFantasyCardPersistence(config));
    }

    [Theory]
    [InlineData(RequestLimitOptions.AuthPolicy, false)]
    [InlineData(RequestLimitOptions.AdminPolicy, false)]
    [InlineData(RequestLimitOptions.ReadPolicy, false)]
    [InlineData(RequestLimitOptions.WritePolicy, false)]
    [InlineData(RequestLimitOptions.AuthPolicy, true)]
    [InlineData(RequestLimitOptions.AdminPolicy, true)]
    [InlineData(RequestLimitOptions.ReadPolicy, true)]
    [InlineData(RequestLimitOptions.WritePolicy, true)]
    public async Task Real_same_IP_requests_observe_policy_bypass_only_when_enabled(string policy, bool bypass)
    {
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = "Development" });
        builder.Configuration.AddConfiguration(TestConfig());
        builder.Configuration["RequestLimits:OwnedTestBypass"] = bypass.ToString();
        foreach (var key in new[] { "AuthPermitLimit", "AdminPermitLimit", "MarketReadPermitLimit", "EconomyWritePermitLimit" })
            builder.Configuration["RequestLimits:" + key] = "1";
        RequestLimitExtensions.ValidateOwnedTestBypass(builder.Configuration, builder.Environment);
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Services.AddFantasyCardRequestLimits(builder.Configuration);
        await using var app = builder.Build();
        app.UseRateLimiter();
        app.MapGet("/probe", () => "owned-test").RequireRateLimiting(policy);
        var cancellationToken = TestContext.Current.CancellationToken;
        await app.StartAsync(cancellationToken);
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()), Timeout = TimeSpan.FromSeconds(10) };
        using var first = await client.GetAsync("/probe", cancellationToken);
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        var results = await Task.WhenAll(Enumerable.Range(0, 32).Select(_ => client.GetAsync("/probe", cancellationToken)));
        foreach (var response in results)
        {
            using (response) Assert.Equal(bypass ? HttpStatusCode.OK : HttpStatusCode.TooManyRequests, response.StatusCode);
        }
        await app.StopAsync(cancellationToken);
    }

    private static IConfiguration TestConfig(string urls = "http://127.0.0.1:28081", string host = "127.0.0.1",
        string database = "pr13_tencent_live_0123456789abcdef", string session = "pr13-tencent-20261009") =>
        new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["urls"] = urls, ["ConnectionStrings:Postgres"] = $"Host={host};Database={database};Username=fixture",
            ["RequestLimits:OwnedTestBypass"] = "true", ["RequestLimits:OwnedTestSession"] = session
        }).Build();

    private sealed class TestEnvironment(string name) : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = name;
        public string ApplicationName { get; set; } = "OwnedTest";
        public string ContentRootPath { get; set; } = "";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
