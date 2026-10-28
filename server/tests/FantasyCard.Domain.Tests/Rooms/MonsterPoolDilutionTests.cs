using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class MonsterPoolDilutionTests(ITestOutputHelper output)
{
    [Fact]
    public void Actual_pool_growth_separates_printed_power_from_key_card_shuffle_latency()
    {
        var deck = BaseDeck(); var pool = new MonsterCardPool();
        for (var i = 0; i < 5; i++)
        {
            var monster = new CombatCardInstance(Guid.NewGuid(), "M-FIREBAT");
            pool.Offer("actual-controlled-kill-" + i, monster);
            pool.Decide(deck, 5, "actual-decision-" + i, monster.InstanceId, true, null);
        }
        var baseline = BaseDeck(); var catalog = CombatCardCatalog.CreatePrototype();
        var a = Cards(baseline); var b = Cards(deck);
        var beforePower = a.Sum(c => catalog.Get(c.CardId).Effect.ElementalDamage + catalog.Get(c.CardId).Effect.DirectDamage);
        var afterPower = b.Sum(c => catalog.Get(c.CardId).Effect.ElementalDamage + catalog.Get(c.CardId).Effect.DirectDamage);
        var before = MeanKeyDraws(a); var after = MeanKeyDraws(b);
        Assert.Equal(20, a.Length); Assert.Equal(25, b.Length); Assert.True(afterPower > beforePower); Assert.True(after > before);
        output.WriteLine("PR13_POOL " + JsonSerializer.Serialize(new { seeds = 1000, seedStart = 100001,
            baselinePool = a.Length, expandedPool = b.Length, printedPowerBefore = beforePower, printedPowerAfter = afterPower,
            keyDrawsBefore = before, keyDrawsAfter = after, scope = "actual offer/accept and native discard shuffle, isolated recycle control; not full encounter benefit or three-round experiment" }));
    }

    [Fact]
    public void Capacity_five_keeps_key_draws_faster_than_ten_automatic_cards_but_requires_choices()
    {
        var capped = BaseDeck(); var automatic = BaseDeck(); var pool = new MonsterCardPool();
        for (var i = 0; i < 10; i++)
        {
            var monster = new CombatCardInstance(Guid.NewGuid(), "M-FIREBAT");
            automatic.AddToDiscard(new(Guid.NewGuid(), "M-FIREBAT"));
            pool.Offer("controlled-kill-" + i, monster);
            pool.Decide(capped, 5, "decision-" + i, monster.InstanceId, true,
                pool.Active.Count < 5 ? null : pool.Active[0].InstanceId);
        }
        var cappedDraws = MeanKeyDraws(Cards(capped)); var autoDraws = MeanKeyDraws(Cards(automatic));
        Assert.Equal(5, pool.Active.Count); Assert.Equal(10, pool.Capture().Receipts.Count);
        Assert.Equal(25, Cards(capped).Length); Assert.Equal(30, Cards(automatic).Length); Assert.True(cappedDraws < autoDraws);
        output.WriteLine("PR13_POOL " + JsonSerializer.Serialize(new { seeds = 1000, seedStart = 100001,
            capacity = 5, cappedKeyDraws = cappedDraws, automaticKeyDraws = autoDraws, decisionInterruptions = 10,
            automaticDecisionInterruptions = 0, observedHumanInterruptionMilliseconds = (double?)null,
            humanTimingUnavailableReason = "no_human_participation", productionActivation = false }));
    }

    private static CombatDeck BaseDeck() => CombatDeck.Create(Enumerable.Range(1, 20).Select(i => $"C{i:D2}").ToArray(), new Random(31));
    private static CombatCardInstance[] Cards(CombatDeck deck) => deck.Hand.Concat(deck.Library).Concat(deck.Discard).ToArray();
    private static double MeanKeyDraws(CombatCardInstance[] cards)
    {
        var all = 0;
        for (var seed = 100001; seed < 101001; seed++)
        {
            var deck = BaseDeck(); deck.Restore(new([], [], cards, 0)); var random = new Random(seed);
            var found = false;
            for (var draws = 1; draws <= cards.Length; draws++)
            {
                deck.DrawImmediate(1, random);
                if (deck.Hand[0].CardId == "C01") { all += draws; found = true; break; }
                deck.DiscardPlayed([deck.Hand[0]]);
            }
            Assert.True(found);
        }
        return (double)all / 1000;
    }
}
