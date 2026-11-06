using System.Diagnostics.Metrics;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Telemetry;

public enum TelemetryQueryOutcome { Success,Invalid,Timeout,Failure }
public sealed class EconomyTelemetryMetrics : IDisposable
{
    private readonly Meter _meter=new(ServerMetrics.MeterName);
    private readonly Histogram<double> _duration;
    public EconomyTelemetryMetrics()=>_duration=_meter.CreateHistogram<double>("fantasycard.telemetry.economy.query.duration","ms");
    public void Observe(TimeSpan elapsed,TelemetryQueryOutcome outcome)=>_duration.Record(Math.Max(0,elapsed.TotalMilliseconds),
        new KeyValuePair<string,object?>("outcome",outcome switch {TelemetryQueryOutcome.Success=>"success",TelemetryQueryOutcome.Invalid=>"invalid",TelemetryQueryOutcome.Timeout=>"timeout",_=>"failure"}));
    public void Dispose()=>_meter.Dispose();
}
