using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Cards;

public sealed class CardEconomyRulesTests
{
    [Theory]
    [InlineData("White", 10, 5, 41)]
    [InlineData("Green", 25, 8, 66)]
    [InlineData("Blue", 50, 12, 102)]
    [InlineData("Purple", 100, 20, 175)]
    [InlineData("Orange", 250, 40, 362)]
    public void Common_card_costs_and_cumulative_refunds_follow_Gdd(
        string quality, int craftCost, int firstUpgrade, int finalRefund)
    {
        var card = GameConfigCatalog.Current.Cards.First(item =>
            item.IsCodex && !item.InitiallyUnlocked && item.HeroClass is null && item.Quality == quality);
        Assert.Equal(craftCost, CardEconomyRules.CraftCost(card, false));
        Assert.Equal(craftCost, CardEconomyRules.CraftCost(card, true));
        Assert.Equal(firstUpgrade, CardEconomyRules.UpgradeSoulSpent(card.CardId, 1));
        Assert.Equal(craftCost / 4, CardEconomyRules.DismantleRefund(card, 0));
        Assert.Equal(finalRefund, CardEconomyRules.DismantleRefund(card, 5));
        Assert.Equal("WarriorSoul", CardEconomyRules.CurrencyKind(card));
    }

    [Theory]
    [InlineData(HeroClass.Priest, "PriestSoul")]
    [InlineData(HeroClass.Mage, "MageSoul")]
    [InlineData(HeroClass.Guardian, "GuardianSoul")]
    public void Class_souls_are_separate_and_starter_recraft_is_not_free(HeroClass heroClass, string currency)
    {
        var cards = GameConfigCatalog.Current.Cards.Where(item => item.IsCodex && item.HeroClass == heroClass).ToArray();
        Assert.All(cards, card => Assert.Equal(currency, CardEconomyRules.CurrencyKind(card)));
        var white = cards.First(item => item.Quality == "White");
        Assert.Equal(12, CardEconomyRules.CraftCost(white, false));
        Assert.Equal(3, CardEconomyRules.DismantleRefund(white, 0));
        Assert.Equal(63, CardEconomyRules.DismantleRefund(white, 5));
        Assert.Equal(80, CardEconomyRules.CraftCost(cards.First(item => item.Quality == "Purple"), false));
        Assert.Equal(240, CardEconomyRules.CraftCost(cards.Single(item => item.Quality == "Orange"), false));
    }

    [Fact]
    public void Every_codex_quality_matches_persisted_deck_enum()
    {
        Assert.All(GameConfigCatalog.Current.Cards.Where(item => item.IsCodex),
            card => Assert.Equal(card.Quality, ((CardRarity)card.Rarity).ToString()));
    }

    [Fact]
    public void Unknown_and_monster_cards_cannot_be_crafted()
    {
        Assert.Throws<DomainValidationException>(() => CardEconomyRules.GetCard("not-a-card"));
        var monster = GameConfigCatalog.Current.Cards.First(item => !item.IsCodex);
        Assert.Throws<DomainValidationException>(() => CardEconomyRules.GetCard(monster.CardId));
    }
}
