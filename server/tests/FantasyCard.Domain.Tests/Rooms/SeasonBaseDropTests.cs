using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class SeasonBaseDropTests
{
    private static readonly string[] Layers = ["outer", "middle", "elite", "boss"];
    private static readonly int[] Seeds = [31, 73];
    // Independent proposal multipliers, not copied from the runtime catalog.
    private static readonly int[][] Multipliers =
    [
        [10000,10000,10000], [12000,11500,14000], [14000,13000,19000],
        [16500,14500,25000], [19000,16000,32000], [22000,17500,40000]
    ];

    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)]
    [InlineData(3)] [InlineData(4)] [InlineData(5)]
    public void ActualVictoryScalesEachOriginalIntegerOnceAndRestoresTheSameLootStream(int difficulty)
    {
        foreach (var layer in Layers)
        foreach (var seed in Seeds)
            VerifyVictory(difficulty, layer, seed);
    }

    [Fact]
    public void PublishedNonSeasonRoomRetainsItsOriginalUnscaledDrops() => VerifyVictory(null, "elite", 73);

    [Fact]
    public void DiscreteD2OuterFragmentMeanIsTwoRatherThanTwoPointEightFive()
    {
        var basis = GameConfigCatalog.Current.SeasonDifficulty(2).FragmentBasisPoints;
        Assert.Equal(19000, basis);
        Assert.Equal(1, SeasonDifficultyConfig.Scale(1, basis));
        Assert.Equal(3, SeasonDifficultyConfig.Scale(2, basis));
        Assert.Equal(2, (SeasonDifficultyConfig.Scale(1, basis) + SeasonDifficultyConfig.Scale(2, basis)) / 2d);
    }

    private static void VerifyVictory(int? difficulty, string layerId, int seed)
    {
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.Create(config);
        var map = ChaosMapGenerator.Generate(seed, 1).Capture();
        var start = map.SpawnPositions[0];
        var layer = layerId switch
        {
            "outer" => ChaosMapLayer.Outer,
            "middle" => ChaosMapLayer.Middle,
            _ => ChaosMapLayer.Core
        };
        var group = layerId switch
        {
            "elite" => "E1",
            "boss" => "BOSS",
            _ => map.Cells.First(cell => cell.Layer == layer && !cell.IsBoss &&
                cell.MonsterGroupId != "BOX" && !cell.MonsterGroupId.StartsWith('E')).MonsterGroupId
        };
        map = map with { Cells = map.Cells.Select(cell => cell.Position == start
            ? cell with { Layer = layer, MonsterGroupId = group, IsBoss = layerId == "boss" }
            : cell).ToArray() };
        var context = difficulty is { } tier
            ? new SeasonContext("drop-control", tier, "season-v1", config.Version, "season-equipment-v1") : null;
        var room = new BattleRoom(Guid.NewGuid(), config.Version, catalog, seed, season: context);
        var id = Guid.NewGuid();
        var player = room.AddPlayer(new(id, HeroClass.Mage, SeasonFenxianTests.Starter(HeroClass.Mage), null));
        room.InitializeMap(ChaosMapState.Restore(map));
        var before = room.Capture();
        var raw = new CombatRandom(0);
        raw.Restore(before.RandomStreams!.Loot);
        var loot = config.LootLayer(layer, layerId == "boss");
        var warrior = raw.Next(loot.WarriorSoulMin, checked(loot.WarriorSoulMax + 1));
        var fragment = raw.Next(loot.FragmentMin, checked(loot.FragmentMax + 1));
        // Controlled one-HP targets exercise real terminal kills and inventory
        // writes. These are deterministic mechanism controls, not route balance.
        foreach (var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp + monster.Shield - 1);
            SeasonFenxianTests.SetHand(player, "C01");
            room.PlayCards(id, player.Pve.BattleId, monster.MonsterId,
                [player.Combat.Deck.Hand[0].InstanceId], room.Revision, DateTimeOffset.UnixEpoch,
                room.NewCombatActionId(id));
            room.Advance(TimeSpan.FromMilliseconds(500), DateTimeOffset.UnixEpoch);
        }
        Assert.Equal(RoomPlayerPhase.Choice, player.Phase);
        var factors = difficulty is { } d ? Multipliers[d] : Multipliers[0];
        Assert.Equal(loot.Gold * factors[0] / 10000, Quantity(player, ExplorationItemKind.Gold));
        Assert.Equal(warrior * factors[1] / 10000, Quantity(player, ExplorationItemKind.WarriorSoul));
        Assert.Equal(loot.ClassSoul * factors[1] / 10000, Quantity(player, ExplorationItemKind.ClassSoul));
        Assert.Equal(fragment * factors[2] / 10000, Quantity(player, ExplorationItemKind.EquipmentFragments));
        var after = room.Capture();
        Assert.Equal(raw.State, after.RandomStreams!.Loot);
        Assert.Equal(before.RandomStreams.PlayerSeed, after.RandomStreams.PlayerSeed);
        Assert.Equal(before.RandomStreams.Bot, after.RandomStreams.Bot);
        var restored = BattleRoom.Restore(after, catalog, seed);
        Assert.Equivalent(after, restored.Capture(), strict: true);
        Assert.Equal(Quantity(player, ExplorationItemKind.EquipmentFragments),
            Quantity(restored.GetPlayer(id), ExplorationItemKind.EquipmentFragments));
    }

    private static int Quantity(RoomPlayerState player, ExplorationItemKind kind) =>
        player.Inventory.Items.Where(item => item.Kind == kind).Sum(item => item.Quantity);
}
