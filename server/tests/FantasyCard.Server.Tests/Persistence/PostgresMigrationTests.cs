using FantasyCard.Server.Persistence;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresMigrationTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(
        Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_migration_restart_and_checksum_rejection()
    {
        var connectionString = Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")!;
        var cancellationToken = TestContext.Current.CancellationToken;
        // Generated internally; never use a supplied schema name for cleanup.
        var schema = "fc_migration_test_" + Guid.NewGuid().ToString("N");
        await using var admin = NpgsqlDataSource.Create(connectionString);
        await using (var create = admin.CreateCommand($"CREATE SCHEMA {schema}"))
            await create.ExecuteNonQueryAsync(cancellationToken);
        try
        {
            var settings = new NpgsqlConnectionStringBuilder(connectionString) { SearchPath = schema };
            await using var isolated = NpgsqlDataSource.Create(settings.ConnectionString);
            var first = new DatabaseMigrator(isolated, NullLogger<DatabaseMigrator>.Instance);
            var second = new DatabaseMigrator(isolated, NullLogger<DatabaseMigrator>.Instance);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(60));
            await Task.WhenAll(first.StartAsync(timeout.Token), second.StartAsync(timeout.Token));

            var migrationCount = typeof(DatabaseMigrator).Assembly.GetManifestResourceNames()
                .Count(name => name.Contains(".Migrations.V", StringComparison.Ordinal) && name.EndsWith(".sql", StringComparison.Ordinal));
            await using (var count = isolated.CreateCommand("SELECT count(*) FROM schema_migrations"))
                Assert.Equal((long)migrationCount, await count.ExecuteScalarAsync(timeout.Token));
            var before = await ReadMigrationRecordsAsync(isolated);
            await first.StartAsync(timeout.Token);
            Assert.Equal(before, await ReadMigrationRecordsAsync(isolated));

            await using (var tamper = isolated.CreateCommand("UPDATE schema_migrations SET checksum=repeat('0',64) WHERE version=1"))
                Assert.Equal(1, await tamper.ExecuteNonQueryAsync(timeout.Token));
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => first.StartAsync(timeout.Token));
            Assert.Contains("checksum changed", exception.Message, StringComparison.Ordinal);
            await using var unchanged = isolated.CreateCommand("SELECT checksum FROM schema_migrations WHERE version=1");
            Assert.Equal(new string('0', 64), await unchanged.ExecuteScalarAsync(timeout.Token));
        }
        finally
        {
            await using var cleanup = admin.CreateCommand($"DROP SCHEMA {schema} CASCADE");
            using var cleanupTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            await cleanup.ExecuteNonQueryAsync(cleanupTimeout.Token);
        }
    }

    private static async Task<string> ReadMigrationRecordsAsync(NpgsqlDataSource source)
    {
        await using var command = source.CreateCommand(
            "SELECT jsonb_agg(to_jsonb(m) ORDER BY version)::text FROM schema_migrations m");
        return (string)(await command.ExecuteScalarAsync(TestContext.Current.CancellationToken))!;
    }
}
