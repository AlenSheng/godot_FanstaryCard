using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Bots;

public enum ItemQuality : short
{
    White = 1,
    Green = 2,
    Blue = 3,
    Purple = 4,
    Orange = 5
}

public enum CellLayer : short
{
    Outer = 0,
    Mid = 1,
    Elite = 2,
    Boss = 3
}

public enum ChoiceSlot : short
{
    Gear = 1,
    Fragments = 2,
    Heal = 3
}

public readonly record struct WearPiece(ItemQuality Quality, int EnhanceLevel);

public readonly record struct PartyWearSnapshot(
    IReadOnlyList<WearPiece> ArmorPieces,
    IReadOnlyList<int> WeaponEnhanceLevels);

public readonly record struct BotCard(
    string Element,
    bool IsDamage,
    bool IsHeal,
    bool IsStun,
    int FaceValue);

public readonly record struct GridCell(int Row, int Col);

public readonly record struct BotLoadout(
    HeroClass Class,
    IReadOnlyList<WearPiece> Armor,
    int WeaponEnhance,
    int PotionCount,
    string DisplayName);

/// <summary>
/// GDD 5.14 补位机器人：匹配补人、练度对齐、PVE 模拟、三选一、回血、撤离、向中心走、中等 1v1。
/// </summary>
public static class BotRules
{
    public const int PartySize = 4;
    public const int QueueWaitSeconds = 30;
    public const int MaxEnhance = 5;
    public const int LowHpPercent = 60;
    public const int CriticalHpPercent = 40;
    public const int StartingPotions = 1;
    public const int ExtractChanceCap = 85;
    public const int BoardSize = 6;

    private static readonly string[] DisplayNames =
    [
        "青岚客", "烬里人", "渡川", "石门卫", "晚潮", "折梅",
        "无名刃", "拾薪", "北渚", "赤苇", "听雪", "沉锋"
    ];

    public static int BotSlots(int realPlayerCount)
    {
        if (realPlayerCount is < 1 or > PartySize)
        {
            throw new DomainValidationException("A match needs 1–4 real players.");
        }

        return PartySize - realPlayerCount;
    }

    public static bool ShouldOpenNow(int realPlayerCount, int waitedSeconds) =>
        realPlayerCount is >= 1 and <= PartySize
        && (realPlayerCount >= PartySize || waitedSeconds >= QueueWaitSeconds);

    public static int HpPercent(int currentHp, int maxHp) =>
        currentHp * 100 / Math.Max(1, maxHp);

    public static (ItemQuality Quality, int Enhance) AverageArmor(PartyWearSnapshot party)
    {
        if (party.ArmorPieces.Count == 0)
        {
            return (ItemQuality.White, 0);
        }

        var qualityMean = party.ArmorPieces.Average(piece => (int)piece.Quality);
        var enhanceMean = party.ArmorPieces.Average(piece => piece.EnhanceLevel);
        var quality = (ItemQuality)Math.Clamp((int)Math.Round(qualityMean, MidpointRounding.AwayFromZero), 1, 5);
        var enhance = Math.Clamp((int)Math.Round(enhanceMean, MidpointRounding.AwayFromZero), 0, MaxEnhance);
        return (quality, enhance);
    }

    public static int AverageWeaponEnhance(PartyWearSnapshot party)
    {
        if (party.WeaponEnhanceLevels.Count == 0)
        {
            return AverageArmor(party).Enhance;
        }

        return Math.Clamp(
            (int)Math.Round(party.WeaponEnhanceLevels.Average(), MidpointRounding.AwayFromZero),
            0,
            MaxEnhance);
    }

    public static WearPiece[] MakeArmorSet(ItemQuality averageQuality, int averageEnhance, int seed)
    {
        var rng = new Random(seed);
        var pieces = new WearPiece[5];
        for (var i = 0; i < pieces.Length; i++)
        {
            var quality = (ItemQuality)Math.Clamp((int)averageQuality + rng.Next(-1, 2), 1, 5);
            var enhance = Math.Clamp(averageEnhance + rng.Next(-1, 2), 0, MaxEnhance);
            pieces[i] = new WearPiece(quality, enhance);
        }

        return pieces;
    }

