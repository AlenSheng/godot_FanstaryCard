using FantasyCard.Domain.Bots;

namespace FantasyCard.Domain.Tests.Bots;

public sealed class BotDirectorTests
{
    [Fact]
    public void Human_duel_plays_medium_ai_cards()
    {
        var heal = new BotCard("water", false, true, false, 18);
        var fire = new BotCard("fire", true, false, false, 12);
        var decision = BotDirector.Decide(
            World(BotPhase.DuelingHuman, currentHp: 28, duelHand: [heal, fire]),
            new Random(1));

        Assert.Equal(BotActionKind.PlayDuelCards, decision.Kind);
        Assert.Contains(0, decision.DuelCardIndexes!);
    }

    [Fact]
    public void Pve_sim_waits_then_finishes_after_layer_timer()
    {
        var waiting = BotDirector.Decide(
            World(BotPhase.SimulatingPve, layer: CellLayer.Outer, pveElapsed: 10),
            new Random(1));
        var done = BotDirector.Decide(
            World(BotPhase.SimulatingPve, layer: CellLayer.Outer, pveElapsed: 32),
            new Random(1));

        Assert.Equal(BotActionKind.Wait, waiting.Kind);
        Assert.Equal(BotActionKind.FinishPveSim, done.Kind);
    }

    [Fact]
    public void Action_bar_heals_before_extract_or_move()
    {
        var decision = BotDirector.Decide(
            World(
                BotPhase.ActionBar,
                currentHp: 40,
                springAvailable: true,
                cellHasExtract: true,
                pveCleared: true),
            new Random(1));

        Assert.Equal(BotActionKind.StartHeal, decision.Kind);
        Assert.True(decision.UseSpring);
    }

    [Fact]
    public void Hurt_bot_on_extract_cell_often_extracts()
    {
        var extracts = 0;
        for (var seed = 0; seed < 80; seed++)
        {
            var decision = BotDirector.Decide(
                World(
                    BotPhase.ActionBar,
                    currentHp: 30,
                    layer: CellLayer.Outer,
                    cellHasExtract: true,
                    pveCleared: true),
                new Random(seed));
            if (decision.Kind == BotActionKind.StartExtract)
            {
                extracts++;
            }
        }

        Assert.InRange(extracts, 20, 80);
    }

    [Fact]
    public void Late_action_bar_moves_inward()
    {
        var cell = new GridCell(4, 0);
        var decision = BotDirector.Decide(
            World(
                BotPhase.ActionBar,
                cell: cell,
                raidElapsed: 500,
                pveCleared: true,
                legalNeighbors: BotRules.LegalNeighbors(cell)),
            new Random(3));

        Assert.Equal(BotActionKind.Move, decision.Kind);
        Assert.Equal(new GridCell(4, 1), decision.MoveTo);
    }

    [Fact]
    public void Arrival_starts_pve_when_uncleared()
    {
        var decision = BotDirector.Decide(World(BotPhase.Arriving, pveCleared: false), new Random(1));
        Assert.Equal(BotActionKind.StartPveSim, decision.Kind);
    }

    private static BotWorld World(
        BotPhase phase,
        GridCell? cell = null,
        CellLayer layer = CellLayer.Outer,
        int currentHp = 100,
        int maxHp = 100,
        bool bagFull = false,
        bool hasFragmentStack = false,
        bool springAvailable = false,
        bool hasPotion = false,
        bool cellHasExtract = false,
        bool pveCleared = false,
        int raidElapsed = 0,
        int pveElapsed = 0,
        int botDuelElapsed = 0,
        IReadOnlyList<GridCell>? legalNeighbors = null,
        IReadOnlyList<BotCard>? duelHand = null) =>
        new(
            phase,
            cell ?? new GridCell(4, 0),
            layer,
            currentHp,
            maxHp,
            bagFull,
            hasFragmentStack,
            springAvailable,
            hasPotion,
            cellHasExtract,
            pveCleared,
            raidElapsed,
            pveElapsed,
            botDuelElapsed,
            legalNeighbors ?? [],
            duelHand ?? []);
}
