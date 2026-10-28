using FantasyCard.Server.Persistence;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresOwnedPoolReuseTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(false, 8)]
    [InlineData(true, 1)]
    [Trait("Category", "PostgresIntegration")]
    public async Task Owned_profile_reuses_actual_backend_only_when_explicitly_enabled(bool reuse, int expectedBackends)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        await using var provider = Services(database.ConnectionString, reuse).BuildServiceProvider();
        var source = provider.GetRequiredService<NpgsqlDataSource>();
        var backends = new HashSet<int>();
        for (var index = 0; index < 8; index++)
        {
            await using var connection = await source.OpenConnectionAsync(TestContext.Current.CancellationToken);
            await using var command = new NpgsqlCommand("SELECT pg_backend_pid()", connection);
            backends.Add((int)(await command.ExecuteScalarAsync(TestContext.Current.CancellationToken))!);
        }
        Assert.Equal(expectedBackends, backends.Count);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Owned_reuse_profile_can_hold_more_than_the_original_16_connections()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        await using var provider = Services(database.ConnectionString, reuse: true).BuildServiceProvider();
        var source = provider.GetRequiredService<NpgsqlDataSource>();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        var leases = Enumerable.Range(0, 17).Select(_ => source.OpenConnectionAsync(timeout.Token).AsTask()).ToArray();
        try
        {
            var connections = await Task.WhenAll(leases);
            Assert.Equal(17, connections.Select(connection => connection.ProcessID).Distinct().Count());
        }
        finally
        {
            foreach (var lease in leases)
                if (lease.IsCompletedSuccessfully) await (await lease).DisposeAsync();
        }
    }

    private static IServiceCollection Services(string connectionString, bool reuse)
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ConnectionStrings:Postgres"] = connectionString,
            ["RequestLimits:OwnedTestBypass"] = "true",
            ["Persistence:OwnedTestPoolReuse"] = reuse.ToString()
        }).Build();
        return new ServiceCollection().AddFantasyCardPersistence(config);
    }
}
