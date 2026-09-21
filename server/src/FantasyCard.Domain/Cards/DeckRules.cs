using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Cards;

public enum CardRarity : short
{
    White = 1,
    Green = 2,
    Blue = 3,
    Purple = 4,
    Orange = 5
}

public sealed record OwnedCard(
    string CardId,
    HeroClass? HeroClass,
    CardRarity Rarity,
    int CopyCount,
    bool IsMonster);

public static class DeckRules
{
    public const int DeckSize = 20;

    public static void Validate(
        HeroClass heroClass,
        IReadOnlyList<string> cardIds,
        IReadOnlyDictionary<string, OwnedCard> ownedCards)
    {
        if (!Enum.IsDefined(heroClass))
        {
            throw new DomainValidationException("Unknown hero class.");
        }

        if (cardIds.Count != DeckSize)
        {
            throw new DomainValidationException($"A deck must contain exactly {DeckSize} cards.");
        }

        var requestedCopies = cardIds
            .GroupBy(cardId => cardId, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.Ordinal);
        var commonOrangeCount = 0;
        var classOrangeCount = 0;

        foreach (var (cardId, count) in requestedCopies)
        {
            if (count > 1)
            {
                throw new DomainValidationException("A deck cannot contain duplicate cards.");
            }

            if (!ownedCards.TryGetValue(cardId, out var card) || card.CopyCount < count)
            {
                throw new DomainValidationException($"Card '{cardId}' is not owned in the requested quantity.");
            }

            if (card.IsMonster)
            {
                throw new DomainValidationException("Monster cards cannot be added to a deck.");
            }

            if (card.HeroClass is not null && card.HeroClass != heroClass)
            {
                throw new DomainValidationException($"Card '{cardId}' belongs to another hero class.");
            }

            if (card.Rarity == CardRarity.Orange)
            {
                if (card.HeroClass is null)
                {
                    commonOrangeCount += count;
                }
                else
                {
                    classOrangeCount += count;
                }
            }
        }

        if (commonOrangeCount > 1 || classOrangeCount > 1)
        {
            throw new DomainValidationException("A deck can contain at most one common orange and one class orange card.");
        }
    }
}
