using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Rooms;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed class SeasonRedMintRepository(NpgsqlDataSource dataSource,TimeProvider clock,PublishedConfigCatalogs configurations,
    IConfiguration? settings=null)
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};
    private readonly string _scope=settings?["Economy:QuotaScopeId"]??"primary";

    public async Task<RedDropReceipt> ResolveBossAsync(Guid matchId,Guid playerId,SeasonContext season,RedDropEvaluation pending,CancellationToken ct)
    {
        var policy=configurations.Resolve(season.ConfigVersion).SeasonRed
            ??throw new DomainValidationException("The frozen configuration has no enabled independent red policy.");
        var hash=Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new {matchId,playerId,season,pending},Json))));
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var tx=await connection.BeginTransactionAsync(ct);
        await using(var gate=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,0))",connection,tx))
        {gate.Parameters.AddWithValue("red-attempt:"+pending.AttemptId.ToString("D"));await gate.ExecuteNonQueryAsync(ct);}
        await using(var replay=new NpgsqlCommand("SELECT request_hash,status,equipment_json::text FROM season_red_drop_attempts WHERE attempt_id=$1",connection,tx))
        {
            replay.Parameters.AddWithValue(pending.AttemptId);await using var reader=await replay.ExecuteReaderAsync(ct);
            if(await reader.ReadAsync(ct))
            {
                if(reader.GetString(0)!=hash)throw new DomainValidationException("Independent red attempt replay changed its original source.");
                var result=new RedDropReceipt(pending.AttemptId,reader.GetString(1),reader.IsDBNull(2)?null:JsonSerializer.Deserialize<ExplorationItem>(reader.GetString(2),Json));
                await reader.DisposeAsync();await tx.CommitAsync(ct);return result;
            }
        }
        await using(var binding=new NpgsqlCommand("SELECT quota_scope FROM red_economy_scope_binding WHERE singleton=true",connection,tx))
            if(await binding.ExecuteScalarAsync(ct) as string!=_scope)throw new InvalidOperationException("Logical economy quota scope differs from its durable binding.");
        DateTimeOffset starts,ends;string raw;
        await using(var source=new NpgsqlCommand("""
            SELECT d.starts_at,d.ends_at,s.snapshot_json::text FROM matches m
            JOIN match_players mp ON mp.match_id=m.match_id AND mp.player_id=$2 AND NOT mp.is_bot
            JOIN season_definitions d ON d.season_id=m.season_id
            JOIN room_snapshots s ON s.room_id=m.room_id
            WHERE m.match_id=$1 AND m.season_id=$3 AND m.config_version=$4 AND m.ruleset_id=$5 AND m.stats_version=$6 AND m.difficulty=$7
            """,connection,tx))
        {
            source.Parameters.AddWithValue(matchId);source.Parameters.AddWithValue(playerId);source.Parameters.AddWithValue(season.SeasonId);
            source.Parameters.AddWithValue(season.ConfigVersion);source.Parameters.AddWithValue(season.RulesetId);source.Parameters.AddWithValue(season.StatsVersion);source.Parameters.AddWithValue(season.DifficultyId);
            await using var reader=await source.ExecuteReaderAsync(ct);
            if(!await reader.ReadAsync(ct))throw new InvalidOperationException("Red generation requires an original persisted human match.");
            starts=reader.GetFieldValue<DateTimeOffset>(0);ends=reader.GetFieldValue<DateTimeOffset>(1);raw=reader.GetString(2);
        }
        var snapshot=JsonSerializer.Deserialize<BattleRoomSnapshot>(raw,Json)??throw new InvalidOperationException("Red source checkpoint is invalid.");
        var owner=snapshot.Players.SingleOrDefault(player=>player.PlayerId==playerId);
        if(snapshot.Season!=season || owner is null || owner.IsBot || owner.PendingRedEvaluation!=pending ||
            owner.Position!=pending.Position || owner.Pve?.Phase!=PveBattlePhase.Cleared || owner.ClearedCells?.Contains(pending.Position)!=true ||
            snapshot.Map?.Cells.SingleOrDefault(cell=>cell.Position==pending.Position) is not {IsBoss:true,Layer:ChaosMapLayer.Core} ||
            pending.Source!="ChaosBoss" || season.Difficulty<policy.MinimumDifficulty || pending.OccurredAt<starts || pending.OccurredAt>=ends)
            throw new InvalidOperationException("Independent red event differs from the original eligible Boss checkpoint.");
        var now=clock.GetUtcNow();var week=DateOnly.ParseExact(RedEquipmentQuotaSchedule.GetWeekKey(now),"yyyy-MM-dd",System.Globalization.CultureInfo.InvariantCulture);
        var status="Miss";ExplorationItem? item=null;
        if(now<starts || now>=ends || owner.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)status="Closed";
        else if(policy.Hits(pending.Source,season.Difficulty,pending.Roll))
        {
            var id=Guid.NewGuid();
            if(!await RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,now,RedEquipmentDropSource.ChaosBoss,playerId,matchId,id,ct,_scope))status="Exhausted";
            else
            {
                var gear=FantasyCard.Domain.Configuration.SeasonRedConfig.Equipment(pending.EquipmentSeed,season.StatsVersion,owner.LootPreferenceElement,
                    configurations.Resolve(season.ConfigVersion).SeasonLootPreference);
                item=new(id.ToString("D"),ExplorationItemKind.Equipment,Equipment:gear,IsGenerated:false);
                await using var mint=new NpgsqlCommand("""
                    INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait,
                        origin_season_id,season_id,asset_scope,source_match_id,generated_difficulty,stats_version,source_kind,loot_rule_id,mint_id,quota_scope,mint_week,unique_affix,unique_element,source_loot_json)
                    VALUES($1,$2,$3,'Red',0,false,'InMatchBackpack',1,$4,$5,$6,$7,$8,$8,'ActiveSeason',$9,$10,$11,'RedBoss',$12,$13,$14,$15,$16,$17,$18)
                    """,connection,tx);
                mint.Parameters.AddWithValue(id);mint.Parameters.AddWithValue(playerId);mint.Parameters.AddWithValue(gear.Slot);mint.Parameters.AddWithValue(now);
                mint.Parameters.AddWithValue(gear.Element);mint.Parameters.AddWithValue(gear.EffectAffix!);mint.Parameters.AddWithValue(gear.SecondaryTrait);
                mint.Parameters.AddWithValue(season.SeasonId);mint.Parameters.AddWithValue(matchId);mint.Parameters.AddWithValue((short)season.Difficulty);
                mint.Parameters.AddWithValue(season.StatsVersion);mint.Parameters.AddWithValue(policy.RuleId);mint.Parameters.AddWithValue(pending.AttemptId);
                mint.Parameters.AddWithValue(_scope);mint.Parameters.AddWithValue(week);mint.Parameters.AddWithValue(gear.UniqueAffix!);
                mint.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)gear.UniqueElement??DBNull.Value);
                mint.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(new {season,source=pending.Source,attemptId=pending.AttemptId,scope=_scope,week,pending.Position},Json));
                await mint.ExecuteNonQueryAsync(ct);status="Minted";
            }
        }
        await using(var record=new NpgsqlCommand("""
            INSERT INTO season_red_drop_attempts(attempt_id,match_id,player_id,quota_scope,week_key,source,source_key,season_id,difficulty,ruleset_id,config_version,stats_version,
                roll,equipment_seed,occurred_at,request_hash,status,equipment_id,equipment_json,handled_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            """,connection,tx))
        {
            record.Parameters.AddWithValue(pending.AttemptId);record.Parameters.AddWithValue(matchId);record.Parameters.AddWithValue(playerId);record.Parameters.AddWithValue(_scope);
            record.Parameters.AddWithValue(week);record.Parameters.AddWithValue(pending.Source);record.Parameters.AddWithValue($"{pending.Position.Row}:{pending.Position.Column}");
            record.Parameters.AddWithValue(season.SeasonId);record.Parameters.AddWithValue((short)season.Difficulty);record.Parameters.AddWithValue(season.RulesetId);
            record.Parameters.AddWithValue(season.ConfigVersion);record.Parameters.AddWithValue(season.StatsVersion);record.Parameters.AddWithValue(pending.Roll);record.Parameters.AddWithValue(pending.EquipmentSeed);
            record.Parameters.AddWithValue(pending.OccurredAt);record.Parameters.AddWithValue(hash);record.Parameters.AddWithValue(status);
            record.Parameters.AddWithValue(NpgsqlDbType.Uuid,item is null?DBNull.Value:Guid.Parse(item.ItemId));record.Parameters.AddWithValue(NpgsqlDbType.Jsonb,item is null?DBNull.Value:JsonSerializer.Serialize(item,Json));record.Parameters.AddWithValue(now);
            await record.ExecuteNonQueryAsync(ct);
        }
        await tx.CommitAsync(ct);return new(pending.AttemptId,status,item);
    }
}
