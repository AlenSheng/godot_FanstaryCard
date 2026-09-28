using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Combat;

public sealed class CombatDeck
{
    public const int HandLimit = 5;
    private List<CombatCardInstance> _hand = [];
    private List<CombatCardInstance> _library = [];
    private List<CombatCardInstance> _discard = [];

    public IReadOnlyList<CombatCardInstance> Hand => _hand;
    public IReadOnlyList<CombatCardInstance> Library => _library;
    public IReadOnlyList<CombatCardInstance> Discard => _discard;
    public double DrawCharge { get; private set; }

    public static CombatDeck Create(IReadOnlyList<string> cardIds, Random random, IReadOnlyList<int>? cardLevels = null)
    {
        ArgumentNullException.ThrowIfNull(cardIds);
        ArgumentNullException.ThrowIfNull(random);
        if (cardIds.Count == 0)
        {
            throw new DomainValidationException("A combat deck cannot be empty.");
        }
        if (cardLevels is not null && (cardLevels.Count != cardIds.Count || cardLevels.Any(level => level is < 0 or > 5)))
            throw new DomainValidationException("Card levels must match the deck slots and be between zero and five.");

        var deck = new CombatDeck
        {
            _library = cardIds
                .Select((cardId, index) => new CombatCardInstance(Guid.CreateVersion7(), cardId, cardLevels?[index] ?? 0))
                .ToList()
        };
        Shuffle(deck._library, random);
        deck.DrawOpeningHand();
        return deck;
    }

    public CombatDeckSnapshot Capture() =>
        new(
            _hand.ToArray(),
            _library.ToArray(),
            _discard.ToArray(),
            DrawCharge);

    public void Restore(CombatDeckSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        if (snapshot.Hand.Concat(snapshot.Library).Concat(snapshot.Discard).Any(card => !ValidCard(card)))
            throw new DomainValidationException("A combat deck snapshot contains an invalid card level or element override.");
        _hand = snapshot.Hand.ToList();
        _library = snapshot.Library.ToList();
        _discard = snapshot.Discard.ToList();
        DrawCharge = snapshot.DrawCharge;
    }

    public void ResetForDuel(Random random)
    {
        ArgumentNullException.ThrowIfNull(random);
        var pool = _hand.Concat(_library).Concat(_discard).ToList();
        _hand = [];
        _discard = [];
        _library = pool;
        DrawCharge = 0;
        Shuffle(_library, random);
        DrawOpeningHand();
    }

    public IReadOnlyList<CombatCardInstance> SelectFromHand(IReadOnlyList<Guid> instanceIds)
    {
        ArgumentNullException.ThrowIfNull(instanceIds);
        if (instanceIds.Count is < 1 or > HandLimit || instanceIds.Distinct().Count() != instanceIds.Count)
        {
            throw new DomainValidationException("A play must contain 1-5 distinct card instances.");
        }

        var byId = _hand.ToDictionary(card => card.InstanceId);
        var selected = new List<CombatCardInstance>(instanceIds.Count);
        foreach (var instanceId in instanceIds)
        {
            if (!byId.TryGetValue(instanceId, out var card))
            {
                throw new DomainValidationException($"Card instance '{instanceId}' is not in hand.");
            }
            selected.Add(card);
        }
        return selected;
    }

    public void DiscardPlayed(IReadOnlyList<CombatCardInstance> selected)
    {
        foreach (var card in selected)
        {
            if (!_hand.Remove(card))
            {
                throw new DomainValidationException($"Card instance '{card.InstanceId}' left the hand before resolution.");
            }
        }
        _discard.AddRange(selected);
    }

    public void AddToDiscard(CombatCardInstance card)
    {
        ArgumentNullException.ThrowIfNull(card);
        if (!ValidCard(card)) throw new DomainValidationException("The card instance is invalid.");
        if (_hand.Concat(_library).Concat(_discard).Any(existing => existing.InstanceId == card.InstanceId))
            throw new DomainValidationException("A card instance cannot enter the combat pool twice.");
        _discard.Add(card);
    }

    public void ReplaceMonsterInstance(Guid? replacedId, CombatCardInstance candidate)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        var current = Capture();
        var all = current.Hand.Concat(current.Library).Concat(current.Discard).ToArray();
        if (!ValidCard(candidate) || candidate.InstanceId == Guid.Empty ||
            all.Any(card => card.InstanceId == candidate.InstanceId) ||
            replacedId is not null && all.Count(card => card.InstanceId == replacedId) != 1)
            throw new DomainValidationException("Monster replacement contains invalid or duplicate instances.");
        Restore(new(
            current.Hand.Where(card => card.InstanceId != replacedId).ToArray(),
            current.Library.Where(card => card.InstanceId != replacedId).ToArray(),
            current.Discard.Where(card => card.InstanceId != replacedId).Append(candidate).ToArray(),
            current.DrawCharge));
    }

    public void RemoveMonsterInstance(Guid instanceId)
    {
        _hand.RemoveAll(card => card.InstanceId == instanceId);
        _library.RemoveAll(card => card.InstanceId == instanceId);
        _discard.RemoveAll(card => card.InstanceId == instanceId);
    }

    public void AddCharge(double amount, Random random)
    {
        if (amount <= 0)
        {
            return;
        }

        DrawCharge += amount;
        while (DrawCharge >= 1)
        {
            if (_hand.Count >= HandLimit)
            {
                DrawCharge = 0;
                return;
            }

            DrawCharge -= 1;
            DrawOne(random);
        }
    }

    public void DrawImmediate(int count, Random random)
    {
        for (var index = 0; index < count && _hand.Count < HandLimit; index++)
        {
            DrawOne(random);
        }
    }

    private void DrawOpeningHand()
    {
        for (var index = 0; index < 3 && _library.Count > 0; index++)
        {
            _hand.Add(_library[0]);
            _library.RemoveAt(0);
        }
    }

    private void DrawOne(Random random)
    {
        if (_library.Count == 0)
        {
            if (_discard.Count == 0)
            {
                return;
            }

            _library = _discard;
            _discard = [];
            Shuffle(_library, random);
        }

        _hand.Add(_library[0]);
        _library.RemoveAt(0);
    }

    private static void Shuffle(List<CombatCardInstance> values, Random random)
    {
        for (var remaining = values.Count; remaining > 1;)
        {
            var index = random.Next(remaining--);
            (values[index], values[remaining]) = (values[remaining], values[index]);
        }
    }

    private static bool ValidCard(CombatCardInstance card) => card.Level is >= 0 and <= 5 &&
        (card.ElementOverride is null || card.CardId == "M-BOXSPIRIT" && card.Level == 0 && Enum.IsDefined(card.ElementOverride.Value));
}
