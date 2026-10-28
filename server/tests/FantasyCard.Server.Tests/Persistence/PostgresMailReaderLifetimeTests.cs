using FantasyCard.Server.Mail;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresMailReaderLifetimeTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Disposed_reader_alias_can_close_a_subsequent_pool_borrowers_reader()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        await using var source = SingleConnectionSource(database.ConnectionString);
        var ct = TestContext.Current.CancellationToken;
        await using var first = source.CreateCommand("SELECT 1");
        var oldReader = await first.ExecuteReaderAsync(ct);
        await oldReader.DisposeAsync();
        await using var second = source.CreateCommand("SELECT 2");
        await using var currentReader = await second.ExecuteReaderAsync(ct);
        // Npgsql caches one reader per physical connector. This is the old Mail
        // premature disposal followed by the compiler-generated scope disposal.
        Assert.Same(oldReader, currentReader);
        await oldReader.DisposeAsync();
        Assert.True(currentReader.IsClosed);
        await Assert.ThrowsAsync<ObjectDisposedException>(() => currentReader.ReadAsync(ct));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_mail_reads_complete_with_a_single_pooled_connection()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        await using var source = SingleConnectionSource(database.ConnectionString);
        var repository = new MailRepository(source, TimeProvider.System);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        var results = await Task.WhenAll(Enumerable.Range(0, 8).Select(async _ =>
        {
            for (var i = 0; i < 10; i++)
            {
                var result = await repository.GetAsync(Guid.NewGuid(), deadline.Token);
                Assert.Empty(result.Items);
                Assert.Equal(0, result.UnreadCount);
            }
            return true;
        }));
        Assert.Equal(8, results.Length);
    }

    private static NpgsqlDataSource SingleConnectionSource(string connectionString) =>
        NpgsqlDataSource.Create(new NpgsqlConnectionStringBuilder(connectionString)
        {
            Pooling = true, MaxPoolSize = 1, MinPoolSize = 0, Timeout = 5, CommandTimeout = 5
        }.ConnectionString);
}
