using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed record MonsterCardDecisionReceipt(string RequestId, Guid CandidateId, bool Accept, Guid? ReplaceId);
public sealed record MonsterCardPoolSnapshot(
    IReadOnlyList<CombatCardInstance> Pending,
    IReadOnlyList<CombatCardInstance> Active,
    IReadOnlyList<string> GrantedSources,
    IReadOnlyList<MonsterCardDecisionReceipt> Receipts);

/// <summary>Bounded, server-issued offers. Not a client-owned inventory.</summary>
public sealed class MonsterCardPool
{
    private const int MaxEntries = 256;
    private readonly List<CombatCardInstance> _pending = [];
    private readonly List<CombatCardInstance> _active = [];
    private readonly HashSet<string> _sources = new(StringComparer.Ordinal);
    private readonly List<MonsterCardDecisionReceipt> _receipts = [];
    public IReadOnlyList<CombatCardInstance> Pending => _pending;
    public IReadOnlyList<CombatCardInstance> Active => _active;

    public void Offer(string source, CombatCardInstance card)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(source);
        ArgumentNullException.ThrowIfNull(card);
        if (_sources.Contains(source)) return;
        if (_sources.Count >= MaxEntries || _pending.Count >= MaxEntries || source.Length > 200 ||
            card.InstanceId == Guid.Empty || card.Level != 0 ||
            _pending.Concat(_active).Any(existing => existing.InstanceId == card.InstanceId))
            throw new DomainValidationException("Monster offer is invalid or the room limit was exceeded.");
        _sources.Add(source);
        _pending.Add(card);
    }

    public bool IsReplay(string requestId, Guid candidateId, bool accept, Guid? replacement)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(requestId);
        if (requestId.Length > 80) throw new DomainValidationException("Monster decision request id is too long.");
        var receipt = _receipts.SingleOrDefault(value => value.RequestId == requestId);
        if (receipt is null) return false;
        if (receipt.CandidateId != candidateId || receipt.Accept != accept || receipt.ReplaceId != replacement)
            throw new DomainValidationException("The request id belongs to a different monster decision.");
        return true;
    }

    public void Decide(CombatDeck deck, int capacity, string requestId, Guid candidateId, bool accept, Guid? replacement)
    {
        if (IsReplay(requestId, candidateId, accept, replacement)) return;
        if (capacity is < 1 or > 8 || _receipts.Count >= MaxEntries)
            throw new DomainValidationException("Monster decision limit was exceeded.");
        var candidate = _pending.SingleOrDefault(card => card.InstanceId == candidateId)
            ?? throw new DomainValidationException("This monster candidate is not owned or is no longer available.");
        if (!accept && replacement is not null)
            throw new DomainValidationException("Skipping a candidate cannot remove another card.");
        if (accept)
        {
            if (replacement is null && _active.Count >= capacity)
                throw new DomainValidationException("Choose an active monster card to replace, or skip.");
            if (replacement is not null && !_active.Any(card => card.InstanceId == replacement))
                throw new DomainValidationException("Only an active monster card can be replaced.");
            // Validates every pile before changing it. No compensating draw, no shuffle.
            deck.ReplaceMonsterInstance(replacement, candidate);
            if (replacement is not null) _active.RemoveAll(card => card.InstanceId == replacement);
            _active.Add(candidate);
        }
        _pending.Remove(candidate);
        _receipts.Add(new(requestId, candidateId, accept, replacement));
    }

    public void DiscardPending() => _pending.Clear();
    public void EndRun(CombatDeck deck)
    {
        foreach (var card in _active) deck.RemoveMonsterInstance(card.InstanceId);
        _active.Clear();
        _pending.Clear();
    }

    public MonsterCardPoolSnapshot Capture() => new(_pending.ToArray(), _active.ToArray(),
        _sources.Order(StringComparer.Ordinal).ToArray(), _receipts.ToArray());

    public void Restore(MonsterCardPoolSnapshot snapshot, CombatDeck deck, int capacity)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var all = snapshot.Pending.Concat(snapshot.Active).ToArray();
        var deckCards = deck.Hand.Concat(deck.Library).Concat(deck.Discard).ToArray();
        if (snapshot.Pending.Count > MaxEntries || snapshot.Active.Count > capacity ||
            snapshot.GrantedSources.Count > MaxEntries || snapshot.Receipts.Count > MaxEntries ||
            all.Any(card => card.InstanceId == Guid.Empty || card.Level != 0) ||
            all.Select(card => card.InstanceId).Distinct().Count() != all.Length ||
            snapshot.Active.Any(card => deckCards.Count(value => value == card) != 1) ||
            snapshot.Pending.Any(card => deckCards.Any(value => value.InstanceId == card.InstanceId)) ||
            snapshot.GrantedSources.Any(string.IsNullOrWhiteSpace) ||
            snapshot.GrantedSources.Distinct(StringComparer.Ordinal).Count() != snapshot.GrantedSources.Count ||
            snapshot.Receipts.Any(value => string.IsNullOrWhiteSpace(value.RequestId) || value.RequestId.Length > 80) ||
            snapshot.Receipts.Select(value => value.RequestId).Distinct(StringComparer.Ordinal).Count() != snapshot.Receipts.Count)
            throw new DomainValidationException("Monster pool snapshot is invalid.");
        _pending.Clear(); _pending.AddRange(snapshot.Pending);
        _active.Clear(); _active.AddRange(snapshot.Active);
        _sources.Clear(); _sources.UnionWith(snapshot.GrantedSources);
        _receipts.Clear(); _receipts.AddRange(snapshot.Receipts);
    }
}
