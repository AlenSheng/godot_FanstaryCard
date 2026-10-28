using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Security.Cryptography;
using System.Text.Json;

namespace FantasyCard.Server.Common;

/// <summary>Opt-in owned local diagnostics. Business identities never become metric dimensions.</summary>
public sealed class LocalRuntimeDiagnostics : BackgroundService
{
    private const int MaximumObservations = 32768;
    private readonly MeterListener _listener = new();
    private readonly object _gate = new();
    private readonly Dictionary<string, List<double>> _durations = new(StringComparer.Ordinal);
    private readonly Dictionary<string, long> _counters = new(StringComparer.Ordinal);
    private readonly string _path;
    private readonly ILogger<LocalRuntimeDiagnostics> _logger;
    private long _dropped;
    private static readonly Action<ILogger, Exception?> OutputUnavailable = LoggerMessage.Define(
        LogLevel.Warning, new EventId(710, nameof(OutputUnavailable)), "Owned local diagnostic output unavailable.");

    public LocalRuntimeDiagnostics(ServerMetrics metrics, string path, ILogger<LocalRuntimeDiagnostics> logger)
    {
        if (!Path.IsPathFullyQualified(path)) throw new ArgumentException("Absolute owned diagnostic path required.", nameof(path));
        _path = path; _logger = logger;
        _listener.InstrumentPublished = (instrument, listener) =>
        {
            if (ReferenceEquals(instrument.Meter, metrics.SourceMeter)) listener.EnableMeasurementEvents(instrument);
        };
        _listener.SetMeasurementEventCallback<double>((instrument, value, tags, _) =>
        {
            if (!double.IsFinite(value) || value < 0) return;
            var name = instrument.Name;
            // Phase is a closed enum. Reject any unexpected dimension instead
            // of allowing an unbounded player/match/request series.
            if (name == "fantasycard.runtime.phase.duration")
            {
                string? phase = null;
                foreach (var tag in tags)
                    if (tag.Key == "phase" && Enum.TryParse<RuntimePhase>(tag.Value?.ToString(), out var parsed) && Enum.IsDefined(parsed))
                        phase = parsed.ToString();
                if (phase is null) return;
                name += ":" + phase;
            }
            if (name != "fantasycard.room_actor.command.wait" && name != "fantasycard.room_actor.tick.delay" &&
                !name.StartsWith("fantasycard.runtime.phase.duration:", StringComparison.Ordinal)) return;
            lock (_gate)
            {
                if (!_durations.TryGetValue(name, out var values)) _durations[name] = values = [];
                if (values.Count < MaximumObservations) values.Add(value); else _dropped++;
            }
        });
        _listener.SetMeasurementEventCallback<long>((instrument, value, _, _) =>
        {
            if (instrument.Name is not ("fantasycard.rooms.active" or "fantasycard.rooms.humans.active" or
                "fantasycard.realtime.connections.active")) return;
            lock (_gate) _counters[instrument.Name] = _counters.GetValueOrDefault(instrument.Name) + value;
        });
        _listener.Start();
    }

    internal Dictionary<string, object> DrainWindow()
    {
        lock (_gate)
        {
            var histograms = _durations.ToDictionary(pair => pair.Key, pair =>
            {
                var values = pair.Value.Order().ToArray();
                return new { count = values.Length, sum_ms = values.Sum(),
                    p95_ms = values.Length == 0 ? (double?)null : values[(int)Math.Ceiling(values.Length * .95) - 1] };
            });
            var result = new Dictionary<string, object>
            {
                ["durations"] = histograms, ["counters"] = new Dictionary<string, long>(_counters),
                ["dropped_observations"] = _dropped,
                ["actor_wait_missing_reason"] = !histograms.TryGetValue("fantasycard.room_actor.command.wait", out var actor) || actor.count == 0
                    ? "no_actor_wait_observation_in_this_window" : ""
            };
            _durations.Clear(); _dropped = 0;
            return result;
        }
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
            // Never append to an earlier process's receipt or overwrite it.
            await using var stream = new FileStream(_path, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
            await using var writer = new StreamWriter(stream);
            using var process = Process.GetCurrentProcess();
            var assembly = typeof(LocalRuntimeDiagnostics).Assembly.Location;
            var assemblyHash = Convert.ToHexStringLower(SHA256.HashData(await File.ReadAllBytesAsync(assembly, stoppingToken)));
            var started = Stopwatch.GetTimestamp(); var previous = started;
            var previousCpu = process.TotalProcessorTime;
            using var timer = new PeriodicTimer(TimeSpan.FromSeconds(1));
            for (var sequence = 1; sequence <= 4096 && await timer.WaitForNextTickAsync(stoppingToken); sequence++)
            {
                process.Refresh(); var now = Stopwatch.GetTimestamp(); var cpu = process.TotalProcessorTime;
                var window = DrainWindow();
                window["pid"] = process.Id; window["process_started_at"] = process.StartTime.ToUniversalTime();
                window["server_assembly_sha256"] = assemblyHash; window["sequence"] = sequence;
                window["observed_at_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                window["window_seconds"] = Stopwatch.GetElapsedTime(previous, now).TotalSeconds;
                window["elapsed_seconds"] = Stopwatch.GetElapsedTime(started, now).TotalSeconds;
                window["rss_bytes"] = process.WorkingSet64;
                window["server_cpu_percent"] = 100 * (cpu - previousCpu).TotalSeconds /
                    Stopwatch.GetElapsedTime(previous, now).TotalSeconds / Environment.ProcessorCount;
                window["managed_allocated_bytes_total"] = GC.GetTotalAllocatedBytes();
                window["managed_heap_bytes"] = GC.GetTotalMemory(false);
                window["gc_collections"] = Enumerable.Range(0, 3).Select(GC.CollectionCount).ToArray();
                await writer.WriteLineAsync(JsonSerializer.Serialize(window)); await writer.FlushAsync(stoppingToken);
                previous = now; previousCpu = cpu;
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { }
        catch (IOException)
        {
            // Diagnostic IO cannot terminate the authoritative game. Missing
            // receipts remain unavailable to the independent load reviewer.
            OutputUnavailable(_logger, null);
        }
        catch (UnauthorizedAccessException) { OutputUnavailable(_logger, null); }
    }

    public override void Dispose() { _listener.Dispose(); base.Dispose(); }
}
