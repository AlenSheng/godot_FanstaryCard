using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Settlement;

public sealed partial class SettlementRepository
{
    private static readonly JsonSerializerOptions ActivitySnapshotJson=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};
    private async Task CreditActivityCompletionAsync(NpgsqlConnection c,NpgsqlTransaction t,SettlementContext context,Guid playerId,Guid settlementId,
        string result,JsonElement details,DateTimeOffset recordedAt,CancellationToken ct)
    {
        if(context.Season is not {} source||result!="Extracted"||details.ValueKind!=JsonValueKind.Object)return;
        var config=_configurations.Resolve(context.ConfigVersion);if(config.SeasonActivity is null)return;
        // Pre-feature checkpoints have no original terminal time and do not
        // retroactively receive event tokens from the recovery/claim clock.
        if(!details.TryGetProperty("extractionCompletedAt",out var time)||time.ValueKind==JsonValueKind.Null)return;
        if(time.ValueKind!=JsonValueKind.String||!time.TryGetDateTimeOffset(out var occurredAt)||
            !details.TryGetProperty("roomId",out var room)||!room.TryGetGuid(out var roomId)||roomId!=context.RoomId||
            !details.TryGetProperty("revision",out var revision)||!revision.TryGetInt64(out var sourceRevision))
            throw new InvalidDataException("Activity completion has no original server room proof.");
        BattleRoomSnapshot checkpoint;
        await using(var q=new NpgsqlCommand("SELECT revision,snapshot_json::text FROM room_snapshots WHERE room_id=$1",c,t))
        {
            q.Parameters.AddWithValue(context.RoomId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetInt64(0)<sourceRevision)throw new InvalidDataException("Activity completion checkpoint is not durable yet.");
            checkpoint=JsonSerializer.Deserialize<BattleRoomSnapshot>(r.GetString(1),ActivitySnapshotJson)??throw new InvalidDataException("The original activity checkpoint is invalid.");
        }
        var player=checkpoint.Players.SingleOrDefault(p=>p.PlayerId==playerId);
        if(checkpoint.RoomId!=context.RoomId||checkpoint.Season!=source||checkpoint.ConfigVersion!=source.ConfigVersion||
            player is null||player.IsBot||player.Phase!=RoomPlayerPhase.Extracted||player.ExtractionCompletedAt!=occurredAt)
            throw new InvalidDataException("Activity completion differs from its durable checkpoint.");
        await using(var q=new NpgsqlCommand("SELECT mp.is_bot,m.created_at FROM match_players mp JOIN matches m USING(match_id) WHERE mp.match_id=$1 AND mp.player_id=$2",c,t))
        {
            q.Parameters.AddWithValue(context.MatchId);q.Parameters.AddWithValue(playerId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetBoolean(0)||r.IsDBNull(1)||occurredAt<r.GetFieldValue<DateTimeOffset>(1)||occurredAt>recordedAt)
                throw new InvalidDataException("Activity completion is not from an admitted real-player match.");
        }
        SeasonDefinition definition;
        await using(var q=new NpgsqlCommand("SELECT starts_at,ends_at,highest_open_difficulty FROM season_definitions WHERE season_id=$1",c,t))
        {
            q.Parameters.AddWithValue(source.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct))throw new InvalidDataException("The original activity season is missing.");
            definition=new(source.SeasonId,source.RulesetId,source.ConfigVersion,source.StatsVersion,r.GetFieldValue<DateTimeOffset>(0),r.GetFieldValue<DateTimeOffset>(1),r.GetInt16(2));
        }
        await SeasonActivityRepository.CreditCompletionWithinTransactionAsync(c,t,playerId,context.MatchId,settlementId,context.RoomId,sourceRevision,
            definition,config,source.Difficulty,occurredAt.ToUniversalTime(),recordedAt,ct);
    }
}
