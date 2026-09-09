namespace FantasyCard.Domain.Bots;

public enum BotPhase : short
{
    Arriving = 0,
    SimulatingPve = 1,
    ChoosingLoot = 2,
    ActionBar = 3,
    Healing = 4,
    Extracting = 5,
    DuelingHuman = 6,
    SimulatingBotDuel = 7
}

public enum BotActionKind : short
{
    Wait = 0,
    Move = 1,
    StartPveSim = 2,
    FinishPveSim = 3,
    PickLoot = 4,
    StartHeal = 5,
    StartExtract = 6,
    PlayDuelCards = 7,
    FinishBotDuel = 8
}

public readonly record struct BotWorld(
    BotPhase Phase,
    GridCell Cell,
    CellLayer Layer,
    int CurrentHp,
    int MaxHp,
    bool BagFull,
    bool HasFragmentStack,
    bool SpringAvailable,
    bool HasPotion,
    bool CellHasExtract,
    bool PveCleared,
    int RaidElapsedSeconds,
    int PveSimElapsedSeconds,
    int BotDuelElapsedSeconds,
    IReadOnlyList<GridCell> LegalNeighbors,
    IReadOnlyList<BotCard> DuelHand);

public readonly record struct BotDecision(
    BotActionKind Kind,
    GridCell? MoveTo = null,
    ChoiceSlot? Loot = null,
    int[]? DuelCardIndexes = null,
    bool UseSpring = false);

/// <summary>
/// 房间 tick 用的机器人决策：优先级为真人 1v1 → 机机模拟 → PVE 模拟 → 三选一 → 回血 → 撤离 → 向内走。
/// </summary>
public static class BotDirector
{
    public static BotDecision Decide(BotWorld world, Random rng)
    {
        return world.Phase switch
        {
            BotPhase.DuelingHuman => PlayDuel(world),
            BotPhase.SimulatingBotDuel => FinishOrWaitBotDuel(world),
            BotPhase.SimulatingPve => FinishOrWaitPve(world),
            BotPhase.ChoosingLoot => new BotDecision(
                BotActionKind.PickLoot,
                Loot: BotRules.PickChoice(world.CurrentHp, world.MaxHp, world.BagFull, world.HasFragmentStack)),
            BotPhase.Healing or BotPhase.Extracting => new BotDecision(BotActionKind.Wait),
            BotPhase.Arriving => Arrive(world),
            BotPhase.ActionBar => ActOnBar(world, rng),
            _ => new BotDecision(BotActionKind.Wait)
        };
    }

    private static BotDecision PlayDuel(BotWorld world) =>
        new(
            BotActionKind.PlayDuelCards,
            DuelCardIndexes: BotRules.SelectDuelCards(
                world.DuelHand,
                BotRules.HpPercent(world.CurrentHp, world.MaxHp)));

    private static BotDecision FinishOrWaitBotDuel(BotWorld world) =>
        world.BotDuelElapsedSeconds >= BotRules.BotVsBotSimSeconds()
            ? new BotDecision(BotActionKind.FinishBotDuel)
            : new BotDecision(BotActionKind.Wait);

    private static BotDecision FinishOrWaitPve(BotWorld world) =>
        world.PveSimElapsedSeconds >= BotRules.PveSimSeconds(world.Layer)
            ? new BotDecision(BotActionKind.FinishPveSim)
            : new BotDecision(BotActionKind.Wait);

    private static BotDecision Arrive(BotWorld world) =>
        world.PveCleared
            ? new BotDecision(BotActionKind.Wait)
            : new BotDecision(BotActionKind.StartPveSim);

    private static BotDecision ActOnBar(BotWorld world, Random rng)
    {
        if (BotRules.ShouldHealOutOfCombat(world.CurrentHp, world.MaxHp, world.SpringAvailable, world.HasPotion))
        {
            return new BotDecision(
                BotActionKind.StartHeal,
                UseSpring: BotRules.PreferSpring(world.SpringAvailable));
        }

        if (world.CellHasExtract
            && world.PveCleared
            && BotRules.ShouldExtract(world.Layer, BotRules.HpPercent(world.CurrentHp, world.MaxHp), rng))
        {
            return new BotDecision(BotActionKind.StartExtract);
        }

        var legal = world.LegalNeighbors.Count > 0
            ? world.LegalNeighbors
            : BotRules.LegalNeighbors(world.Cell);
        var next = BotRules.PickNextCell(world.Cell, world.RaidElapsedSeconds, legal, rng);
        return new BotDecision(BotActionKind.Move, MoveTo: next);
    }
}
