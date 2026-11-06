using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Tests.Combat;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class CrossRoomRewardIdentityTests
{
    private const int Seed = 73;
    private static readonly Guid FirstRoom = Guid.Parse("68e94e64-682d-44d4-bdd4-5d4e60bccb01");
    private static readonly Guid SecondRoom = Guid.Parse("68e94e64-682d-44d4-bdd4-5d4e60bccb02");

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void SameSeedRoomsMintDifferentEquipmentWhileRewardDataStayEqual(bool seasonal)
    {
        var first = ClearedRoom(FirstRoom, seasonal);
        var second = ClearedRoom(SecondRoom, seasonal);
        var a = Assert.Single(first.Capture().Players).RewardChoice!;
        var b = Assert.Single(second.Capture().Players).RewardChoice!;
        var firstItem = a.Options.Single(x => x.Kind == RewardChoiceKind.Equipment).Item!;
        var secondItem = b.Options.Single(x => x.Kind == RewardChoiceKind.Equipment).Item!;
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_LOOT_ID_PROOF_OUTPUT");
        if (output is not null)
            File.AppendAllText(output, JsonSerializer.Serialize(new { seasonal, seed = Seed, first = first.Capture(), second = second.Capture(),
                item_ids_equal = firstItem.ItemId == secondItem.ItemId, controlled_one_HP_fixtures = 2, timed_routes = 0 }) + Environment.NewLine);
        Assert.Equal(firstItem.Equipment, secondItem.Equipment);
        Assert.Equal(a.Options.Select(x => (x.OptionId, x.Kind, x.HealPercent, x.Item?.Quantity)), b.Options.Select(x => (x.OptionId, x.Kind, x.HealPercent, x.Item?.Quantity)));
        Assert.Equivalent(first.Capture().RandomStreams, second.Capture().RandomStreams, strict: true);
        Assert.NotEqual(firstItem.ItemId, secondItem.ItemId);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void OldPendingIdsSurviveRestoreAndNewRefreshesBindToTheirActualRoom(bool seasonal)
    {
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.Create(config);
        var original = ClearedRoom(FirstRoom, seasonal);
        var player = original.GetPlayer(Assert.Single(original.Capture().Players).PlayerId);
        Assert.True(player.Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 1000)));
        var current = player.RewardChoice!.Capture();
        // A pre-upgrade choice has raw deterministic IDs; its parent room already exists in the snapshot.
        var old = RewardChoiceState.Create(current.Layer, new CombatRandom(991), current.IsBoss, isTreasure: current.IsTreasure,
            configuration: config, season: current.SeasonLoot).Capture();
        var snapshot = original.Capture() with { Players = original.Capture().Players.Select(x => x with { RewardChoice = old }).ToArray() };
        var before = JsonSerializer.Serialize(snapshot);
        var restored = BattleRoom.Restore(snapshot, catalog, Seed);
        Assert.Equal(before, JsonSerializer.Serialize(restored.Capture()));
        var refreshed = restored.RefreshRewardChoice(player.PlayerId, snapshot.Revision, requestId: "f02-identity-refresh");
        var replay = BattleRoom.Restore(snapshot, catalog, Seed).RefreshRewardChoice(player.PlayerId, snapshot.Revision, requestId: "f02-identity-refresh");
        Assert.Equivalent(refreshed, replay, strict: true);
        var refreshedSnapshot = restored.Capture();
        var afterRestart = BattleRoom.Restore(refreshedSnapshot, catalog, Seed);
        Assert.Equal(JsonSerializer.Serialize(refreshedSnapshot), JsonSerializer.Serialize(afterRestart.Capture()));
        Assert.Equivalent(refreshed, afterRestart.RefreshRewardChoice(player.PlayerId, snapshot.Revision, requestId: "f02-identity-refresh"), strict: true);
        var other = BattleRoom.Restore(snapshot with { RoomId = SecondRoom }, catalog, Seed);
        var otherRefresh = other.RefreshRewardChoice(player.PlayerId, snapshot.Revision, requestId: "f02-identity-refresh");
        var firstItem = refreshed.Choice.Options.Single(x => x.Kind == RewardChoiceKind.Equipment).Item!;
        var secondItem = otherRefresh.Choice.Options.Single(x => x.Kind == RewardChoiceKind.Equipment).Item!;
        Assert.Equal(firstItem.Equipment, secondItem.Equipment);
        Assert.NotEqual(firstItem.ItemId, secondItem.ItemId);
        Assert.Equal(before, JsonSerializer.Serialize(snapshot));
        restored.ClaimReward(player.PlayerId, refreshed.Choice.Options.Single(x => x.Kind == RewardChoiceKind.Equipment).OptionId);
        Assert.Contains(restored.GetPlayer(player.PlayerId).Inventory.Items, x => x.ItemId == firstItem.ItemId);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void RoomBindingChangesOnlyPhysicalIdsWithoutConsumingRandomValues(bool seasonal)
    {
        var config = GameConfigCatalog.Current;
        var context = seasonal ? new SeasonRewardContext(new("f02-rng", 2, "season-v1", config.Version, "season-equipment-v1"), SeasonRewardBias.None) : null;
        foreach (var layer in Enum.GetValues<ChaosMapLayer>())
        for (var seed = 0; seed < 4; seed++)
        {
            var baselineRandom = new CombatRandom(seed);
            var boundRandom = new CombatRandom(seed);
            var baseline = RewardChoiceState.Create(layer, baselineRandom, configuration: config, season: context);
            var bound = RewardChoiceState.Create(layer, boundRandom, configuration: config, season: context, roomId: FirstRoom);
            var ids = new HashSet<string>(StringComparer.Ordinal);
            for (var round = 0; round < 3; round++)
            {
                if (round > 0) { baseline.Refresh(baselineRandom); bound.Refresh(boundRandom); }
                var raw = baseline.Capture(); var scoped = bound.Capture();
                var equipment = scoped.Options.Single(x => x.Kind == RewardChoiceKind.Equipment).Item!;
                Assert.True(ids.Add(equipment.ItemId));
                var normalized = raw with { Options = raw.Options.Select(x => x.Kind == RewardChoiceKind.Equipment
                    ? x with { Item = x.Item! with { ItemId = equipment.ItemId } } : x).ToArray() };
                Assert.Equivalent(normalized, scoped, strict: true);
                Assert.Equal(baselineRandom.State, boundRandom.State);
                Assert.Equal(baselineRandom.Next(), boundRandom.Next());
            }
        }
    }

    private static BattleRoom ClearedRoom(Guid roomId, bool seasonal)
    {
        var config = GameConfigCatalog.Current;
        var catalog = CombatCardCatalog.Create(config);
        var context = seasonal ? new SeasonContext("f02-loot-id", 0, "season-v1", config.Version, "season-equipment-v1") : null;
        var room = new BattleRoom(roomId, config.Version, catalog, Seed, season: context);
        var player = room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, SeasonFenxianTests.Starter(HeroClass.Mage), null));
        room.InitializeMap(ChaosMapGenerator.Generate(Seed, 1, seasonal ? config.SeasonThemes : null));
        // Identity fixture only: actual resolver/choice path, with controlled one-HP targets. No route/balance claim.
        foreach (var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp + monster.Shield - 1);
            SeasonFenxianTests.SetHand(player, "C01");
            room.PlayCards(player.PlayerId, player.Pve.BattleId, monster.MonsterId, [player.Combat.Deck.Hand[0].InstanceId],
                room.Revision, DateTimeOffset.UnixEpoch, room.NewCombatActionId(player.PlayerId));
            room.Advance(TimeSpan.FromMilliseconds(500), DateTimeOffset.UnixEpoch);
        }
        Assert.Equal(RoomPlayerPhase.Choice, player.Phase);
        return room;
    }
}
