using System.Data;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Seasons;
using FantasyCard.Domain.Players;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    private const string ArchiveSummarySql = """
        SELECT d.season_id,d.ruleset_id,d.config_version,d.config_sha256,d.stats_version,d.starts_at,d.ends_at,s.archived_at,
            CASE WHEN d.ruleset_id='legacy' THEN 'Legacy' ELSE COALESCE(j.status,'Pending') END,j.phase,
            w.gold,w.equipment_fragments,w.challenge_marks,w.version,w.archived_at,w.blueprint_marks,w.orange_blueprint_marks,
            (SELECT count(*) FROM equipments e WHERE e.owner_id=s.player_id AND e.season_id=s.season_id AND e.asset_scope IN ('ActiveSeason','ArchivedSeason')),
            (SELECT count(*) FROM learned_season_recipes r WHERE r.player_id=s.player_id AND r.season_id=s.season_id),
            (SELECT count(*) FROM player_crafting_wishes p WHERE p.player_id=s.player_id AND p.season_id=s.season_id),
            (SELECT count(*) FROM season_archive_loadouts l WHERE l.player_id=s.player_id AND l.season_id=s.season_id)
        FROM player_season_state s JOIN season_definitions d ON d.season_id=s.season_id
        LEFT JOIN player_season_wallets w ON w.player_id=s.player_id AND w.season_id=s.season_id
        LEFT JOIN season_archive_jobs j ON j.player_id=s.player_id AND j.from_season_id=s.season_id
        WHERE s.player_id=$1 AND (d.ends_at<=$2 OR (d.ruleset_id='legacy' AND s.archived_at IS NOT NULL))
        """;

    private static void ValidateArchivePage(int limit, int offset)
    {
        if (limit is < 1 or > 50 || offset is < 0 or > 1_000_000)
            throw new DomainValidationException("Archive page size must be 1 to 50 and offset 0 to 1000000.");
    }

    private static SeasonArchiveSummaryResponse ReadArchiveSummary(NpgsqlDataReader r)
    {
        var season = r.GetString(0); var rules = r.GetString(1);
        DateTimeOffset? Date(int i) => r.IsDBNull(i) ? null : r.GetFieldValue<DateTimeOffset>(i);
        string? Text(int i) => r.IsDBNull(i) ? null : r.GetString(i);
        var wallet = r.IsDBNull(10) ? null : new SeasonWalletResponse(season,r.GetInt64(10),r.GetInt64(11),r.GetInt64(12),
            r.GetInt64(13),Date(14),rules=="season-v1",r.GetInt64(15),r.GetInt64(16));
        return new(season,rules,Text(2),Text(3),Text(4),Date(5),Date(6),Date(7),r.GetString(8),Text(9),wallet,
            r.GetInt64(17),r.GetInt64(18),r.GetInt64(19),r.GetInt64(20));
    }

    public async Task<SeasonArchivesResponse> GetSeasonArchivesAsync(Guid playerId, int limit, int offset, CancellationToken ct)
    {
        ValidateArchivePage(limit,offset); var now=(timeProvider??TimeProvider.System).GetUtcNow();
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using var command=new NpgsqlCommand(ArchiveSummarySql+" ORDER BY d.ends_at DESC NULLS LAST,d.season_id LIMIT $3 OFFSET $4",connection,transaction);
        command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(now);command.Parameters.AddWithValue(limit+1);command.Parameters.AddWithValue(offset);
        var rows=new List<SeasonArchiveSummaryResponse>();
        await using(var reader=await command.ExecuteReaderAsync(ct)) while(await reader.ReadAsync(ct))rows.Add(ReadArchiveSummary(reader));
        var more=rows.Count>limit;if(more)rows.RemoveAt(rows.Count-1);await transaction.CommitAsync(ct);
        return new(rows,more?offset+limit:null);
    }

    public async Task<SeasonArchiveSectionResponse?> GetSeasonArchiveSectionAsync(Guid playerId,string seasonId,string section,
        int limit,int offset,CancellationToken ct)
    {
        ValidateArchivePage(limit,offset);
        if (string.IsNullOrWhiteSpace(seasonId) || seasonId.Length>80 || section is not ("equipment" or "recipes" or "wishes" or "loadouts"))
            throw new DomainValidationException("The archive source or section is invalid.");
        var now=(timeProvider??TimeProvider.System).GetUtcNow();
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        SeasonArchiveSummaryResponse summary;
        await using(var query=new NpgsqlCommand(ArchiveSummarySql+" AND d.season_id=$3",connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(now);query.Parameters.AddWithValue(seasonId);
            await using var reader=await query.ExecuteReaderAsync(ct);if(!await reader.ReadAsync(ct))return null;
            summary=ReadArchiveSummary(reader);
        }
        var equipment=new List<EquipmentResponse>();var recipes=new List<SeasonRecipeResponse>();
        var wishes=new List<ArchivedCraftingWishResponse>();var loadouts=new List<LoadoutResponse>();
        var sql=section switch
        {
            "equipment"=>"""
                SELECT instance_id,slot,quality,level,is_bound,location,version,element,effect_affix,secondary_trait,
                    origin_season_id,season_id,asset_scope,stats_version,source_kind,recipe_extracted,unique_affix,unique_element
                FROM equipments WHERE owner_id=$1 AND season_id=$2 AND asset_scope IN ('ActiveSeason','ArchivedSeason')
                ORDER BY instance_id LIMIT $3 OFFSET $4
                """,
            "recipes"=>"""
                SELECT recipe_id,season_id,quality,slot,element,effect_affix,secondary_trait,stats_version,source_item_id
                FROM learned_season_recipes WHERE player_id=$1 AND season_id=$2 ORDER BY recipe_id LIMIT $3 OFFSET $4
                """,
            "wishes"=>"""
                SELECT quality,slot,element,wished_effect,failures FROM player_crafting_wishes
                WHERE player_id=$1 AND season_id=$2 ORDER BY quality,slot,element,wished_effect LIMIT $3 OFFSET $4
                """,
            _=>"""
                SELECT hero_class,head_id,chest_id,hands_id,legs_id,feet_id,original_version FROM season_archive_loadouts
                WHERE player_id=$1 AND season_id=$2 ORDER BY hero_class LIMIT $3 OFFSET $4
                """
        };
        await using(var query=new NpgsqlCommand(sql,connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(seasonId);query.Parameters.AddWithValue(limit+1);query.Parameters.AddWithValue(offset);
            await using var reader=await query.ExecuteReaderAsync(ct);
            while(await reader.ReadAsync(ct))
            {
                switch(section)
                {
                    case "equipment":equipment.Add(ReadCompleteEquipment(reader));break;
                    case "recipes":recipes.Add(RecipeRow(reader));break;
                    case "wishes":wishes.Add(new(reader.GetString(0),reader.GetString(1),reader.GetString(2),reader.GetString(3),reader.GetInt32(4)));break;
                    case "loadouts":loadouts.Add(new((HeroClassDto)reader.GetInt16(0),Enumerable.Range(1,5).Select(i=>reader.IsDBNull(i)?null:(Guid?)reader.GetGuid(i)).ToArray(),reader.GetInt64(6),seasonId));break;
                }
            }
        }
        var count=equipment.Count+recipes.Count+wishes.Count+loadouts.Count;var more=count>limit;
        if(more)
        {
            if(equipment.Count>limit)equipment.RemoveAt(limit);if(recipes.Count>limit)recipes.RemoveAt(limit);
            if(wishes.Count>limit)wishes.RemoveAt(limit);if(loadouts.Count>limit)loadouts.RemoveAt(limit);
        }
        var references=new List<EquipmentResponse>();
        if(loadouts.Count>0)
        {
            var ids=loadouts.SelectMany(x=>x.EquipmentIds).Where(x=>x.HasValue).Select(x=>x!.Value).Distinct().ToArray();
            await using var query=new NpgsqlCommand("""
                SELECT instance_id,slot,quality,level,is_bound,location,version,element,effect_affix,secondary_trait,
                    origin_season_id,season_id,asset_scope,stats_version,source_kind,recipe_extracted,unique_affix,unique_element
                FROM equipments WHERE owner_id=$1 AND season_id=$2 AND instance_id=ANY($3)
                    AND asset_scope IN ('ActiveSeason','ArchivedSeason') ORDER BY instance_id
                """,connection,transaction);
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(seasonId);
            query.Parameters.AddWithValue(NpgsqlDbType.Array|NpgsqlDbType.Uuid,ids);
            await using var reader=await query.ExecuteReaderAsync(ct);while(await reader.ReadAsync(ct))references.Add(ReadCompleteEquipment(reader));
        }
        await transaction.CommitAsync(ct);
        return new(summary,section,true,equipment,recipes,wishes,loadouts,more?offset+limit:null,references);
    }
}
