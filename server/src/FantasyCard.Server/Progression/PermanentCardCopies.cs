using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using Npgsql;

namespace FantasyCard.Server.Progression;

internal sealed record PermanentCardGrant(string CardId,int Quantity,bool NewlyUnlocked,int CopiesAfter,long Version);

/// <summary>
/// Transaction helpers for the season shop's permanent copies. Callers own the
/// player lock and durable action receipt; no helper commits or opens a second connection.
/// </summary>
internal static class PermanentCardCopies
{
    internal static async Task EnsurePublishedPolicyAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,DateTimeOffset now,CancellationToken ct)
    {
        if(await IsEnabledAsync(connection,transaction,playerId,ct))return;
        var config=GameConfigCatalog.Current;
        if(config.SeasonShop is not null)
        {
            // Also recognize a definition installed by the deployment operator,
            // but only when its version AND hash match this compiled bundle.
            await using var adopt=new NpgsqlCommand("UPDATE season_definitions SET permanent_card_rule=$1 WHERE permanent_card_rule IS NULL AND config_version=$2 AND config_sha256=$3 AND starts_at<=$4",connection,transaction);
            adopt.Parameters.AddWithValue(SeasonShopConfig.Version);adopt.Parameters.AddWithValue(config.Version);
            adopt.Parameters.AddWithValue(config.ContentHash);adopt.Parameters.AddWithValue(now);await adopt.ExecuteNonQueryAsync(ct);
        }
        // Adoption survives the end of its first season and later shop closures.
        // No archive lookup or seasonal balance is needed for permanent assets.
        await using var q=new NpgsqlCommand("SELECT config_version FROM season_definitions WHERE permanent_card_rule=$1 AND starts_at<=$2 ORDER BY starts_at DESC LIMIT 1",connection,transaction);
        q.Parameters.AddWithValue(SeasonShopConfig.Version);q.Parameters.AddWithValue(now);
        if(await q.ExecuteScalarAsync(ct) is string version)
            await EnableWithinTransactionAsync(connection,transaction,playerId,version,now,ct);
    }

    // Only a validated, published new-season shop policy may call this method.
    // The first activation is permanent and retains its original config provenance.
    internal static async Task EnableWithinTransactionAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,string configVersion,DateTimeOffset now,CancellationToken ct)
    {
        if(string.IsNullOrWhiteSpace(configVersion) || configVersion.Length>80)
            throw new DomainValidationException("The permanent card policy configuration is invalid.");
        await using var command=new NpgsqlCommand("""
            INSERT INTO player_card_copy_modes(player_id,enabled_by_config,enabled_at) VALUES($1,$2,$3)
            ON CONFLICT(player_id) DO NOTHING
            """,connection,transaction);
        command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(configVersion);command.Parameters.AddWithValue(now);
        await command.ExecuteNonQueryAsync(ct);
    }

    internal static async Task<bool> IsEnabledAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,Guid playerId,CancellationToken ct)
    {
        await using var command=new NpgsqlCommand("SELECT EXISTS(SELECT 1 FROM player_card_copy_modes WHERE player_id=$1)",connection,transaction);
        command.Parameters.AddWithValue(playerId);return (bool)(await command.ExecuteScalarAsync(ct))!;
    }

    internal static async Task SaveReserveAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,string cardId,int copiesAfter,CancellationToken ct)
    {
        if(copiesAfter<0)throw new DomainValidationException("Permanent card copies cannot be negative.");
        await using var command=new NpgsqlCommand("""
            INSERT INTO player_card_reserves(player_id,card_id,extra_count) VALUES($1,$2,$3)
            ON CONFLICT(player_id,card_id) DO UPDATE SET extra_count=EXCLUDED.extra_count
            """,connection,transaction);
        command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(cardId);command.Parameters.AddWithValue(Math.Max(0,copiesAfter-1));
        await command.ExecuteNonQueryAsync(ct);
    }

    internal static async Task WriteLedgerAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid playerId,
        string cardId,int delta,int balanceAfter,string reason,string requestId,DateTimeOffset now,CancellationToken ct)
    {
        if(delta==0)return;
        await using var command=new NpgsqlCommand("""
            INSERT INTO card_copy_ledger(movement_id,player_id,card_id,delta,balance_after,reason,request_id,created_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            """,connection,transaction);
        command.Parameters.AddWithValue(Guid.CreateVersion7());command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(cardId);
        command.Parameters.AddWithValue(delta);command.Parameters.AddWithValue(balanceAfter);command.Parameters.AddWithValue(reason);
        command.Parameters.AddWithValue(requestId);command.Parameters.AddWithValue(now);await command.ExecuteNonQueryAsync(ct);
    }

    /// <summary>Grant grouped copies, including already owned and repeated pack draws, in the caller's transaction.</summary>
    internal static async Task<PermanentCardGrant> GrantWithinTransactionAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,CardConfigDefinition definition,int quantity,string reason,string requestId,DateTimeOffset now,CancellationToken ct)
    {
        if(quantity<1 || !definition.Enabled || !definition.IsCodex)
            throw new DomainValidationException("The permanent card grant is invalid.");
        return await GrantStoredWithinTransactionAsync(connection,transaction,playerId,definition.CardId,
            quantity,reason,requestId,now,ct);
    }

    /// <summary>
    /// Credit an existing player-card identity from a durable legacy grant.
    /// Unversioned mail must not be reinterpreted against a current season's catalog.
    /// The caller owns the player lock and the original mail's one-time receipt.
    /// </summary>
    internal static async Task<PermanentCardGrant> GrantStoredWithinTransactionAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,string cardId,int quantity,string reason,string requestId,DateTimeOffset now,CancellationToken ct)
    {
        if(quantity<1 || string.IsNullOrWhiteSpace(cardId))
            throw new DomainValidationException("The permanent card grant is invalid.");
        if(!await IsEnabledAsync(connection,transaction,playerId,ct))
            throw new DomainValidationException("Permanent card copies have not been enabled for this account.");
        int before;long version;
        await using(var query=new NpgsqlCommand("""
            SELECT c.copy_count+COALESCE(r.extra_count,0),c.version FROM player_cards c
            LEFT JOIN player_card_reserves r USING(player_id,card_id)
            WHERE c.player_id=$1 AND c.card_id=$2 FOR UPDATE OF c
            """,connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(cardId);
            await using var reader=await query.ExecuteReaderAsync(ct);
            if(!await reader.ReadAsync(ct))throw new DomainValidationException("The player card aggregate is missing the granted card.");
            before=reader.GetInt32(0);version=reader.GetInt64(1);
        }
        var after=checked(before+quantity);
        await using(var command=new NpgsqlCommand("""
            UPDATE player_cards SET unlocked=true,copy_count=1,version=version+1
            WHERE player_id=$1 AND card_id=$2
            """,connection,transaction))
        {
            command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(cardId);await command.ExecuteNonQueryAsync(ct);
        }
        await SaveReserveAsync(connection,transaction,playerId,cardId,after,ct);
        await WriteLedgerAsync(connection,transaction,playerId,cardId,quantity,after,reason,requestId,now,ct);
        return new(cardId,quantity,before==0,after,version+1);
    }
}
