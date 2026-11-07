using System.Data;
using System.Text.Json;
using FantasyCard.Server.Persistence;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

static string Quote(string text) => "\"" + text.Replace("\"", "\"\"") + "\"";

static async Task<Dictionary<string, TablePin>> Snapshot(NpgsqlDataSource source, Dictionary<string, TablePin>? projection = null)
{
    await using var connection = await source.OpenConnectionAsync();
    await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead);
    await using (var setup = new NpgsqlCommand("SET TRANSACTION READ ONLY; SET LOCAL TIME ZONE 'UTC'; SET LOCAL work_mem='16MB'", connection, transaction))
        await setup.ExecuteNonQueryAsync();
    var columns = new Dictionary<string, string[]>(StringComparer.Ordinal);
    if (projection is null)
    {
        await using var tables = new NpgsqlCommand("""
            SELECT c.table_name,array_agg(c.column_name::text ORDER BY c.ordinal_position)
            FROM information_schema.columns c JOIN information_schema.tables t USING(table_schema,table_name)
            WHERE c.table_schema='public' AND t.table_type='BASE TABLE' AND c.table_name<>'schema_migrations'
            GROUP BY c.table_name ORDER BY c.table_name
            """, connection, transaction);
        await using var reader = await tables.ExecuteReaderAsync();
        while (await reader.ReadAsync()) columns.Add(reader.GetString(0), reader.GetFieldValue<string[]>(1));
    }
    else
    {
        foreach (var (name, pin) in projection) columns.Add(name, pin.Columns);
    }
    var result = new Dictionary<string, TablePin>(StringComparer.Ordinal);
    foreach (var (name, names) in columns)
    {
        var sql = "SELECT count(*)::bigint,md5(coalesce(string_agg(x::text,E'\\n' ORDER BY x::text),'')) FROM (SELECT to_jsonb(t) x FROM (SELECT " +
            string.Join(",", names.Select(Quote)) + " FROM public." + Quote(name) + ")t)q";
        await using var command = new NpgsqlCommand(sql, connection, transaction) { CommandTimeout = 90 };
        await using var reader = await command.ExecuteReaderAsync();
        await reader.ReadAsync();
        result.Add(name, new(names, reader.GetInt64(0), reader.GetString(1)));
    }
    await transaction.CommitAsync();
    return result;
}

static async Task<MigrationPin> Migrations(NpgsqlDataSource source)
{
    await using var query = source.CreateCommand("""
        SELECT count(*)::int,max(version),md5(jsonb_agg(to_jsonb(m) ORDER BY version)::text)
        FROM schema_migrations m
        """);
    await using var reader = await query.ExecuteReaderAsync();
    await reader.ReadAsync();
    return new(reader.GetInt32(0), reader.GetInt32(1), reader.GetString(2));
}

var output = Environment.GetEnvironmentVariable("F03_REHEARSAL_RESULT") ?? throw new InvalidOperationException("Owned result path required.");
try
{
    var raw = Environment.GetEnvironmentVariable("F03_REHEARSAL_DSN") ?? throw new InvalidOperationException("Owned clone required.");
    var settings = new NpgsqlConnectionStringBuilder(raw);
    if (settings.Host != "127.0.0.1" || settings.Database is null || !settings.Database.StartsWith("fc_f03_", StringComparison.Ordinal)
        || settings.Username != "f03_owner" || settings.ApplicationName is null || !settings.ApplicationName.StartsWith("fc-f03-rehearsal-", StringComparison.Ordinal))
        throw new InvalidOperationException("Only the separately owned network-isolated clone is permitted.");
    settings.IncludeErrorDetail = false;
    await using var source = NpgsqlDataSource.Create(settings.ConnectionString);
    var beforeMigrations = await Migrations(source);
    if (beforeMigrations.Count != 27 || beforeMigrations.Maximum != 30)
        throw new InvalidOperationException("Backup migration identity differs from observed production baseline.");
    var before = await Snapshot(source);
    var migrator = new DatabaseMigrator(source, NullLogger<DatabaseMigrator>.Instance);
    await migrator.StartAsync(CancellationToken.None);
    var firstMigrations = await Migrations(source);
    if (firstMigrations.Count != 52 || firstMigrations.Maximum != 55)
        throw new InvalidOperationException("Current embedded migration set did not complete.");
    var afterLegacy = await Snapshot(source, before);
    var differences = before.Where(pair => pair.Value.Rows != afterLegacy[pair.Key].Rows || pair.Value.Hash != afterLegacy[pair.Key].Hash)
        .Select(pair => new { table = pair.Key, before = pair.Value, after = afterLegacy[pair.Key] }).ToArray();
    var afterAll = await Snapshot(source);
    await migrator.StartAsync(CancellationToken.None);
    var replay = await Snapshot(source);
    var replayMigrations = await Migrations(source);
    var replayStable = JsonSerializer.Serialize(afterAll) == JsonSerializer.Serialize(replay) && firstMigrations == replayMigrations;
    var ok = differences.Length == 0 && replayStable;
    File.WriteAllText(output, JsonSerializer.Serialize(new
    {
        ok,
        scope = "Private production backup restored into an owned PostgreSQL clone; migration only, no server host, gameplay or external network.",
        beforeMigrations,
        firstMigrations,
        replayMigrations,
        legacy_tables = before,
        legacy_projection_after = afterLegacy,
        differences,
        current_table_count = afterAll.Count,
        replayStable,
        backup_contains_private_data = true,
        public_report_contains_hashes_counts_and_schema_only = true,
        production_migration_performed = false,
        new_gameplay_cases = 0,
        final_protected_release_artifact_validated = false
    }, new JsonSerializerOptions { WriteIndented = true }));
    Console.WriteLine(JsonSerializer.Serialize(new { ok, old_tables = before.Count, migrated_to = firstMigrations.Maximum, differences = differences.Length, replayStable }));
    return ok ? 0 : 1;
}
catch (Exception exception)
{
    File.WriteAllText(output, JsonSerializer.Serialize(new
    {
        ok = false,
        error_type = exception.GetType().FullName,
        sql_state = (exception as PostgresException)?.SqlState,
        table = (exception as PostgresException)?.TableName,
        constraint = (exception as PostgresException)?.ConstraintName,
        exception_details_with_data_omitted = true,
        production_migration_performed = false,
        new_gameplay_cases = 0
    }));
    Console.Error.WriteLine("Owned rehearsal failed: " + exception.GetType().Name);
    return 2;
}

sealed record TablePin(string[] Columns, long Rows, string Hash);
sealed record MigrationPin(int Count, int Maximum, string Hash);
