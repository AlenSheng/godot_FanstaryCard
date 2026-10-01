using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class FenxianRoomDrawLedgerTests
{
    private static readonly CombatCardCatalog Catalog = new([
        new("core", new(ElementalDamage: 8, Element: CardElement.Fire)),
        new("bonus", new(ResonanceBonus: 1)),
        new("draw", new(ImmediateDraw: 3)),
        new("filler", new())]);
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch;

    // Hand begins full. Requests, actual immediate acquisitions and charge
    // conversions are independently specified; no hand-count arithmetic model
    // substitutes for the actual Room -> PlayerCombatState -> CombatDeck path.
    [Theory]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 1, 0, 0d, 0, 0, 0, .18)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 1, 0, 0d, 0, 0, 0, .18)]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 1, 4, 0d, 2, 1, 0, .50)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 1, 4, 0d, 0, 0, 0, .50)]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 1, 4, .90, 2, 0, 1, .40)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 1, 4, .90, 0, 0, 1, .40)]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 3, 0, 0d, 1, 1, 0, .42)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 3, 0, 0d, 1, 1, 0, .42)]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 3, 0, .90, 1, 1, 1, .32)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 3, 0, .90, 1, 1, 1, .32)]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 5, 0, 0d, 2, 2, 0, .50)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 5, 0, 0d, 2, 2, 0, .50)]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 5, 0, .90, 2, 2, 1, .40)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 5, 0, .90, 2, 2, 1, .40)]
    public void Full_hand_R1_R3_R5_preserves_requested_draw_and_accounts_for_actual_acquisitions(
        FenxianImmediateDrawPolicy policy, int coreCount, int priorCombo, double initialCharge,
        int immediateRequested, int immediateAcquired, int chargeAcquired, double remainingCharge)
    {
        var (room, player) = Create(policy, coreCount, initialCharge);
        player.Combat.SetFenxian(CardElement.Fire, priorCombo);
        var before = player.Combat.Deck.Capture();
        var selected = before.Hand.Take(coreCount).Select(card => card.InstanceId).ToArray();
        var unchanged = room.Capture();
        var preview = room.PreviewCards(player.PlayerId, player.Pve!.BattleId, "ledger-target", selected, room.Revision, Now);
        Assert.Equivalent(unchanged, room.Capture(), strict: true);
        var result = room.PlayCards(player.PlayerId, player.Pve.BattleId, "ledger-target", selected, room.Revision, Now);
        Assert.Equivalent(preview with { RoomRevision = result.RoomRevision }, result, strict: true);
        Assert.Equal(coreCount, result.CoreCount);
        Assert.Equal(immediateRequested, result.ImmediateDraw);
        AssertLedger(player, before, selected, immediateAcquired + chargeAcquired);
        Assert.Equal(remainingCharge, player.Combat.Deck.DrawCharge, 6);
        Assert.Equal(chargeAcquired, initialCharge + result.DrawCharge - player.Combat.Deck.DrawCharge, 6);
        var acquired = player.Combat.Deck.Hand.Count(card => before.Library.Contains(card));
        Assert.Equal(immediateAcquired, acquired - chargeAcquired);
    }

    [Theory]
    [InlineData(FenxianImmediateDrawPolicy.CurrentRhythm, 2, 2)]
    [InlineData(FenxianImmediateDrawPolicy.CoreCardsSpent, 0, 0)]
    public void Resonance_bonus_does_not_increase_core_count_or_the_cards_spent_draw_tier(
        FenxianImmediateDrawPolicy policy, int requested, int acquired)
    {
        var (room, player) = Create(policy, 1, 0);
        player.Combat.SetFenxian(CardElement.Fire, 4);
        var deck = player.Combat.Deck.Capture();
        player.Combat.Deck.Restore(deck with { Hand = deck.Hand.Select((card, index) => index == 1 ? card with { CardId = "bonus" } : card).ToArray() });
        var before = player.Combat.Deck.Capture();
        var selected = before.Hand.Take(2).Select(card => card.InstanceId).ToArray();
        var result = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "ledger-target", selected, room.Revision, Now);
        Assert.Equal(1, result.CoreCount);
        Assert.Equal(1.2, result.ResonanceMultiplier, 6);
        Assert.Equal(requested, result.ImmediateDraw);
        Assert.Equal(5, player.Combat.FenxianChargeLevel);
        AssertLedger(player, before, selected, acquired);
    }

    [Fact]
    public void Pure_bonus_resets_fenxian_and_immediate_draw_remains_a_request_when_hand_fills()
    {
        var (room, player) = Create(FenxianImmediateDrawPolicy.CurrentRhythm, 0, 0);
        player.Combat.SetFenxian(CardElement.Fire, 4);
        foreach (var cardId in new[] { "bonus", "draw" })
        {
            var deck = player.Combat.Deck.Capture();
            player.Combat.Deck.Restore(deck with { Hand = deck.Hand.Select((card, index) => index == 0 ? card with { CardId = cardId } : card).ToArray() });
            var before = player.Combat.Deck.Capture();
            var selected = new[] { before.Hand[0].InstanceId };
            var result = room.PlayCards(player.PlayerId, player.Pve!.BattleId, "ledger-target", selected, room.Revision, Now);
            Assert.Equal(0, result.CoreCount);
            Assert.Equal(0, player.Combat.FenxianCombo);
            Assert.Equal(cardId == "draw" ? 3 : 0, result.ImmediateDraw);
            // The preceding bonus left four cards; playing draw now opens two
            // slots, so the request for three actually acquires two cards.
            AssertLedger(player, before, selected, cardId == "draw" ? 2 : 0);
        }
    }

    private static void AssertLedger(RoomPlayerState player, CombatDeckSnapshot before, Guid[] spent, int acquired)
    {
        var after = player.Combat.Deck.Capture();
        Assert.Equal(before.Hand.Count - spent.Length + acquired, after.Hand.Count);
        Assert.Equal(before.Library.Count - acquired, after.Library.Count);
        Assert.Equal(before.Discard.Count + spent.Length, after.Discard.Count);
        Assert.Equal(acquired, after.Hand.Count(card => before.Library.Contains(card)));
        Assert.All(spent, id => Assert.Contains(after.Discard, card => card.InstanceId == id));
        Assert.Equal(before.Hand.Concat(before.Library).Concat(before.Discard).Select(card => card.InstanceId).Order(),
            after.Hand.Concat(after.Library).Concat(after.Discard).Select(card => card.InstanceId).Order());
    }

    private static (BattleRoom Room, RoomPlayerState Player) Create(FenxianImmediateDrawPolicy policy, int coreCount, double charge)
    {
        var room = new BattleRoom(Guid.NewGuid(), "draw-ledger", Catalog, 23);
        var target = new MonsterCombatState("ledger-target", 10000, 10000, 0, TimeSpan.FromSeconds(4),
            [new(MonsterIntentKind.Charge, 0, CardElement.None)]);
        var player = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, Enumerable.Repeat("core", 20).ToArray(),
            new(Guid.NewGuid(), null, [target])));
        player.Combat.Restore(player.Combat.Capture() with { FenxianPolicy = policy });
        player.Combat.Deck.Restore(new(Enumerable.Range(0, 5).Select(i => new CombatCardInstance(Guid.NewGuid(), i < coreCount ? "core" : "filler")).ToArray(),
            Enumerable.Range(0, 20).Select(_ => new CombatCardInstance(Guid.NewGuid(), "filler")).ToArray(), [], charge));
        return (room, player);
    }
}
