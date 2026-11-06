using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Settlement;

public sealed partial class SettlementRepository
{
    private async Task CreditJourneyAsync(NpgsqlConnection c,NpgsqlTransaction t,SettlementContext context,Guid playerId,
        Guid settlementId,string result,JsonElement details,DateTimeOffset recordedAt,CancellationToken ct)
    {
        if(context.Season is not {} source||result is not ("Extracted" or "Dead")||details.ValueKind!=JsonValueKind.Object)return;
        var config=_configurations.Resolve(context.ConfigVersion);if(config.SeasonJourney is null)return;
        SeasonCellCompletionSnapshot[] clears=[];
        if(details.TryGetProperty("journeyCompletions",out var entries)&&entries.ValueKind!=JsonValueKind.Null)
        {
            if(entries.ValueKind!=JsonValueKind.Array)throw new InvalidDataException("Journey source must be an original completion list.");
            clears=JsonSerializer.Deserialize<SeasonCellCompletionSnapshot[]>(entries.GetRawText(),ActivitySnapshotJson)
                ??throw new InvalidDataException("Journey completion list is invalid.");
        }
        DateTimeOffset? extraction=null;
        if(result=="Extracted"&&details.TryGetProperty("extractionCompletedAt",out var time)&&time.ValueKind!=JsonValueKind.Null)
        {
            if(time.ValueKind!=JsonValueKind.String||!time.TryGetDateTimeOffset(out var at))
                throw new InvalidDataException("Journey extraction time is invalid.");
            extraction=at;
        }
        // Missing provenance in an older checkpoint does not become a source
        // merely because settlement is being observed by a newer process.
        if(clears.Length==0&&extraction is null)return;
        if(!details.TryGetProperty("roomId",out var room)||!room.TryGetGuid(out var roomId)||roomId!=context.RoomId||
            !details.TryGetProperty("revision",out var revision)||!revision.TryGetInt64(out var sourceRevision))
            throw new InvalidDataException("Journey completion is missing its original room proof.");
        BattleRoomSnapshot checkpoint;
        await using(var q=new NpgsqlCommand("SELECT revision,snapshot_json::text FROM room_snapshots WHERE room_id=$1",c,t))
        {
            q.Parameters.AddWithValue(context.RoomId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetInt64(0)<sourceRevision)throw new InvalidDataException("Journey checkpoint is not durable yet.");
            checkpoint=JsonSerializer.Deserialize<BattleRoomSnapshot>(r.GetString(1),ActivitySnapshotJson)
                ??throw new InvalidDataException("The original journey checkpoint is invalid.");
        }
        var player=checkpoint.Players.SingleOrDefault(p=>p.PlayerId==playerId);
        var expectedPhase=result=="Extracted"?RoomPlayerPhase.Extracted:RoomPlayerPhase.Dead;
        if(checkpoint.RoomId!=context.RoomId||checkpoint.Season!=source||checkpoint.ConfigVersion!=source.ConfigVersion||player is null||
            player.IsBot||player.Phase!=expectedPhase||!clears.SequenceEqual(player.JourneyCompletions??[])||
            (result=="Extracted"&&player.ExtractionCompletedAt!=extraction))
            throw new InvalidDataException("Journey sources differ from the original durable checkpoint.");
        DateTimeOffset matchCreatedAt;
        await using(var q=new NpgsqlCommand("SELECT mp.is_bot,m.created_at FROM match_players mp JOIN matches m USING(match_id) WHERE mp.match_id=$1 AND mp.player_id=$2",c,t))
        {
            q.Parameters.AddWithValue(context.MatchId);q.Parameters.AddWithValue(playerId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetBoolean(0))throw new InvalidDataException("Journey completion is not from an admitted real-player match.");
            matchCreatedAt=r.GetFieldValue<DateTimeOffset>(1);
        }
        var sources=new List<SeasonJourneySource>();var positions=new HashSet<MapPosition>();var battles=new HashSet<Guid>();
        foreach(var entry in clears)
        {
            var cell=checkpoint.Map?.Cells.SingleOrDefault(cell=>cell.Position==entry.Position);
            if(cell is null||cell.MonsterGroupId!=entry.MonsterGroupId||entry.BattleId==Guid.Empty||
                !positions.Add(entry.Position)||!battles.Add(entry.BattleId)||!(player.ClearedCells??[]).Contains(entry.Position))
                throw new InvalidDataException("Journey clear has an invalid or duplicated original PVE source.");
            sources.Add(new(FormattableString.Invariant($"cell:{entry.Position.Row}:{entry.Position.Column}"),
                SeasonJourneyConfig.CellKind(cell),entry.BattleId,entry.CompletedAt.ToUniversalTime()));
        }
        if(extraction is {} completed)sources.Add(new("extraction","Extracted",null,completed.ToUniversalTime()));
        if(sources.Any(s=>s.OccurredAt<matchCreatedAt||s.OccurredAt>recordedAt))
            throw new InvalidDataException("Journey completion time is outside its admitted match history.");
        SeasonDefinition definition;
        await using(var q=new NpgsqlCommand("SELECT ruleset_id,config_version,stats_version,starts_at,ends_at,highest_open_difficulty FROM season_definitions WHERE season_id=$1",c,t))
        {
            q.Parameters.AddWithValue(source.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetString(0)!=source.RulesetId||r.GetString(1)!=source.ConfigVersion||r.GetString(2)!=source.StatsVersion)
                throw new InvalidDataException("The journey's original season definition is missing or changed.");
            definition=new(source.SeasonId,source.RulesetId,source.ConfigVersion,source.StatsVersion,
                r.GetFieldValue<DateTimeOffset>(3),r.GetFieldValue<DateTimeOffset>(4),r.GetInt16(5));
        }
        await SeasonJourneyRepository.CreditWithinTransactionAsync(c,t,playerId,context.MatchId,settlementId,context.RoomId,
            definition,config,source.Difficulty,sources,recordedAt,sourceRevision,ct);
    }
}
