using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Combat;

public sealed class PausedDrawLedgerTests(ITestOutputHelper output)
{
    [Fact]
    public void Candidate_passive_alone_cannot_sustain_cards_without_natural_time()
    {
        var state = new PlayerCombatState(HeroClass.Mage,Enumerable.Repeat("C01",20).ToArray(),new Random(41),
            fenxianImmediateDrawPolicy:FenxianImmediateDrawPolicy.CoreCardsSpent);
        var original = Instances(state);
        var actions = 0;
        var ledger = new List<object>();
        while (state.Deck.Hand.Count>0 && actions<100)
        {
            var played = new[] { state.Deck.Hand[0] };
            state.Deck.DiscardPlayed(played);
            var passive = state.UpdateFenxian(CardElement.Fire,1);
            state.AddDrawCharge(passive.Charge);
            state.DrawImmediate(passive.Draw);
            Assert.Equal(0,passive.Draw);
            Assert.Equal(original,Instances(state));
            ledger.Add(new { action=actions+1,spent=1,requestedPassiveDraw=passive.Draw,passiveCharge=passive.Charge,
                hand=state.Deck.Hand.Count,library=state.Deck.Library.Count,discard=state.Deck.Discard.Count,totalInstances=20,naturalSeconds=0 });
            actions++;
        }
        Assert.Empty(state.Deck.Hand);
        Assert.InRange(actions,1,99);
        output.WriteLine($"PR13_DRAW passive-only actions={actions} naturalSeconds=0 instances=20 outcome=Exhausted localRepeatedCardControl=true");
        output.WriteLine("PR13_DRAW_LEDGER " + System.Text.Json.JsonSerializer.Serialize(ledger));
    }

    [Fact]
    public void Printed_double_draw_can_form_a_local_loop_and_action_cap_stays_unfinished()
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var state = new PlayerCombatState(HeroClass.Mage,Enumerable.Repeat("GP21",20).ToArray(),new Random(41),
            fenxianImmediateDrawPolicy:FenxianImmediateDrawPolicy.CoreCardsSpent);
        var original=Instances(state);var actualDraws=0;var requestedDraws=0;
        var ledger = new List<object>();
        for (var action=0;action<100;action++)
        {
            var card=state.Deck.Hand[0];var draft=CombatResolver.Resolve([catalog.Get(card.CardId)],state);
            Assert.Equal(2,draft.ImmediateDraw);
            state.Deck.DiscardPlayed([card]);var before=state.Deck.Hand.Count;
            state.AddDrawCharge(draft.DrawCharge);state.DrawImmediate(draft.ImmediateDraw);
            var passive=state.UpdateFenxian(draft.CoreElement,draft.CoreCount);
            state.AddDrawCharge(passive.Charge);state.DrawImmediate(passive.Draw);
            requestedDraws+=draft.ImmediateDraw+passive.Draw;actualDraws+=state.Deck.Hand.Count-before;
            Assert.NotEmpty(state.Deck.Hand);Assert.Equal(original,Instances(state));
            ledger.Add(new { action=action+1,spent=1,printedImmediateDraw=draft.ImmediateDraw,passiveRequestedDraw=passive.Draw,
                actualDraw=state.Deck.Hand.Count-before,hand=state.Deck.Hand.Count,library=state.Deck.Library.Count,discard=state.Deck.Discard.Count,totalInstances=20,naturalSeconds=0 });
        }
        Assert.True(actualDraws<requestedDraws);
        Assert.Equal(5,state.Deck.Hand.Count);
        output.WriteLine($"PR13_DRAW printed-double-draw actions=100 requested={requestedDraws} actual={actualDraws} naturalSeconds=0 outcome=ActionCapUnfinished source=GP21 localRepeatedCardControl=true legalPublishedDeckClaim=false");
        output.WriteLine("PR13_DRAW_LEDGER " + System.Text.Json.JsonSerializer.Serialize(ledger));
    }

    private static Guid[] Instances(PlayerCombatState state) =>
        state.Deck.Hand.Concat(state.Deck.Library).Concat(state.Deck.Discard).Select(c=>c.InstanceId).Order().ToArray();
}
