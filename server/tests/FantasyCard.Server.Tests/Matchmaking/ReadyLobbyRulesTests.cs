using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Matchmaking;

namespace FantasyCard.Server.Tests.Matchmaking;

public sealed class ReadyLobbyRulesTests
{
    [Fact]
    public void CompleteWithBots_ReplacesEveryMissingSeatAndPreservesReadyHumans()
    {
        var human = new MatchPlayerAssignment(Guid.NewGuid(), false, HeroClass.Mage,
            ["common-01"], WeaponLevel: 7);
        var botIds = new[] { Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid() };

        var players = MatchmakingRepository.CompleteWithBots([human], botIds, seed: 53);

        Assert.Equal(4, players.Count);
        Assert.Same(human, players[0]);
        Assert.Equal(botIds.Order().ToArray(), players.Where(player => player.IsBot).Select(player => player.PlayerId).Order().ToArray());
        Assert.All(players.Where(player => player.IsBot), player =>
        {
            Assert.Equal(BotRules.AverageWeaponEnhance(new PartyWearSnapshot([], [7])), player.WeaponLevel);
            Assert.Equal(20, player.CardIds.Count);
        });
    }

    [Fact]
    public void CompleteWithBots_CanLaunchFourBotRoomWhenNobodyReadies()
    {
        var botIds = Enumerable.Range(0, 4).Select(_ => Guid.NewGuid()).Order().ToArray();

        var players = MatchmakingRepository.CompleteWithBots([], botIds, seed: 59);

        Assert.Equal(4, players.Count);
        Assert.All(players, player => Assert.True(player.IsBot));
        Assert.All(Enum.GetValues<HeroClass>(), heroClass =>
            Assert.Contains(players, player => player.HeroClass == heroClass));
        Assert.True(players.GroupBy(player => player.HeroClass).Max(group => group.Count()) <= 2);
    }
}