    public static HeroClass PickClass(IReadOnlyList<HeroClass> realClasses, int seed)
    {
        var counts = Enum.GetValues<HeroClass>().ToDictionary(hero => hero, _ => 0);
        foreach (var hero in realClasses)
        {
            counts[hero]++;
        }

        var least = counts.Values.Min();
        var candidates = counts.Where(pair => pair.Value == least).Select(pair => pair.Key).ToArray();
        return candidates[new Random(seed).Next(candidates.Length)];
    }

    public static string PickDisplayName(IReadOnlyCollection<string> takenNames, int seed)
    {
        var rng = new Random(seed);
        var unused = DisplayNames.Where(name => !takenNames.Contains(name)).ToArray();
        if (unused.Length > 0)
        {
            return unused[rng.Next(unused.Length)];
        }

        return $"{DisplayNames[rng.Next(DisplayNames.Length)]}{rng.Next(10, 99)}";
    }

    public static BotLoadout CreateLoadout(
        PartyWearSnapshot party,
        IReadOnlyList<HeroClass> realClasses,
        IReadOnlyCollection<string> takenNames,
        int seed)
    {
        var (quality, enhance) = AverageArmor(party);
        return new BotLoadout(
            PickClass(realClasses, seed),
            MakeArmorSet(quality, enhance, seed),
            AverageWeaponEnhance(party),
            StartingPotions,
            PickDisplayName(takenNames, seed));
    }

    public static int PveSimSeconds(CellLayer layer) => layer switch
    {
        CellLayer.Outer => 32,
        CellLayer.Mid => 45,
        CellLayer.Elite => 65,
        CellLayer.Boss => 80,
        _ => 32
    };

    public static int PveHpLossPercent(CellLayer layer) => layer switch
    {
        CellLayer.Outer => 18,
        CellLayer.Mid => 26,
        CellLayer.Elite => 40,
        CellLayer.Boss => 55,
        _ => 18
    };

    public static int ApplyHpLoss(int currentHp, int maxHp, int lossPercent)
    {
        var loss = Math.Max(1, (int)Math.Floor(maxHp * (lossPercent / 100.0)));
        return Math.Max(1, currentHp - loss);
    }

    public static ChoiceSlot PickChoice(int currentHp, int maxHp, bool bagFull, bool hasFragmentStack)
    {
        if (HpPercent(currentHp, maxHp) <= LowHpPercent)
        {
            return ChoiceSlot.Heal;
        }

        if (!bagFull)
        {
            return ChoiceSlot.Gear;
        }

        return hasFragmentStack ? ChoiceSlot.Fragments : ChoiceSlot.Heal;
    }

    public static bool ShouldHealOutOfCombat(int currentHp, int maxHp, bool springAvailable, bool hasPotion) =>
        HpPercent(currentHp, maxHp) <= LowHpPercent && (springAvailable || hasPotion);

    public static bool PreferSpring(bool springAvailable) =>
        springAvailable;

    public static int ExtractChancePercent(CellLayer layer, int hpPercent)
    {
        var chance = layer switch
        {
            CellLayer.Outer => 40,
            CellLayer.Mid => 25,
            CellLayer.Elite => 20,
            CellLayer.Boss => 15,
            _ => 40
        };

        if (hpPercent <= CriticalHpPercent)
        {
            chance += 25;
        }
        else if (hpPercent <= LowHpPercent)
        {
            chance += 10;
        }

        return Math.Clamp(chance, 0, ExtractChanceCap);
    }

    public static bool ShouldExtract(CellLayer layer, int hpPercent, Random rng) =>
        rng.Next(100) < ExtractChancePercent(layer, hpPercent);

    public static int InwardBiasPercent(int elapsedSeconds) => elapsedSeconds switch
    {
        < 240 => 30,
        < 480 => 55,
        _ => 80
    };

    public static GridCell PickNextCell(
        GridCell current,
        int elapsedSeconds,
        IReadOnlyList<GridCell> legalNeighbors,
        Random rng)
    {
        if (legalNeighbors.Count == 0)
        {
            return current;
        }

        var currentLayer = LayerDistance(current);
        var inward = legalNeighbors.Where(cell => LayerDistance(cell) > currentLayer).ToArray();
        var same = legalNeighbors.Where(cell => LayerDistance(cell) == currentLayer).ToArray();
        var bias = InwardBiasPercent(elapsedSeconds);

        if (inward.Length > 0 && rng.Next(100) < bias)
        {
            return inward[rng.Next(inward.Length)];
        }

        var pool = same.Length > 0 ? same : legalNeighbors;
        return pool[rng.Next(pool.Count)];
    }

