using System.Diagnostics;
using FantasyCard.Server.Telemetry;
using Npgsql;

namespace FantasyCard.Server.Admin;

public static partial class AdminEndpoints
{
    private static async Task<IResult> ReadPhysicalEquipmentAsync(DateTimeOffset? from,DateTimeOffset? to,TimeProvider clock,
        PhysicalEquipmentTelemetryRepository repository,EconomyTelemetryMetrics metrics,CancellationToken ct)
    {
        var began=Stopwatch.GetTimestamp();var outcome=TelemetryQueryOutcome.Failure;
        try
        {
            var end=to??clock.GetUtcNow();var start=from??end.AddDays(-1);var report=await repository.ReadAsync(start,end,ct);
            outcome=TelemetryQueryOutcome.Success;return Results.Ok(report);
        }
        catch(ArgumentException){outcome=TelemetryQueryOutcome.Invalid;return Results.Problem(statusCode:400,title:"Use an interval of at most seven days.");}
        catch(PostgresException error)when(error.SqlState=="57014"&&!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        finally{metrics.Observe(Stopwatch.GetElapsedTime(began),outcome);}
    }

    private static async Task<IResult> ReadRoomEventsAsync(DateTimeOffset? from,DateTimeOffset? to,TimeProvider clock,
        RoomEventTelemetryRepository repository,EconomyTelemetryMetrics metrics,CancellationToken ct)
    {
        var began=Stopwatch.GetTimestamp();var outcome=TelemetryQueryOutcome.Failure;
        try
        {
            var end=to??clock.GetUtcNow();var start=from??end.AddDays(-1);
            var report=await repository.ReadAsync(start,end,ct);outcome=TelemetryQueryOutcome.Success;return Results.Ok(report);
        }
        catch(ArgumentException){outcome=TelemetryQueryOutcome.Invalid;return Results.Problem(statusCode:400,title:"Use an interval of at most seven days.");}
        catch(PostgresException error)when(error.SqlState=="57014"&&!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        finally{metrics.Observe(Stopwatch.GetElapsedTime(began),outcome);}
    }

    private static async Task<IResult> ReadLifecycleEventsAsync(DateTimeOffset? from,DateTimeOffset? to,TimeProvider clock,
        LifecycleEventTelemetryRepository repository,EconomyTelemetryMetrics metrics,CancellationToken ct)
    {
        var began=Stopwatch.GetTimestamp();var outcome=TelemetryQueryOutcome.Failure;
        try
        {
            var end=to??clock.GetUtcNow();var start=from??end.AddDays(-1);
            var report=await repository.ReadAsync(start,end,ct);outcome=TelemetryQueryOutcome.Success;return Results.Ok(report);
        }
        catch(ArgumentException){outcome=TelemetryQueryOutcome.Invalid;return Results.Problem(statusCode:400,title:"Use an interval of at most seven days.");}
        catch(PostgresException error)when(error.SqlState=="57014"&&!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        finally{metrics.Observe(Stopwatch.GetElapsedTime(began),outcome);}
    }

    private static async Task<IResult> ReadCraftingEventsAsync(DateTimeOffset? from,DateTimeOffset? to,TimeProvider clock,
        CraftingEventTelemetryRepository repository,EconomyTelemetryMetrics metrics,CancellationToken ct)
    {
        var began=Stopwatch.GetTimestamp();var outcome=TelemetryQueryOutcome.Failure;
        try
        {
            var end=to??clock.GetUtcNow();var start=from??end.AddDays(-1);
            var report=await repository.ReadAsync(start,end,ct);outcome=TelemetryQueryOutcome.Success;return Results.Ok(report);
        }
        catch(ArgumentException){outcome=TelemetryQueryOutcome.Invalid;return Results.Problem(statusCode:400,title:"Use an interval of at most seven days.");}
        catch(PostgresException error)when(error.SqlState=="57014"&&!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        finally{metrics.Observe(Stopwatch.GetElapsedTime(began),outcome);}
    }

    private static async Task<IResult> ReadPlaytimeTelemetryAsync(string currency,string? seasonId,bool? legacy,DateTimeOffset? from,DateTimeOffset? to,
        TimeProvider clock,PlaytimeTelemetryRepository repository,EconomyTelemetryMetrics metrics,CancellationToken ct)
    {
        var began=Stopwatch.GetTimestamp();var outcome=TelemetryQueryOutcome.Failure;
        try
        {
            var end=to??clock.GetUtcNow();var start=from??end.AddDays(-1);
            var report=await repository.ReadAsync(start,end,currency,seasonId,legacy??false,ct);outcome=TelemetryQueryOutcome.Success;return Results.Ok(report);
        }
        catch(ArgumentException){outcome=TelemetryQueryOutcome.Invalid;return Results.Problem(statusCode:400,title:"Specify a valid currency wallet and an interval of at most seven days.");}
        catch(PostgresException error)when(error.SqlState=="57014"&&!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        finally{metrics.Observe(Stopwatch.GetElapsedTime(began),outcome);}
    }

    private static async Task<IResult> ReadEconomyTelemetryAsync(DateTimeOffset? from,DateTimeOffset? to,TimeProvider clock,
        EconomyTelemetryRepository repository,EconomyTelemetryMetrics metrics,CancellationToken ct)
    {
        var began=Stopwatch.GetTimestamp();var outcome=TelemetryQueryOutcome.Failure;
        try
        {
            var end=to??clock.GetUtcNow();var start=from??end.AddDays(-1);
            EconomyTelemetryRepository.ValidateWindow(start,end);
            var report=await repository.ReadAsync(start,end,ct);outcome=TelemetryQueryOutcome.Success;return Results.Ok(report);
        }
        catch(ArgumentException){outcome=TelemetryQueryOutcome.Invalid;return Results.Problem(statusCode:400,title:"Use an interval of at most seven days.");}
        catch(PostgresException error)when(error.SqlState=="57014"&&!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        catch(OperationCanceledException)when(!ct.IsCancellationRequested)
        {outcome=TelemetryQueryOutcome.Timeout;return Results.Problem(statusCode:503,title:"Telemetry query deadline exceeded.");}
        finally{metrics.Observe(Stopwatch.GetElapsedTime(began),outcome);}
    }
}
