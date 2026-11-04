using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonActivityExchangeConfig(string RuleId,int TokenCost,string RewardKind,int RewardCount,int EventLimit);
public sealed record SeasonActivityCalendarConfig(string EventId,int FirstDay42,int Days);
public sealed record SeasonActivityWindow(string EventId,DateTimeOffset StartsAt,DateTimeOffset EndsAt)
{
    public bool Contains(DateTimeOffset time)=>time>=StartsAt&&time<EndsAt;
}

public sealed record SeasonActivityConfig(string RuleId,string CompletionKind,int TokensPerCompletion,int TokenCap,
    string TimeZoneId,int StartHour,bool LateExchange,IReadOnlyList<SeasonActivityCalendarConfig> Calendar,
    IReadOnlyList<SeasonActivityExchangeConfig> Exchanges)
{
    public const string Version="season-limited-activity-v1";
    public void Validate()
    {
        SeasonActivityExchangeConfig[] expected=[new("event-fragments",3,"bound_fragments",10,4),
            new("event-warrior",3,"bound_warrior_soul",6,4),new("event-class",3,"bound_class_soul",2,4),new("event-potion",6,"potion",1,1)];
        if(RuleId!=Version||CompletionKind!="Extracted"||TokensPerCompletion!=4||TokenCap!=12||TimeZoneId!="Asia/Shanghai"||StartHour!=0||!LateExchange||
            Calendar.Count!=2||Calendar.Select(x=>x.EventId).Distinct(StringComparer.Ordinal).Count()!=2||
            Calendar.Any(x=>string.IsNullOrWhiteSpace(x.EventId)||x.EventId.Length>80||x.FirstDay42 is <1 or >40||x.Days!=3)||
            !Exchanges.OrderBy(x=>x.RuleId,StringComparer.Ordinal).SequenceEqual(expected.OrderBy(x=>x.RuleId,StringComparer.Ordinal)))
            throw new InvalidDataException("Activity terms differ from the limited bound-resource contract.");
        foreach(var duration in new[]{30,42,60})
        {
            var starts=Calendar.Select(x=>(x.FirstDay42-1)*duration/42).Order().ToArray();
            if(starts[0]+3>starts[1]||starts[1]+3>duration)
                throw new InvalidDataException("Activity calendars must fit two non-overlapping three-day windows.");
        }
    }

    public IReadOnlyList<SeasonActivityWindow> Windows(SeasonDefinition season)=>Calendar
        .Select(e=>new SeasonActivityWindow(e.EventId,season.StartsAtUtc.AddDays((e.FirstDay42-1)*season.DurationDays/42),
            season.StartsAtUtc.AddDays((e.FirstDay42-1)*season.DurationDays/42+e.Days)))
        .OrderBy(e=>e.StartsAt).ToArray();

    public SeasonActivityExchangeConfig Exchange(string id)=>Exchanges.SingleOrDefault(e=>e.RuleId==id)
        ??throw new DomainValidationException("The selected activity exchange is unavailable.");

    public (int Cost,int Reward) Quote(string ruleId,int quantity)
    {
        var rule=Exchange(ruleId);
        if(quantity<1||quantity>rule.EventLimit)throw new DomainValidationException("Activity quantity exceeds its event limit.");
        return (checked(rule.TokenCost*quantity),checked(rule.RewardCount*quantity));
    }
}
