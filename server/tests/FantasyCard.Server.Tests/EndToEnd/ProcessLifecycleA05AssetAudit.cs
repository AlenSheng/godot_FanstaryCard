using System.Text.Json;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private const string A05AuditSql = """
        WITH chain AS (
            SELECT *,lag(balance_after) OVER(PARTITION BY player_id,currency ORDER BY created_at,ledger_id) previous
            FROM economy_ledger WHERE currency <> 'ClassSoul'
        )
        SELECT jsonb_build_object(
            'checked_at',CURRENT_TIMESTAMP,
            'wallets',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM player_wallets t),'[]'::jsonb),
            'consumables',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM player_consumables t),'[]'::jsonb),
            'equipment',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM equipments t),'[]'::jsonb),
            'movements',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM inventory_movements t),'[]'::jsonb),
            'ledger',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM economy_ledger t),'[]'::jsonb),
            'settlements',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM match_settlements t),'[]'::jsonb),
            'holds',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM settlement_asset_holds t),'[]'::jsonb),
            'preparations',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM preparations t),'[]'::jsonb),
            'matches',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM matches t),'[]'::jsonb),
            'match_players',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM match_players t),'[]'::jsonb),
            'ledger_chain_mismatches',(SELECT count(*) FROM chain WHERE previous IS NOT NULL AND previous+delta<>balance_after),
            'wallet_gold_mismatches',(SELECT count(*) FROM player_wallets w WHERE EXISTS(SELECT 1 FROM economy_ledger e WHERE e.player_id=w.player_id AND e.currency='Gold') AND
                w.gold<>(SELECT e.balance_after FROM economy_ledger e WHERE e.player_id=w.player_id AND e.currency='Gold' ORDER BY e.created_at DESC,e.ledger_id DESC LIMIT 1)),
            'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),
            'active_preparations',(SELECT count(*) FROM preparations WHERE status IN ('Active','Queued','Matched')),
            'queued_tickets',(SELECT count(*) FROM match_tickets WHERE status='Queued'),
            'unacknowledged_settlements',(SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NULL),
            'unfinished_matches',(SELECT count(*) FROM matches WHERE status IN ('Starting','Launching','Running')),
            'locked_equipment',(SELECT count(*) FROM equipments WHERE location IN ('PreparationLocked','InMatchEquipped','InMatchBackpack'))
        )::text
        """;
    private static readonly string[] A05ClearAuditFields = ["ledger_chain_mismatches", "wallet_gold_mismatches", "pending_holds", "active_preparations",
        "queued_tickets", "unacknowledged_settlements", "unfinished_matches", "locked_equipment"];

    private static async Task A05AuditAsync(PostgresTestSchema database, string label, bool requireClear, CancellationToken ct)
    {
        await using var connection = await database.DataSource.OpenConnectionAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(ct);
        await using (var readOnly = new NpgsqlCommand("SET TRANSACTION READ ONLY; SET LOCAL statement_timeout='5s'", connection, transaction))
            await readOnly.ExecuteNonQueryAsync(ct);
        string raw;
        await using (var command = new NpgsqlCommand(A05AuditSql, connection, transaction))
            raw = (string)(await command.ExecuteScalarAsync(ct))!;
        await transaction.RollbackAsync(ct);
        Directory.CreateDirectory(EvidenceDirectory);
        var queryPath = Path.Combine(EvidenceDirectory, "a05-owned-readonly-audit.sql");
        await File.WriteAllTextAsync(queryPath, "BEGIN READ ONLY;\nSET LOCAL statement_timeout='5s';\n" + A05AuditSql + ";\nROLLBACK;\n", ct);
        var path = Path.Combine(EvidenceDirectory, "a05-audit-" + label + ".json");
        using var result = JsonDocument.Parse(raw);
        await File.WriteAllTextAsync(path, JsonSerializer.Serialize(new { label, requireClear, scope = new NpgsqlConnectionStringBuilder(database.ConnectionString).SearchPath,
            querySha256 = A05Sha(await File.ReadAllBytesAsync(queryPath, ct)), transaction = "READ ONLY; rollback; no mutation", result = result.RootElement.Clone() }), ct);
        if (requireClear)
            foreach (var field in A05ClearAuditFields) Assert.Equal(0L, result.RootElement.GetProperty(field).GetInt64());
        Record("A05-readonly-audit", new { label, requireClear, path, querySha256 = A05Sha(await File.ReadAllBytesAsync(queryPath, ct)),
            resultSha256 = A05Sha(await File.ReadAllBytesAsync(path, ct)), actual = "owned schema queries ran in READ ONLY transaction and rolled back" });
    }
}