    public static IReadOnlyList<GridCell> LegalNeighbors(GridCell current)
    {
        var candidates = new GridCell[]
        {
            current with { Row = current.Row - 1 },
            current with { Row = current.Row + 1 },
            current with { Col = current.Col - 1 },
            current with { Col = current.Col + 1 }
        };

        return candidates
            .Where(IsOnBoard)
            .Where(next => LayerDistance(next) >= LayerDistance(current))
            .ToArray();
    }

    public static bool IsOnBoard(GridCell cell) =>
        cell.Row is >= 0 and < BoardSize && cell.Col is >= 0 and < BoardSize;

    public static int LayerDistance(GridCell cell) =>
        Math.Min(Math.Min(cell.Row, cell.Col), Math.Min(BoardSize - 1 - cell.Row, BoardSize - 1 - cell.Col));

    public static CellLayer ClassifyLayer(GridCell cell, bool isBossCell, bool isEliteCell)
    {
        if (isBossCell)
        {
            return CellLayer.Boss;
        }

        if (isEliteCell || LayerDistance(cell) == 2)
        {
            return CellLayer.Elite;
        }

        return LayerDistance(cell) == 0 ? CellLayer.Outer : CellLayer.Mid;
    }

    /// <summary>
    /// 中等 1v1：残血优先奶/控；否则尽量 2–3 张同元素连放，不够再补直伤。
    /// </summary>
    public static int[] SelectDuelCards(IReadOnlyList<BotCard> hand, int hpPercent)
    {
        if (hand.Count == 0)
        {
            return [];
        }

        if (hpPercent <= CriticalHpPercent)
        {
            var heal = IndexOf(hand, card => card.IsHeal);
            if (heal >= 0)
            {
                var stun = IndexOf(hand, card => card.IsStun && !card.IsHeal);
                if (stun < 0)
                {
                    stun = FirstIndexExcept(hand, heal, card => card.IsStun);
                }

                return stun >= 0 ? [heal, stun] : [heal];
            }
        }

        var bestElement = hand
            .Select((card, index) => (card, index))
            .Where(pair => pair.card.IsDamage && pair.card.Element is not ("" or "none" or "direct"))
            .GroupBy(pair => pair.card.Element)
            .OrderByDescending(group => group.Count())
            .ThenByDescending(group => group.Sum(pair => pair.card.FaceValue))
            .FirstOrDefault();

        if (bestElement is not null)
        {
            return bestElement.Select(pair => pair.index).Take(3).ToArray();
        }

        return hand
            .Select((card, index) => (card, index))
            .Where(pair => pair.card.IsDamage)
            .OrderByDescending(pair => pair.card.FaceValue)
            .Select(pair => pair.index)
            .Take(2)
            .ToArray();
    }

    public static int BotVsBotSimSeconds() => 10;

    public static (int WinnerLossPercent, int LoserLossPercent) BotVsBotHpLoss() => (15, 35);

    public static bool ShouldSimulateBotVersusBot(bool leftIsBot, bool rightIsBot) =>
        leftIsBot && rightIsBot;

    public static (int LeftHp, int RightHp, bool LeftWon) ResolveBotVersusBot(
        int leftHp,
        int leftMax,
        int rightHp,
        int rightMax)
    {
        var leftWon = leftHp * rightMax >= rightHp * leftMax;
        var (winnerLoss, loserLoss) = BotVsBotHpLoss();
        return leftWon
            ? (ApplyHpLoss(leftHp, leftMax, winnerLoss), ApplyHpLoss(rightHp, rightMax, loserLoss), true)
            : (ApplyHpLoss(leftHp, leftMax, loserLoss), ApplyHpLoss(rightHp, rightMax, winnerLoss), false);
    }

    public static bool ShouldEndRoom(int remainingRealPlayers) => remainingRealPlayers <= 0;

    private static int IndexOf(IReadOnlyList<BotCard> hand, Func<BotCard, bool> predicate)
    {
        for (var i = 0; i < hand.Count; i++)
        {
            if (predicate(hand[i]))
            {
                return i;
            }
        }

        return -1;
    }

    private static int FirstIndexExcept(
        IReadOnlyList<BotCard> hand,
        int excluded,
        Func<BotCard, bool> predicate)
    {
        for (var i = 0; i < hand.Count; i++)
        {
            if (i != excluded && predicate(hand[i]))
            {
                return i;
            }
        }

        return -1;
    }
}
