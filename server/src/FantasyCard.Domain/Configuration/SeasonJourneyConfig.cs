using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonWeeklyContractConfig(string ContractId,string CompletionKind,int Target,int Experience);
public sealed record SeasonJourneyLevel(int Level,int ExperienceIntoLevel,int ExperienceToNext,int TotalExperience,int MainRewardLevels);
public sealed record SeasonJourneyGrant(int BaseExperience,int CatchUpExperience,int CreditedExperience,int ExperienceAfter);

/// <summary>Experience is separate from currency and permanent progression.</summary>
public sealed record SeasonJourneyConfig(string RuleId,int OuterExperience,int MiddleExperience,int EliteExperience,int BossExperience,
    int ExtractionExperience,int CatchUpMultiplier,int ReferenceDays,int ReferenceExperience42,int MainRewardLevels,
    IReadOnlyList<int> ExperienceToNext42,IReadOnlyList<SeasonWeeklyContractConfig> WeeklyContracts)
{
    public const string Version="season-journey-v1";

    public void Validate()
    {
        if(RuleId!=Version||OuterExperience!=6||MiddleExperience!=10||EliteExperience!=25||BossExperience!=80||
            ExtractionExperience!=70||CatchUpMultiplier!=2||ReferenceDays!=21||ReferenceExperience42!=6850||MainRewardLevels!=20||
            ExperienceToNext42.Count!=30||!ExperienceToNext42.SequenceEqual(Enumerable.Range(0,30).Select(level=>200+15*level))||
            WeeklyContracts.Count!=3||WeeklyContracts.Select(c=>c.ContractId).Distinct(StringComparer.Ordinal).Count()!=3||
            !WeeklyContracts.Select(c=>c.CompletionKind).Order(StringComparer.Ordinal).SequenceEqual(ContractKinds.Order(StringComparer.Ordinal))||
            WeeklyContracts.Any(c=>string.IsNullOrWhiteSpace(c.ContractId)||c.ContractId.Length>80||c.Target is <1 or >100||c.Experience!=300))
            throw new InvalidDataException("Season journey terms differ from the bounded experience contract.");
    }

    private static readonly string[] ContractKinds=["Extracted","Elite","Boss"];

    public int Cost(int level,int durationDays)
    {
        RequireDuration(durationDays);
        if(level<0||level>=ExperienceToNext42.Count)throw new DomainValidationException("Journey level is out of range.");
        // Apply ceiling per level, never once after summing the complete track.
        return checked((ExperienceToNext42[level]*Math.Min(durationDays,42)+41)/42);
    }

    public int Threshold(int level,int durationDays)
    {
        if(level<0||level>ExperienceToNext42.Count)throw new DomainValidationException("Journey level is out of range.");
        RequireDuration(durationDays);
        return Enumerable.Range(0,level).Sum(current=>Cost(current,durationDays));
    }

    public SeasonJourneyLevel Progress(int experience,int durationDays)
    {
        var maximum=Threshold(ExperienceToNext42.Count,durationDays);
        if(experience<0||experience>maximum)throw new DomainValidationException("Journey experience is outside its original track.");
        var level=0;var remaining=experience;
        while(level<ExperienceToNext42.Count&&remaining>=Cost(level,durationDays))remaining-=Cost(level++,durationDays);
        return new(level,remaining,level==ExperienceToNext42.Count?0:Cost(level,durationDays),experience,MainRewardLevels);
    }

    public int ReferenceAt(SeasonDefinition season,DateTimeOffset occurredAt)
    {
        var day=season.NaturalDayAt(occurredAt);
        // Short seasons use their actual level-20 threshold; the 21-day curve
        // remains a candidate calendar and does not multiply ordinary loot.
        return checked(Threshold(MainRewardLevels,season.DurationDays)*Math.Min(day,ReferenceDays)/ReferenceDays);
    }

    public SeasonJourneyGrant Grant(SeasonDefinition season,DateTimeOffset occurredAt,int experience,string completionKind)
    {
        if(!season.Contains(occurredAt))throw new DomainValidationException("Journey source is outside its original season.");
        var maximum=Threshold(ExperienceToNext42.Count,season.DurationDays);
        if(experience<0||experience>maximum)throw new DomainValidationException("Journey experience is outside its original track.");
        var basis=SourceExperience(completionKind);
        var available=maximum-experience;
        var creditedBase=Math.Min(available,basis);
        var reference=ReferenceAt(season,occurredAt);
        var bonus=completionKind=="Extracted"?0:Math.Min(basis*(CatchUpMultiplier-1),Math.Max(0,reference-experience-creditedBase));
        bonus=Math.Min(bonus,available-creditedBase);
        return new(creditedBase,bonus,creditedBase+bonus,experience+creditedBase+bonus);
    }

    public int SourceExperience(string kind)=>kind switch
    {
        "Outer"=>OuterExperience,"Middle"=>MiddleExperience,"Elite"=>EliteExperience,"Boss"=>BossExperience,
        "Extracted"=>ExtractionExperience,_=>throw new DomainValidationException("This event is not a journey experience source.")
    };

    public static string CellKind(ChaosMapCell cell)=>cell.IsBoss||cell.MonsterGroupId=="BOSS"?"Boss":
        cell.MonsterGroupId.StartsWith('E')?"Elite":cell.Layer switch
        {
            ChaosMapLayer.Outer=>"Outer",ChaosMapLayer.Middle=>"Middle",
            _=>throw new DomainValidationException("The cleared cell has no configured journey kind.")
        };

    public static int WeekAt(SeasonDefinition season,DateTimeOffset occurredAt)=>(season.NaturalDayAt(occurredAt)-1)/7+1;
    private static void RequireDuration(int days)
    {
        if(days is <SeasonDefinition.MinimumDurationDays or >SeasonDefinition.MaximumDurationDays)
            throw new DomainValidationException("Journey duration must match a valid original season.");
    }
}
