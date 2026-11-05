namespace FantasyCard.Contracts.Progression;

public sealed record JourneyRewardResponse(Guid? RewardId,string SeasonId,string ConfigVersion,int Level,int RequiredExperience,
    string Kind,int Amount,string Ownership,bool RequiresClassChoice,string? CosmeticId,string State,bool CanClaim,
    string? HeroClass=null,DateTimeOffset? EarnedAt=null,DateTimeOffset? ClaimedAt=null);
public sealed record JourneyRewardsResponse(string State,string? SeasonId,string? ConfigVersion,IReadOnlyList<JourneyRewardResponse> Rewards);
public sealed record JourneyClaimRequest(string SeasonId,string? HeroClass=null);
public sealed record JourneyClaimResponse(JourneyRewardResponse Reward,IReadOnlyList<ShopGrantResponse> Grants,
    long? BalanceAfter=null,bool CosmeticNewlyOwned=false);
public sealed record OwnedCosmeticResponse(string CosmeticId,string Kind,string NameKey,string DescriptionKey,
    string SourceSeasonId,string ConfigVersion,DateTimeOffset AcquiredAt);
public sealed record CosmeticSelectionResponse(string? AvatarFrameId,string? CardBackId,string? TitleId,long Version);
public sealed record CosmeticsResponse(IReadOnlyList<OwnedCosmeticResponse> Owned,CosmeticSelectionResponse Selection);
public sealed record CosmeticSelectionRequest(string Slot,string? CosmeticId,long ExpectedVersion);
