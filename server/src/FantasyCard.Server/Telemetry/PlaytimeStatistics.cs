using System.Globalization;
using System.Numerics;

namespace FantasyCard.Server.Telemetry;

public sealed record PlaytimeInterval(Guid PlayerId,string PlayerKind,string Hero,DateTimeOffset StartedAtUtc,TimeSpan ObservedElapsed,TimeSpan? TerminalElapsed,bool Terminal);
public sealed record ExactHourlyRate(string Numerator,string Denominator,string DecimalDisplay);
public sealed record PlaytimeRateSample(Guid PlayerId,string PlayerKind,string Hero,long KnownTicks,BigInteger Net);
public sealed record PlaytimeRateDistribution(string PlayerKind,string Hero,int Players,int ZeroNetPlayers,int NegativeNetPlayers,string KnownPlayerTicks,
    string NetAmount,ExactHourlyRate WeightedNetPerHour,ExactHourlyRate P10,ExactHourlyRate P50,ExactHourlyRate P90);
public sealed record PlaytimeClockProjection(IReadOnlyList<PlaytimeRateSample> Samples,int InvalidClocks,int UnknownTerminalClocks,int ZeroLengthClocks,int RightCensoredClocks);

public static class PlaytimeStatistics
{
    public static PlaytimeClockProjection Project(IEnumerable<PlaytimeInterval> source,DateTimeOffset from,DateTimeOffset to,IReadOnlyDictionary<Guid,BigInteger> net)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);var intervals=new Dictionary<Guid,List<(long Start,long End)>>();var profile=new Dictionary<Guid,(HashSet<string> Kind,HashSet<string> Hero)>();
        var invalid=0;var unknown=0;var zero=0;var censored=0;
        foreach(var row in source)
        {
            if(row.ObservedElapsed<TimeSpan.Zero){invalid++;continue;}
            if(row.Terminal&&row.TerminalElapsed==TimeSpan.Zero||!row.Terminal&&row.TerminalElapsed is null&&row.ObservedElapsed==TimeSpan.Zero)
            {if(row.StartedAtUtc>=from&&row.StartedAtUtc<to)zero++;continue;}
            var possibleEnd=(BigInteger)row.StartedAtUtc.UtcTicks+row.ObservedElapsed.Ticks;
            if(possibleEnd<=from.UtcTicks||row.StartedAtUtc.UtcTicks>=to.UtcTicks)continue;
            if(row.Terminal&&row.TerminalElapsed is null){unknown++;continue;}
            var elapsed=row.Terminal?row.TerminalElapsed!.Value:row.ObservedElapsed;
            if(elapsed<TimeSpan.Zero||row.ObservedElapsed<elapsed||!row.Terminal&&row.TerminalElapsed is not null){invalid++;continue;}
            var end=(BigInteger)row.StartedAtUtc.UtcTicks+elapsed.Ticks;
            if(end>DateTimeOffset.MaxValue.UtcTicks||end<DateTimeOffset.MinValue.UtcTicks){invalid++;continue;}
            if(elapsed==TimeSpan.Zero){zero++;continue;}
            var start=Math.Max(row.StartedAtUtc.UtcTicks,from.UtcTicks);var finish=Math.Min((long)end,to.UtcTicks);if(finish<=start)continue;
            if(!row.Terminal&&end<to.UtcTicks)censored++;
            if(!intervals.TryGetValue(row.PlayerId,out var list)){intervals[row.PlayerId]=list=[];profile[row.PlayerId]=(new(StringComparer.Ordinal),new(StringComparer.Ordinal));}
            list.Add((start,finish));profile[row.PlayerId].Kind.Add(row.PlayerKind is "Human" or "Bot"?row.PlayerKind:"Unknown");
            profile[row.PlayerId].Hero.Add(row.Hero is "Mage" or "Priest" or "Guardian"?row.Hero:"Unknown");
        }
        var result=new List<PlaytimeRateSample>();
        foreach(var(player,list)in intervals)
        {
            long total=0,start=-1,end=-1;
            foreach(var span in list.OrderBy(v=>v.Start).ThenBy(v=>v.End))
            {
                if(start<0){start=span.Start;end=span.End;}
                else if(span.Start<=end)end=Math.Max(end,span.End);
                else{total+=end-start;start=span.Start;end=span.End;}
            }
            if(start>=0)total+=end-start;
            string Compose(HashSet<string> values)=>values.Contains("Unknown")?"Unknown":values.Count==1?values.Single():"Mixed";
            result.Add(new(player,Compose(profile[player].Kind),Compose(profile[player].Hero),total,net.GetValueOrDefault(player)));
        }
        return new(result,invalid,unknown,zero,censored);
    }

    public static IReadOnlyList<PlaytimeRateDistribution> Distributions(IEnumerable<PlaytimeRateSample> source)=>source.Where(s=>s.KnownTicks>0)
        .GroupBy(s=>(s.PlayerKind,s.Hero)).OrderBy(g=>g.Key.PlayerKind,StringComparer.Ordinal).ThenBy(g=>g.Key.Hero,StringComparer.Ordinal).Select(g=>
        {
            var samples=g.ToArray();var sorted=samples.OrderBy(s=>s,Comparer<PlaytimeRateSample>.Create((a,b)=>(a.Net*b.KnownTicks).CompareTo(b.Net*a.KnownTicks))).ToArray();
            var ticks=samples.Aggregate(BigInteger.Zero,(sum,s)=>sum+s.KnownTicks);var net=samples.Aggregate(BigInteger.Zero,(sum,s)=>sum+s.Net);
            ExactHourlyRate Percentile(int percentile){var at=Math.Max(0,(sorted.Length*percentile+99)/100-1);return Rate(sorted[at].Net,sorted[at].KnownTicks);}
            return new PlaytimeRateDistribution(g.Key.PlayerKind,g.Key.Hero,samples.Length,samples.Count(s=>s.Net.IsZero),samples.Count(s=>s.Net.Sign<0),Text(ticks),Text(net),Rate(net,ticks),Percentile(10),Percentile(50),Percentile(90));
        }).ToArray();

    public static ExactHourlyRate Rate(BigInteger net,BigInteger ticks)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(ticks);var numerator=net*TimeSpan.TicksPerHour;var divisor=BigInteger.GreatestCommonDivisor(BigInteger.Abs(numerator),ticks);
        numerator/=divisor;ticks/=divisor;var scaled=BigInteger.DivRem(BigInteger.Abs(numerator)*1000000,ticks,out var remainder);if(remainder*2>=ticks)scaled++;
        var display=(numerator.Sign<0&&scaled>0?"-":"")+Text(scaled/1000000)+"."+(scaled%1000000).ToString("D6",CultureInfo.InvariantCulture);
        return new(Text(numerator),Text(ticks),display);
    }
    private static string Text(BigInteger value)=>value.ToString(CultureInfo.InvariantCulture);
}
