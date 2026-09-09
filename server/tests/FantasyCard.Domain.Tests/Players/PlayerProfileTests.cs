using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Players;

public sealed class PlayerProfileTests
{
    [Fact]
    public void Create_NormalizesDisplayName()
    {
        var player = PlayerProfile.Create(Guid.NewGuid(), "  山海客  ", DateTimeOffset.UtcNow);

        Assert.Equal("山海客", player.DisplayName);
        Assert.Equal(1, player.Version);
    }

    [Theory]
    [InlineData("")]
    [InlineData("a")]
    [InlineData("abcdefghijklmnopqrstu")]
    public void Create_RejectsInvalidDisplayNameLength(string displayName)
    {
        Assert.Throws<DomainValidationException>(() =>
            PlayerProfile.Create(Guid.NewGuid(), displayName, DateTimeOffset.UtcNow));
    }

    [Fact]
    public void Update_ChangesClassAndIncrementsVersion()
    {
        var now = DateTimeOffset.UtcNow;
        var player = PlayerProfile.Create(Guid.NewGuid(), "焚弦者", now);

        player.Update(null, HeroClass.Mage, now.AddMinutes(1));

        Assert.Equal(HeroClass.Mage, player.SelectedClass);
        Assert.Equal(2, player.Version);
        Assert.Equal(now.AddMinutes(1), player.UpdatedAt);
    }
}
