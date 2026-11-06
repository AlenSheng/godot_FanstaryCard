using System.Data;
using System.Globalization;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

public sealed record DurableRoomEvent(string EventId,Guid RoomId,Guid MatchId,string ConfigVersion,SeasonContext? Season,RoomEventObservation Event,
    SeasonEventDimensions Dimensions,string BuildProfileBasis,string? BuildProfileId);
public sealed record RoomEventTelemetryReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,IReadOnlyList<DurableRoomEvent> Events,
    int SourceRooms,int LegacyUnobservedRooms,int InvalidRooms,int UnknownTimestampEvents,string DroppedEvents,long OmittedItems,
    bool SourceTruncated,bool FullyObserved,
    string ClockBasis="Original room UTC start plus authoritative logical elapsed, including recovery time.",
    string Scope="Room observations only: potential choices, carried items, exit and relic custody pending asset settlement. These are not additional account credits, irreversible destruction or proof of settlement commit.",
    IReadOnlyList<RoomBuildProfile>? BuildProfiles=null,IReadOnlyDictionary<string,int>? UnknownDimensionCounts=null,
    IReadOnlyList<CombatMeasurementReport>? CombatMeasurements=null,int RoomsWithoutCombatObservations=0,string? OmittedCombatMeasurements=null,bool CombatRowsTruncated=false,
    string CombatScope="Cumulative since each row's declared observation start, not time-window deltas. Partial/saturated rows are explicit. Advance ticks are actual combat-state advances, not human active time.");

