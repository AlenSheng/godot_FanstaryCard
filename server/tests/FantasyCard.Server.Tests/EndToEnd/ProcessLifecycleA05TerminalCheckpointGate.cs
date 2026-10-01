using System.Globalization;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    // Test-only scheduling gate in this test's disposable schema. It changes no
    // snapshot, receipt, response, asset value, or production code.
    private sealed class A05TerminalCheckpointGate(
        PostgresTestSchema database, NpgsqlConnection connection, int key, string label) : IAsyncDisposable
    {
        private bool _released;

        public static async Task<A05TerminalCheckpointGate> CreateAsync(
            PostgresTestSchema database, Guid playerId, string label, CancellationToken ct)
        {
            var schema = new NpgsqlConnectionStringBuilder(database.ConnectionString).SearchPath;
            Assert.StartsWith("fc_runtime_test_", schema);
            var key = Random.Shared.Next(1, int.MaxValue);
            var connection = await database.DataSource.OpenConnectionAsync(ct);
            var result = new A05TerminalCheckpointGate(database, connection, key, label);
            try
            {
                await using (var command = new NpgsqlCommand("SELECT pg_advisory_lock($1::bigint)", connection))
                { command.Parameters.AddWithValue(key); await command.ExecuteNonQueryAsync(ct); }
                // Only generated numeric/UUID literals enter this function body.
                var lockLiteral = key.ToString(CultureInfo.InvariantCulture);
                await SqlAsync(database, $$"""
                    CREATE FUNCTION hold_a05_terminal_checkpoint() RETURNS trigger LANGUAGE plpgsql AS $gate$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM jsonb_array_elements(NEW.snapshot_json->'players') AS player
                            WHERE player->>'playerId' = '{{playerId:D}}' AND player->>'phase' = 'Extracted'
                        ) THEN
                            PERFORM pg_advisory_xact_lock({{lockLiteral}}::bigint);
                        END IF;
                        RETURN NEW;
                    END $gate$;
                    CREATE TRIGGER gate_a05_terminal_checkpoint BEFORE INSERT OR UPDATE ON room_snapshots
                        FOR EACH ROW EXECUTE FUNCTION hold_a05_terminal_checkpoint();
                    """, ct);
                Record("A05-ordinary-checkpoint-gate-installed", new { label, schema, key, playerId });
                return result;
            }
            catch
            {
                await result.DisposeAsync();
                throw;
            }
        }

        public async Task WaitUntilBlockedAsync(CancellationToken ct)
        {
            await WaitAsync(async () =>
            {
                await using var command = database.DataSource.CreateCommand(
                    "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=0 AND objid=$1::oid AND objsubid=1 AND NOT granted");
                command.Parameters.AddWithValue(key);
                return (long)(await command.ExecuteScalarAsync(ct))! == 1;
            }, ct);
            Record("A05-ordinary-terminal-checkpoint-blocked", new { label, key });
        }

        public async Task ReleaseAsync()
        {
            if (_released) return;
            await using var command = new NpgsqlCommand("SELECT pg_advisory_unlock($1::bigint)", connection);
            command.Parameters.AddWithValue(key);
            Assert.True((bool)(await command.ExecuteScalarAsync(CancellationToken.None))!);
            _released = true;
            Record("A05-ordinary-terminal-checkpoint-released", new { label, key });
        }

        public async ValueTask DisposeAsync()
        {
            try { await ReleaseAsync(); }
            finally { await connection.DisposeAsync(); }
            // PostgresTestSchema drops this schema, including its trigger and
            // function, after the owned host and client have been disposed.
        }
    }
}
