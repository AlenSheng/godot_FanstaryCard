using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using FantasyCard.Server.Common;
using Npgsql;

namespace FantasyCard.Server.Persistence;

public sealed partial class DatabaseMigrator(
    NpgsqlDataSource dataSource,
    ILogger<DatabaseMigrator> logger,
    ServerMetrics? metrics = null) : IHostedService
{
    private const long MigrationLockKey = 4_662_110_845_612_103_801;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var startedAt = Stopwatch.GetTimestamp();
        const int maximumAttempts = 15;
        for (var attempt = 1; attempt <= maximumAttempts; attempt++)
        {
            try
            {
                await MigrateAsync(cancellationToken);
                metrics?.DatabaseMigrationFinished(Stopwatch.GetElapsedTime(startedAt), succeeded: true);
                return;
            }
            catch (Exception exception) when (attempt < maximumAttempts && !cancellationToken.IsCancellationRequested)
            {
                metrics?.DatabaseMigrationAttemptFailed();
                LogMigrationAttemptFailed(logger, attempt, maximumAttempts, exception);
                await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);
            }
            catch
            {
                metrics?.DatabaseMigrationFinished(Stopwatch.GetElapsedTime(startedAt), succeeded: false);
                throw;
            }
        }

        throw new InvalidOperationException("PostgreSQL migrations did not complete in time.");
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    private async Task MigrateAsync(CancellationToken cancellationToken)
    {
        var migrations = LoadMigrations();
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var lockCommand = new NpgsqlCommand("SELECT pg_advisory_lock($1)", connection);
        lockCommand.Parameters.AddWithValue(MigrationLockKey);
        await lockCommand.ExecuteNonQueryAsync(cancellationToken);

        try
        {
            await EnsureMigrationTableAsync(connection, cancellationToken);
            var applied = await LoadAppliedMigrationsAsync(connection, cancellationToken);

            foreach (var migration in migrations)
            {
                if (applied.TryGetValue(migration.Version, out var checksum))
                {
                    if (!MigrationChecksum.Matches(migration.Sql, checksum))
                    {
                        throw new InvalidOperationException(
                            $"Migration V{migration.Version:D3} checksum changed after it was applied.");
                    }

                    continue;
                }

                await ApplyMigrationAsync(connection, migration, cancellationToken);
                metrics?.DatabaseMigrationApplied();
                LogMigrationApplied(logger, migration.Version, migration.Name);
            }

            metrics?.ObserveDatabaseSchemaVersion(migrations[^1].Version);
            LogSchemaCurrent(logger, migrations[^1].Version);
        }
        finally
        {
            await using var unlockCommand = new NpgsqlCommand("SELECT pg_advisory_unlock($1)", connection);
            unlockCommand.Parameters.AddWithValue(MigrationLockKey);
            await unlockCommand.ExecuteNonQueryAsync(CancellationToken.None);
        }
    }

    private static async Task EnsureMigrationTableAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version integer PRIMARY KEY CHECK (version > 0),
                name varchar(160) NOT NULL,
                checksum varchar(64) NOT NULL,
                applied_at timestamptz NOT NULL
            )
            """,
            connection);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task<Dictionary<int, string>> LoadAppliedMigrationsAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "SELECT version, checksum FROM schema_migrations ORDER BY version",
            connection);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new Dictionary<int, string>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(reader.GetInt32(0), reader.GetString(1));
        }

        return result;
    }

    private static async Task ApplyMigrationAsync(
        NpgsqlConnection connection,
        Migration migration,
        CancellationToken cancellationToken)
    {
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var migrationCommand = new NpgsqlCommand(migration.Sql, connection, transaction))
        {
            await migrationCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await using (var recordCommand = new NpgsqlCommand(
            """
            INSERT INTO schema_migrations(version, name, checksum, applied_at)
            VALUES ($1, $2, $3, $4)
            """,
            connection,
            transaction))
        {
            recordCommand.Parameters.AddWithValue(migration.Version);
            recordCommand.Parameters.AddWithValue(migration.Name);
            recordCommand.Parameters.AddWithValue(migration.Checksum);
            recordCommand.Parameters.AddWithValue(DateTimeOffset.UtcNow);
            await recordCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    private static List<Migration> LoadMigrations()
    {
        var assembly = typeof(DatabaseMigrator).Assembly;
        var migrations = new List<Migration>();

        foreach (var resourceName in assembly.GetManifestResourceNames())
        {
            var match = MigrationResourcePattern().Match(resourceName);
            if (!match.Success)
            {
                continue;
            }

            using var stream = assembly.GetManifestResourceStream(resourceName)
                ?? throw new InvalidOperationException($"Embedded migration '{resourceName}' cannot be read.");
            using var reader = new StreamReader(stream, Encoding.UTF8);
            var sql = reader.ReadToEnd();
            var checksum = MigrationChecksum.Calculate(sql);
            migrations.Add(new Migration(
                int.Parse(match.Groups["version"].Value, System.Globalization.CultureInfo.InvariantCulture),
                match.Groups["name"].Value,
                checksum,
                sql));
        }

        migrations.Sort((left, right) => left.Version.CompareTo(right.Version));
        if (migrations.Count == 0)
        {
            throw new InvalidOperationException("No embedded database migrations were found.");
        }

        if (migrations.Select(migration => migration.Version).Distinct().Count() != migrations.Count)
        {
            throw new InvalidOperationException("Database migration versions must be unique.");
        }

        return migrations;
    }

    [GeneratedRegex(@"\.V(?<version>\d+)__(?<name>[^.]+)\.sql$", RegexOptions.CultureInvariant)]
    private static partial Regex MigrationResourcePattern();

    [LoggerMessage(
        EventId = 1001,
        Level = LogLevel.Warning,
        Message = "PostgreSQL migration attempt {Attempt}/{MaximumAttempts} failed")]
    private static partial void LogMigrationAttemptFailed(
        ILogger logger,
        int attempt,
        int maximumAttempts,
        Exception exception);

    [LoggerMessage(
        EventId = 1002,
        Level = LogLevel.Information,
        Message = "Applied database migration V{Version:D3} {Name}")]
    private static partial void LogMigrationApplied(ILogger logger, int version, string name);

    [LoggerMessage(
        EventId = 1003,
        Level = LogLevel.Information,
        Message = "PostgreSQL schema is current at V{Version:D3}")]
    private static partial void LogSchemaCurrent(ILogger logger, int version);

    private sealed record Migration(int Version, string Name, string Checksum, string Sql);
}
