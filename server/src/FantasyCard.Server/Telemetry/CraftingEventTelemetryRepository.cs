using System.Data;
using System.Text.Json;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

public sealed record CraftingEventTelemetryReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,IReadOnlyList<DurableCraftingEvent> Events,
    int MissingHistoricalActions,int InvalidObservations,int ObservedNoEventActions,bool SourceTruncated,bool CraftingSourceComplete,
    string Scope="Three crafting event types only; lobby dimensions remain unknown. Reforge mutates an existing item; learning retains its sample.");

public sealed class CraftingEventTelemetryRepository(NpgsqlDataSource dataSource)
{
    public async Task<CraftingEventTelemetryReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,CancellationToken cancellationToken)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);from=from.ToUniversalTime();to=to.ToUniversalTime();
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var config=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await config.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout=5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        var events=new List<DurableCraftingEvent>();var missing=0;var invalid=0;var empty=0;var truncated=false;
        await using(var query=new NpgsqlCommand("""
            SELECT action_id,player_id,created_at,season_id,action_kind,
                CASE WHEN octet_length(telemetry_json::text)<=65536 THEN telemetry_json::text ELSE NULL END,
                telemetry_json IS NULL
            FROM season_equipment_actions WHERE created_at >= $1 AND created_at < $2
            ORDER BY created_at,action_id LIMIT 1001
            """,connection,transaction))
        {
            query.Parameters.AddWithValue(from);query.Parameters.AddWithValue(to);
            await using var reader=await query.ExecuteReaderAsync(ct);var count=0;
            while(await reader.ReadAsync(ct))
            {
                if(++count>1000){truncated=true;break;}
                if(reader.GetBoolean(6)){missing++;continue;}
                if(reader.IsDBNull(5)){invalid++;continue;}
                CraftingEventObservation? observation;
                try{observation=JsonSerializer.Deserialize<CraftingEventObservation>(reader.GetString(5));}
                catch(JsonException){invalid++;continue;}
                if(!Valid(observation,reader.GetString(3),reader.GetString(4))){invalid++;continue;}
                var rows=CraftingEventObservations.Expand(reader.GetGuid(0),reader.GetGuid(1),reader.GetFieldValue<DateTimeOffset>(2),observation!);
                if(rows.Count==0)empty++;
                events.AddRange(rows);
            }
        }
        await transaction.CommitAsync(ct);
        return new(from,to,events,missing,invalid,empty,truncated,!truncated&&missing==0&&invalid==0);
    }

    private static bool Valid(CraftingEventObservation? row,string season,string kind)
    {
        if(row is not {SchemaVersion:1,Dimensions:not null,EventNames:not null}||row.Dimensions.SeasonId!=season||row.Operation!=kind||row.ItemId==Guid.Empty)return false;
        string[] expected=kind switch
        {
            "equipment.craft" when row.PityTriggered is true=>["craft_completed","pity_triggered"],
            "equipment.craft" when row.PityTriggered is false=>["craft_completed"],
            "equipment.reforge"=>["craft_completed"],
            "recipe.learn" when row.AlreadyLearned is false=>["recipe_learned"],
            "recipe.learn" when row.AlreadyLearned is true=>[],
            _=>["Invalid"]
        };
        return row.EventNames.SequenceEqual(expected,StringComparer.Ordinal);
    }
}
