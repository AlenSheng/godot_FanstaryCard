namespace FantasyCard.Contracts.Progression;

public sealed record JourneySeasonResponse(string SeasonId,string State,string ConfigVersion,DateTimeOffset StartsAt,DateTimeOffset EndsAt);
public sealed record JourneyLevelResponse(int Level,int RequiredExperience,int CumulativeExperience,string Stage,bool Reached);
public sealed record WeeklyContractResponse(string ContractId,int Week,string CompletionKind,int Target,int Progress,
    int ExperienceReward,int ExperienceCredited,DateTimeOffset OpensAt,DateTimeOffset? CompletedAt,string State);
public sealed record SeasonJourneyResponse(string State,string? SeasonId,string? ConfigVersion,DateTimeOffset? StartsAt,DateTimeOffset? EndsAt,
    int DurationDays,int Day,int Experience,int Level,int ExperienceIntoLevel,int ExperienceToNext,int MaximumExperience,
    int MainRewardLevels,int ReferenceExperience,int MaximumCatchUpMultiplier,bool CatchUpActive,long Version,
    IReadOnlyList<WeeklyContractResponse> Contracts,IReadOnlyList<JourneyLevelResponse> Levels,
    IReadOnlyList<JourneySeasonResponse> Seasons,int? NextOffset=null);
