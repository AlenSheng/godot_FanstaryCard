namespace FantasyCard.Contracts.Progression;

public sealed record ActivityExchangeRequest(string SeasonId,string RuleId,long ExpectedAccountVersion,int Quantity=1,string? HeroClass=null);
public sealed record ActivityExchangeOptionResponse(string RuleId,int CostTokens,string RewardKind,int RewardCount,int EventLimit,int Used);
public sealed record ActivityRewardResponse(Guid RewardId,string SeasonId,string EventId,string RuleId,string RewardKind,int RewardAmount,
    string? HeroClass,int TokenCost,int Quantity,string State,DateTimeOffset CreatedAt,DateTimeOffset? ClaimedAt,bool CanClaim,string ConfigVersion);
public sealed record ActivityEventResponse(string SeasonId,string EventId,string State,DateTimeOffset StartsAt,DateTimeOffset EndsAt,
    int Earned,int Spent,int Available,int TokenCap,long AccountVersion,bool CanExchange,string ConfigVersion,
    IReadOnlyList<ActivityExchangeOptionResponse> Options,IReadOnlyList<ActivityRewardResponse> Rewards);
public sealed record SeasonActivitiesResponse(IReadOnlyList<ActivityEventResponse> Events,int? NextOffset=null);
public sealed record ActivityExchangeResponse(ActivityRewardResponse Reward,int TokensRemaining,long AccountVersion);
public sealed record ActivityClaimResponse(ActivityRewardResponse Reward,long BalanceAfter);
