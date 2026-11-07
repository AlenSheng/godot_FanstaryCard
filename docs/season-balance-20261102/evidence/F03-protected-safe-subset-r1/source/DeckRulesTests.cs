using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Cards;

public sealed class DeckRulesTests
{
    [Fact]
    public void Validate_AcceptsTwentyOwnedClassAndCommonCards()
    {
        var cards = Enumerable.Range(1, 20)
            .Select(index => new OwnedCard(
                $"card-{index}",
                index <= 7 ? HeroClass.Mage : null,
                CardRarity.White,
                1,
                false))
            .ToDictionary(card => card.CardId, StringComparer.Ordinal);

        DeckRules.Validate(HeroClass.Mage, cards.Keys.ToArray(), cards);
    }

    [Fact]
    public void Validate_RejectsCardFromAnotherClass()
    {
        var cards = Enumerable.Range(1, 20)
            .Select(index => new OwnedCard(
                $"card-{index}",
                index == 1 ? HeroClass.Priest : null,
                CardRarity.White,
                1,
                false))
            .ToDictionary(card => card.CardId, StringComparer.Ordinal);

        Assert.Throws<DomainValidationException>(() =>
            DeckRules.Validate(HeroClass.Mage, cards.Keys.ToArray(), cards));
    }

    [Fact]
    public void Validate_RejectsMoreThanOneCommonOrange()
    {
        var cards = Enumerable.Range(1, 20)
            .Select(index => new OwnedCard(
                $"card-{index}",
                null,
                index <= 2 ? CardRarity.Orange : CardRarity.White,
                1,
                false))
            .ToDictionary(card => card.CardId, StringComparer.Ordinal);

        Assert.Throws<DomainValidationException>(() =>
            DeckRules.Validate(HeroClass.Guardian, cards.Keys.ToArray(), cards));
    }

    [Fact]
    public void Validate_RejectsIncompleteDeck()
    {
        var cards = Enumerable.Range(1, 19)
            .Select(index => new OwnedCard($"card-{index}", null, CardRarity.White, 1, false))
            .ToDictionary(card => card.CardId, StringComparer.Ordinal);

        var error = Assert.Throws<DomainValidationException>(() =>
            DeckRules.Validate(HeroClass.Mage, cards.Keys.ToArray(), cards));

        Assert.Contains("exactly 20", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Validate_RejectsDuplicateCardNames()
    {
        var cards = Enumerable.Range(1, 20)
            .Select(index => new OwnedCard($"card-{index}", null, CardRarity.White, 1, false))
            .ToDictionary(card => card.CardId, StringComparer.Ordinal);
        var deck = cards.Keys.ToArray();
        deck[1] = deck[0];

        Assert.Throws<DomainValidationException>(() => DeckRules.Validate(HeroClass.Mage, deck, cards));
    }
}
