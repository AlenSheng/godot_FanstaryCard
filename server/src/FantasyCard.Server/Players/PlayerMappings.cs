using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Players;

namespace FantasyCard.Server.Players;

public static class PlayerMappings
{
    public static PlayerProfileResponse ToResponse(this PlayerProfile profile) =>
        new(
            profile.UserId,
            profile.DisplayName,
            profile.SelectedClass is null ? null : (HeroClassDto)(int)profile.SelectedClass.Value,
            profile.Version,
            profile.CreatedAt,
            profile.UpdatedAt);

    public static HeroClass? ToDomain(this HeroClassDto? heroClass) =>
        heroClass is null ? null : (HeroClass)(int)heroClass.Value;
}
