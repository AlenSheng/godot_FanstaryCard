using System.Diagnostics;
using Npgsql;

namespace FantasyCard.Server.Common;

public enum RuntimePhase { DatabaseAcquire, SqlExecution, PlayerLockRoundTrip, ActorExecute, SocketGateWait, SocketSend }

/// <summary>Local monotonic durations; business identities belong to traces only.</summary>
public sealed class RuntimeTiming : IDisposable
{
    private static readonly ActivitySource Source = new(ServerMetrics.MeterName);
    private readonly long _started = Stopwatch.GetTimestamp();
    private readonly ServerMetrics? _metrics;
    private readonly RuntimePhase _phase;
    private readonly Activity? _activity;

    private RuntimeTiming(ServerMetrics? metrics, RuntimePhase phase, ActivityContext? parent,
        string? room, string? player, string? request, string? match)
    {
        _metrics = metrics;
        _phase = phase;
        _activity = Source.StartActivity("runtime." + phase, ActivityKind.Internal,
            parent ?? Activity.Current?.Context ?? default);
        _activity?.SetTag("runtime.phase", phase.ToString());
        if (room is not null) _activity?.SetTag("room.id", room);
        if (player is not null) _activity?.SetTag("player.id", player);
        if (request is not null) _activity?.SetTag("request.id", request);
        if (match is not null) _activity?.SetTag("match.id", match);
    }

    public static RuntimeTiming Measure(ServerMetrics? metrics, RuntimePhase phase,
        ActivityContext? parent = null, string? room = null, string? player = null, string? request = null, string? match = null) =>
        new(metrics, phase, parent, room, player, request, match);

    public static async Task<NpgsqlConnection> OpenConnectionAsync(NpgsqlDataSource source,
        ServerMetrics metrics, Guid player, string request, CancellationToken ct)
    {
        using var timing = Measure(metrics, RuntimePhase.DatabaseAcquire, player: player.ToString("D"), request: request);
        return await source.OpenConnectionAsync(ct);
    }

    public static async Task<NpgsqlDataReader> ExecuteReaderAsync(NpgsqlCommand command,
        ServerMetrics metrics, Guid player, string request, CancellationToken ct)
    {
        using var timing = Measure(metrics, RuntimePhase.SqlExecution, player: player.ToString("D"), request: request);
        return await command.ExecuteReaderAsync(ct);
    }

    public void Dispose()
    {
        _metrics?.ObserveRuntimePhase(_phase, Stopwatch.GetElapsedTime(_started));
        _activity?.Dispose();
    }
}
