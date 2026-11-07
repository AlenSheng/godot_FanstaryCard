using FantasyCard.Domain.Players;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Seasons;

public sealed record SeasonArchiveWork(Guid PlayerId,string SeasonId);
public sealed record SeasonArchivePage(Guid JobId,string Status,string Phase,Guid? Cursor,int ArchivedItems);

public sealed partial class SeasonRepository
{
    public async Task<IReadOnlyList<SeasonArchiveWork>> GetArchiveWorkAsync(int limit,CancellationToken ct)
    {
        if(limit is <1 or >100)throw new ArgumentOutOfRangeException(nameof(limit));
        await using var command=dataSource.CreateCommand("""
            SELECT s.player_id,s.season_id FROM player_season_state s
            JOIN season_definitions d USING(season_id)
            LEFT JOIN season_archive_jobs j ON j.player_id=s.player_id AND j.from_season_id=s.season_id
            WHERE d.ruleset_id='season-v1' AND d.ends_at <= $1
              AND (j.job_id IS NULL OR (j.status <> 'Completed' AND j.updated_at <= $1 - interval '5 seconds'))
            ORDER BY j.updated_at NULLS FIRST,s.season_id,s.player_id LIMIT $2
            """);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());command.Parameters.AddWithValue(limit);
        await using var reader=await command.ExecuteReaderAsync(ct);var result=new List<SeasonArchiveWork>();
        while(await reader.ReadAsync(ct))result.Add(new(reader.GetGuid(0),reader.GetString(1)));
        return result;
    }

    /// <summary>One account-first transaction commits at most one equipment page and its cursor.</summary>
    public async Task<SeasonArchivePage> AdvanceArchivePageAsync(Guid playerId,string seasonId,int pageSize,CancellationToken ct)
    {
        if(pageSize is <1 or >100)throw new ArgumentOutOfRangeException(nameof(pageSize));
        var now=timeProvider.GetUtcNow();
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,playerId,ct);
        await using(var eligible=new NpgsqlCommand("""
            SELECT 1 FROM player_season_state s JOIN season_definitions d USING(season_id)
            WHERE s.player_id=$1 AND s.season_id=$2 AND d.ruleset_id='season-v1' AND d.ends_at <= $3
            """,connection,transaction))
        {
            eligible.Parameters.AddWithValue(playerId);eligible.Parameters.AddWithValue(seasonId);eligible.Parameters.AddWithValue(now);
            if(await eligible.ExecuteScalarAsync(ct) is null)throw new DomainValidationException("Only an ended original season membership can be archived.");
        }
        await using(var insert=new NpgsqlCommand("""
            INSERT INTO season_archive_jobs(job_id,player_id,from_season_id,to_season_id,created_at,updated_at)
            SELECT $1,$2,$3,(SELECT n.season_id FROM season_definitions n,season_definitions old
                WHERE old.season_id=$3 AND n.ruleset_id='season-v1' AND n.starts_at >= old.ends_at
                  AND n.starts_at <= $4 ORDER BY n.starts_at LIMIT 1),$4,$4
            ON CONFLICT(player_id,from_season_id) DO NOTHING
            """,connection,transaction))
        {
            insert.Parameters.AddWithValue(Guid.CreateVersion7());insert.Parameters.AddWithValue(playerId);
            insert.Parameters.AddWithValue(seasonId);insert.Parameters.AddWithValue(now);await insert.ExecuteNonQueryAsync(ct);
        }
        Guid jobId;Guid? cursor;string status;
        await using(var query=new NpgsqlCommand("SELECT job_id,status,cursor_id FROM season_archive_jobs WHERE player_id=$1 AND from_season_id=$2 FOR UPDATE",connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(seasonId);await using var reader=await query.ExecuteReaderAsync(ct);
            if(!await reader.ReadAsync(ct))throw new InvalidOperationException("The archive job disappeared.");
            jobId=reader.GetGuid(0);status=reader.GetString(1);cursor=reader.IsDBNull(2)?null:reader.GetGuid(2);
        }
        if(status=="Completed")
        {
            await transaction.CommitAsync(ct);return new(jobId,status,"Completed",cursor,0);
        }
        // Reuse the same account-lock order and original return/hold policy as
        // normal preparation expiry and market maintenance. Never touch an actor.
        await PreparationRepository.ExpireStaleAsync(connection,transaction,playerId,now,ct);
        await EconomyRepository.ExpireSellerMarketListingsAsync(connection,transaction,playerId,now,ct);
        await SaveArchiveLoadoutsAsync(connection,transaction,playerId,seasonId,now,ct);
        await using(var mark=new NpgsqlCommand("""
            WITH archived_state AS (
                UPDATE player_season_state SET archived_at=$3,version=version+1
                    WHERE player_id=$1 AND season_id=$2 AND archived_at IS NULL RETURNING player_id)
            UPDATE player_season_wallets SET archived_at=$3,version=version+1
                WHERE player_id=$1 AND season_id=$2 AND archived_at IS NULL
            """,connection,transaction))
        {
            mark.Parameters.AddWithValue(playerId);mark.Parameters.AddWithValue(seasonId);mark.Parameters.AddWithValue(now);
            await mark.ExecuteNonQueryAsync(ct);
        }
        var items=new List<(Guid Id,string Location)>();
        await using(var query=new NpgsqlCommand("""
            SELECT instance_id,location FROM equipments WHERE owner_id=$1 AND season_id=$2
              AND asset_scope='ActiveSeason' AND location IN ('Inventory','Equipped','MarketReturnPending','EnhanceMaterialConsumed','Recycled')
              AND ($3::uuid IS NULL OR instance_id > $3) ORDER BY instance_id LIMIT $4 FOR UPDATE
            """,connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(seasonId);
            query.Parameters.AddWithValue(NpgsqlDbType.Uuid,(object?)cursor??DBNull.Value);query.Parameters.AddWithValue(pageSize);
            await using var reader=await query.ExecuteReaderAsync(ct);
            while(await reader.ReadAsync(ct))items.Add((reader.GetGuid(0),reader.GetString(1)));
        }
        foreach(var item in items)
        {
            var destination=item.Location is "Inventory" or "Equipped"?"SeasonArchive":item.Location;
            await using var archive=new NpgsqlCommand("""
                WITH archived AS (
                    UPDATE equipments SET asset_scope='ArchivedSeason',location=$6,version=version+1
                        WHERE instance_id=$3 RETURNING instance_id,generated_difficulty),
                recorded AS (
                    INSERT INTO season_archive_items(player_id,season_id,item_id,job_id,from_location,to_location,archived_at)
                        SELECT $1,$2,instance_id,$4,$5,$6,$7 FROM archived RETURNING item_id),
                moved AS (
                    INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,created_at,
                        season_id,source_kind,difficulty_id,ruleset_id,config_version,stats_version)
                    SELECT $8,$1,e.instance_id,$5,$6,'season.archive',$7,$2,'SeasonArchive','D'||e.generated_difficulty::text,
                        d.ruleset_id,d.config_version,d.stats_version FROM archived e CROSS JOIN season_definitions d
                        WHERE d.season_id=$2)
                UPDATE player_loadouts SET head_id=CASE WHEN head_id=$3 THEN NULL ELSE head_id END,
                    hands_id=CASE WHEN hands_id=$3 THEN NULL ELSE hands_id END,chest_id=CASE WHEN chest_id=$3 THEN NULL ELSE chest_id END,
                    legs_id=CASE WHEN legs_id=$3 THEN NULL ELSE legs_id END,feet_id=CASE WHEN feet_id=$3 THEN NULL ELSE feet_id END,
                    version=version+1 WHERE player_id=$1 AND $3 IN(head_id,hands_id,chest_id,legs_id,feet_id)
                        AND EXISTS(SELECT 1 FROM recorded)
                """,connection,transaction);
            archive.Parameters.AddWithValue(playerId);archive.Parameters.AddWithValue(seasonId);archive.Parameters.AddWithValue(item.Id);
            archive.Parameters.AddWithValue(jobId);archive.Parameters.AddWithValue(item.Location);archive.Parameters.AddWithValue(destination);
            archive.Parameters.AddWithValue(now);archive.Parameters.AddWithValue(Guid.CreateVersion7());await archive.ExecuteNonQueryAsync(ct);
        }
        bool remaining;bool blocked;
        await using(var pending=new NpgsqlCommand("""
            SELECT EXISTS(SELECT 1 FROM equipments WHERE owner_id=$1 AND season_id=$2 AND asset_scope='ActiveSeason'
                AND location IN('Inventory','Equipped','MarketReturnPending','EnhanceMaterialConsumed','Recycled')),
              EXISTS(SELECT 1 FROM equipments WHERE owner_id=$1 AND season_id=$2 AND asset_scope='ActiveSeason'
                AND location NOT IN('Inventory','Equipped','MarketReturnPending','EnhanceMaterialConsumed','Recycled'))
              OR EXISTS(SELECT 1 FROM match_players p JOIN matches m USING(match_id)
                WHERE p.player_id=$1 AND NOT p.is_bot AND m.season_id=$2 AND p.settled_at IS NULL)
              OR EXISTS(SELECT 1 FROM settlement_asset_holds WHERE player_id=$1 AND season_id=$2 AND state IN('Held','Pending'))
            """,connection,transaction))
        {
            pending.Parameters.AddWithValue(playerId);pending.Parameters.AddWithValue(seasonId);await using var reader=await pending.ExecuteReaderAsync(ct);
            await reader.ReadAsync(ct);remaining=reader.GetBoolean(0);blocked=reader.GetBoolean(1);
        }
        status=remaining?"Running":blocked?"WaitingAssets":"Completed";
        var phase=remaining?"EquipmentPaging":status;
        cursor=remaining&&items.Count>0?items[^1].Id:null;
        await using(var finish=new NpgsqlCommand("""
            UPDATE season_archive_jobs SET status=$3,phase=$4,cursor_id=$5,attempts=attempts+1,
                last_error_code=NULL,updated_at=$6,version=version+1 WHERE player_id=$1 AND from_season_id=$2
            """,connection,transaction))
        {
            finish.Parameters.AddWithValue(playerId);finish.Parameters.AddWithValue(seasonId);finish.Parameters.AddWithValue(status);
            finish.Parameters.AddWithValue(phase);finish.Parameters.AddWithValue(NpgsqlDbType.Uuid,(object?)cursor??DBNull.Value);
            finish.Parameters.AddWithValue(now);await finish.ExecuteNonQueryAsync(ct);
        }
        await transaction.CommitAsync(ct);return new(jobId,status,phase,cursor,items.Count);
    }

    private static async Task SaveArchiveLoadoutsAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid player,string season,DateTimeOffset now,CancellationToken ct)
    {
        await using var command=new NpgsqlCommand("""
            INSERT INTO season_archive_loadouts(player_id,season_id,hero_class,head_id,hands_id,chest_id,legs_id,feet_id,original_version,archived_at)
            SELECT l.player_id,$2,l.hero_class,h.instance_id,a.instance_id,c.instance_id,g.instance_id,f.instance_id,l.version,$3
            FROM player_loadouts l
            LEFT JOIN equipments h ON h.instance_id=l.head_id AND h.season_id=$2
            LEFT JOIN equipments a ON a.instance_id=l.hands_id AND a.season_id=$2
            LEFT JOIN equipments c ON c.instance_id=l.chest_id AND c.season_id=$2
            LEFT JOIN equipments g ON g.instance_id=l.legs_id AND g.season_id=$2
            LEFT JOIN equipments f ON f.instance_id=l.feet_id AND f.season_id=$2
            WHERE l.player_id=$1 AND coalesce(h.instance_id,a.instance_id,c.instance_id,g.instance_id,f.instance_id) IS NOT NULL
            ON CONFLICT(player_id,season_id,hero_class) DO NOTHING
            """,connection,transaction);
        command.Parameters.AddWithValue(player);command.Parameters.AddWithValue(season);command.Parameters.AddWithValue(now);
        await command.ExecuteNonQueryAsync(ct);
    }

    public async Task MarkArchiveFailureAsync(SeasonArchiveWork work,string errorCode,CancellationToken ct)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(errorCode);
        if(errorCode.Length>80)throw new ArgumentOutOfRangeException(nameof(errorCode));
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,work.PlayerId,ct);
        await using var command=new NpgsqlCommand("""
            INSERT INTO season_archive_jobs(job_id,player_id,from_season_id,status,attempts,last_error_code,created_at,updated_at)
            SELECT $5,$1,$2,'Failed',1,$3,$4,$4 FROM player_season_state s JOIN season_definitions d USING(season_id)
                WHERE s.player_id=$1 AND s.season_id=$2 AND d.ruleset_id='season-v1' AND d.ends_at <= $4
            ON CONFLICT(player_id,from_season_id) DO UPDATE
                SET status='Failed',attempts=season_archive_jobs.attempts+1,last_error_code=$3,updated_at=$4,version=season_archive_jobs.version+1
                WHERE season_archive_jobs.status <> 'Completed'
            """,connection,transaction);
        command.Parameters.AddWithValue(work.PlayerId);command.Parameters.AddWithValue(work.SeasonId);
        command.Parameters.AddWithValue(errorCode);command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        command.Parameters.AddWithValue(Guid.CreateVersion7());
        await command.ExecuteNonQueryAsync(ct);await transaction.CommitAsync(ct);
    }
}