public sealed class RoomEventTelemetryRepository(NpgsqlDataSource dataSource)
{
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};

    public async Task<RoomEventTelemetryReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,CancellationToken cancellationToken)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);from=from.ToUniversalTime();to=to.ToUniversalTime();
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var config=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await config.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout=5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        var events=new List<DurableRoomEvent>();var rooms=0;var missing=0;var invalid=0;var unknownTime=0;var dropped=BigInteger.Zero;long omitted=0;var truncated=false;
        var usedProfiles=new Dictionary<string,RoomBuildProfile>(StringComparer.Ordinal);
        var combatRows=new List<CombatMeasurementReport>();var missingCombat=0;var omittedCombat=BigInteger.Zero;var combatTruncated=false;
        await using(var query=new NpgsqlCommand("""
            SELECT s.room_id,m.match_id,m.config_version,m.season_id,m.difficulty,m.ruleset_id,m.stats_version,
                s.snapshot_json->>'startedAtUtc',s.snapshot_json->>'elapsed',coalesce(s.snapshot_json->'observations','null'::jsonb)='null'::jsonb,
                CASE WHEN octet_length((s.snapshot_json->'observations')::text)<=4194304 THEN (s.snapshot_json->'observations')::text END,
                (SELECT jsonb_agg(jsonb_build_object('playerId',p->'playerId','heroClass',p->'heroClass','isBot',p->'isBot'))::text
                    FROM jsonb_array_elements(CASE WHEN jsonb_typeof(s.snapshot_json->'players')='array' THEN s.snapshot_json->'players' ELSE '[]'::jsonb END)p),
                coalesce(s.snapshot_json->>'configVersion'=m.config_version
                    AND coalesce(s.snapshot_json->'season','null'::jsonb)=CASE WHEN m.season_id IS NULL THEN 'null'::jsonb
                        ELSE jsonb_build_object('seasonId',m.season_id,'difficulty',substring(m.difficulty,2)::int,'difficultyId',m.difficulty,
                            'rulesetId',m.ruleset_id,'configVersion',m.config_version,'statsVersion',m.stats_version) END,false)
            FROM room_snapshots s JOIN matches m ON m.room_id=s.room_id
            WHERE s.updated_at >= $1 AND m.created_at < $2 ORDER BY s.updated_at,s.room_id LIMIT 1001
            """,connection,transaction))
        {
            query.Parameters.AddWithValue(from);query.Parameters.AddWithValue(to);await using var reader=await query.ExecuteReaderAsync(ct);
            while(await reader.ReadAsync(ct))
            {
                if(rooms==1000){truncated=true;break;}rooms++;
                if(reader.GetBoolean(9)){missing++;continue;}
                if(reader.IsDBNull(10)||reader.IsDBNull(11)||!reader.GetBoolean(12)||reader.IsDBNull(7)||reader.IsDBNull(8)||
                    !DateTimeOffset.TryParse(reader.GetString(7),CultureInfo.InvariantCulture,DateTimeStyles.None,out var start)||
                    !TimeSpan.TryParseExact(reader.GetString(8),"c",CultureInfo.InvariantCulture,out var elapsed)){invalid++;continue;}
                RoomObservationSnapshot? observations;RoomObservationOwner[]? owners;
                try
                {
                    observations=JsonSerializer.Deserialize<RoomObservationSnapshot>(reader.GetString(10),Json);
                    owners=JsonSerializer.Deserialize<RoomObservationOwner[]>(reader.GetString(11),Json);
                    if(observations is null||owners is null){invalid++;continue;}
                    observations.RequireValid(owners,elapsed,start);
                }
                catch(Exception error)when(error is JsonException or DomainValidationException){invalid++;continue;}
                dropped+=observations.DroppedEvents;
                var profiles=(observations.Profiles??[]).ToDictionary(p=>p.ProfileId,StringComparer.Ordinal);
                SeasonContext? season=reader.IsDBNull(3)?null:new(reader.GetString(3),reader.GetString(4)[1]-'0',reader.GetString(5),reader.GetString(2),reader.GetString(6));
                if(observations.Combat is not { } combat)missingCombat++;
                else
                {
                    if(combat.HistoryMissing)missingCombat++;
                    omittedCombat+=combat.OmittedMeasurements;
                    foreach(var measurement in combat.Rows)
                    {
                        if((BigInteger)start.UtcTicks+measurement.ObservedThroughRoomElapsed.Ticks<from.UtcTicks||
                            (BigInteger)start.UtcTicks+measurement.ObservedFromRoomElapsed.Ticks>=to.UtcTicks)continue;
                        if(combatRows.Count==1000){combatTruncated=true;break;}
                        var binding=(observations.BattleBuilds??[]).SingleOrDefault(b=>b.PlayerId==measurement.PlayerId&&b.BattleId==measurement.BattleId);
                        var profile=binding is null?null:profiles.GetValueOrDefault(binding.ProfileId);
                        combatRows.Add(CombatMeasurementProjection.Project(reader.GetGuid(0),reader.GetString(2),season,reader.GetString(4),owners.Single(o=>o.PlayerId==measurement.PlayerId),measurement,profile));
                    }
                }
                foreach(var row in observations.Events)
                {
                    if(row.OccurredAtUtc is not { } at){unknownTime++;continue;}
                    if(at<from||at>=to)continue;
                    omitted+=row.OmittedItems;
                    if(events.Count==1000){truncated=true;continue;}
                    var projected=SeasonEventDimensionRules.Room(reader.GetString(2),season,reader.GetString(4),row,profiles);
                    if(projected.Profile is { } profile)usedProfiles.TryAdd(profile.ProfileId,profile);
                    var room=reader.GetGuid(0);events.Add(new($"{room:N}:{row.Sequence.ToString(CultureInfo.InvariantCulture)}",room,reader.GetGuid(1),reader.GetString(2),season,row,
                        projected.Dimensions,projected.Basis,projected.Profile?.ProfileId));
                }
            }
        }
        await transaction.CommitAsync(ct);
        return new(from,to,events.OrderBy(e=>e.Event.OccurredAtUtc).ThenBy(e=>e.RoomId).ThenBy(e=>e.Event.Sequence).ToArray(),rooms,missing,invalid,unknownTime,
            dropped.ToString(CultureInfo.InvariantCulture),omitted,truncated,!truncated&&missing==0&&invalid==0&&unknownTime==0&&dropped.IsZero&&omitted==0,
            BuildProfiles:usedProfiles.Values.OrderBy(p=>p.ProfileId,StringComparer.Ordinal).ToArray(),UnknownDimensionCounts:SeasonEventDimensionRules.UnknownCounts(events.Select(e=>e.Dimensions)),
            CombatMeasurements:combatRows,RoomsWithoutCombatObservations:missingCombat,OmittedCombatMeasurements:omittedCombat.ToString(CultureInfo.InvariantCulture),CombatRowsTruncated:combatTruncated);
    }
}
