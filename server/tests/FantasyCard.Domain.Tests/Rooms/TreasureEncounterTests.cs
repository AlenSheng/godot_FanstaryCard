using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class TreasureEncounterTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();
    private static readonly DateTimeOffset Now = DateTimeOffset.UnixEpoch.AddSeconds(20);
    private static readonly JsonSerializerOptions SnapshotJson = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    [Fact]
    public void Treasure_count_and_element_rolls_have_the_exact_frozen_weights()
    {
        var counts = Enumerable.Range(0, 100).Select(ChaosMapGenerator.RollTreasureCount).ToArray();
        Assert.Equal([40, 35, 20, 5], Enumerable.Range(0, 4).Select(count => counts.Count(value => value == count)));
        var elements = Enumerable.Range(0, 100).Select(ChaosMapGenerator.RollTreasureElement).ToArray();
        Assert.Equal(20, elements.Count(element => element == CardElement.None));
        foreach (var element in Enum.GetValues<CardElement>().Where(element => element != CardElement.None))
            Assert.Equal(16, elements.Count(value => value == element));
        Assert.Throws<ArgumentOutOfRangeException>(() => ChaosMapGenerator.RollTreasureCount(100));
        Assert.Throws<ArgumentOutOfRangeException>(() => ChaosMapGenerator.RollTreasureElement(-1));
    }

    [Fact]
    public void Generated_treasures_are_distinct_outer_cells_can_overlap_spawns_and_evacuations_and_restore_exactly()
    {
        var spawnOverlap = false;
        var evacuationOverlap = false;
        var observedCounts = new HashSet<int>();
        for (var seed = 0; seed < 300; seed++)
        {
            var map = ChaosMapGenerator.Generate(seed, 4);
            var treasure = map.Cells.Where(cell => cell.MonsterGroupId == "BOX").ToArray();
            observedCounts.Add(treasure.Length);
            Assert.InRange(treasure.Length, 0, 3);
            Assert.Equal(treasure.Length, treasure.Select(cell => cell.Position).Distinct().Count());
            Assert.All(treasure, cell =>
            {
                Assert.Equal(ChaosMapLayer.Outer, cell.Layer);
                Assert.False(cell.IsBoss);
                Assert.NotNull(cell.TreasureElement);
            });
            Assert.All(map.Cells.Except(treasure), cell => Assert.Null(cell.TreasureElement));
            spawnOverlap |= treasure.Any(cell => map.SpawnPositions.Contains(cell.Position));
            evacuationOverlap |= treasure.Any(cell => cell.HasEvacuation);
            Assert.Equivalent(map.Capture(), ChaosMapState.Restore(map.Capture()).Capture(), strict: true);
            Assert.Equivalent(map.Capture(), ChaosMapGenerator.Generate(seed, 4).Capture(), strict: true);
        }
        Assert.Equal([0, 1, 2, 3], observedCounts.Order());
        Assert.True(spawnOverlap);
        Assert.True(evacuationOverlap);
    }

    [Theory]
    [InlineData(CardElement.None)]
    [InlineData(CardElement.Fire)]
    [InlineData(CardElement.Wood)]
    [InlineData(CardElement.Earth)]
    [InlineData(CardElement.Metal)]
    [InlineData(CardElement.Water)]
    public void Treasure_factory_replaces_the_group_with_an_independent_frozen_outer_monster(CardElement element)
    {
        var cell = TreasureCell(element);
        var first = PveBattleFactory.Create(cell);
        var second = PveBattleFactory.Create(cell);
        var monster = Assert.Single(first.Monsters);
        var other = Assert.Single(second.Monsters);
        Assert.NotEqual(first.BattleId, second.BattleId);
        Assert.Equal("box-spirit", monster.MonsterId);
        Assert.Equal(84, monster.MaximumHp);
        Assert.Equal(0, monster.Shield);
        Assert.Equal(TimeSpan.FromSeconds(4), monster.AttackInterval);
        Assert.Equal(element, monster.Intents[0].Element);
        Assert.Equal(element == CardElement.None ? MonsterIntentKind.Direct : MonsterIntentKind.Attack, monster.Intents[0].Kind);
        Assert.Equal(element == CardElement.None ? 0 : .10, monster.ElementalAmplification);
        Assert.Null(monster.Advance(TimeSpan.FromSeconds(4)));
        Assert.Equal(TimeSpan.FromSeconds(.6), monster.WindupRemaining);
        var intent = Assert.IsType<MonsterIntentState>(monster.Advance(TimeSpan.FromSeconds(.6)));
        Assert.Equal(3, monster.ResolveIntentDamage(intent));
        if (element == CardElement.None)
            Assert.All(Enum.GetValues<CardElement>(), incoming => Assert.Equal(0, monster.ElementalResistance(incoming)));
        else Assert.Equal(.15, monster.ElementalResistance(element));
        monster.TakeDamage(20);
        Assert.Equal(84, other.Hp);
        Assert.Equivalent(first.Capture(), PveBattleState.Rehydrate(first.Capture()).Capture(), strict: true);
    }

    [Theory]
    [InlineData(CardElement.None)]
    [InlineData(CardElement.Fire)]
    [InlineData(CardElement.Wood)]
    [InlineData(CardElement.Earth)]
    [InlineData(CardElement.Metal)]
    [InlineData(CardElement.Water)]
    public void Acquired_treasure_card_keeps_one_art_id_and_its_element_across_restart_duel_preview_and_play(CardElement element)
    {
        var room = CreateRoom(element);
        var playerId = room.Capture().Players[0].PlayerId;
        KillCurrentMonster(room, playerId);
        var card = Assert.Single(room.GetPlayer(playerId).Combat.Deck.Discard, value => value.CardId == "M-BOXSPIRIT");
        Assert.Equal(element, card.ElementOverride);
        Assert.Equal(0, card.Level);
        Assert.True(room.GetPlayer(playerId).RewardChoice!.IsTreasure);

        var snapshot = JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(room.Capture(), SnapshotJson), SnapshotJson)!;
        room = BattleRoom.Restore(snapshot, Catalog, 91);
        Assert.Equal(element, room.Map!.GetCell(room.GetPlayer(playerId).Position!.Value).TreasureElement);
        var opponentId = Guid.NewGuid();
        room.AddPlayer(new(opponentId, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        var duel = room.StartDuel(playerId, opponentId, Now);
        var player = room.GetPlayer(playerId);
        var pooled = player.Combat.Deck.Hand.Concat(player.Combat.Deck.Library).Concat(player.Combat.Deck.Discard).ToArray();
        var drawn = Assert.Single(pooled, value => value.InstanceId == card.InstanceId);
        Assert.Equal(element, drawn.ElementOverride);
        player.Combat.Deck.Restore(new([drawn], pooled.Where(value => value.InstanceId != drawn.InstanceId).ToArray(), [], 0));
        var before = room.Capture();
        var preview = room.PreviewCards(playerId, duel.DuelId, opponentId.ToString("D"), [drawn.InstanceId], room.Revision, Now);
        Assert.Equivalent(before, room.Capture(), strict: true);
        var result = room.PlayCards(playerId, duel.DuelId, opponentId.ToString("D"), [drawn.InstanceId], room.Revision, Now);
        Assert.Equivalent(preview with { RoomRevision = result.RoomRevision }, result, strict: true);
        Assert.Equal(new CombatDamageSegment(element == CardElement.None ? "Direct" : element.ToString(), 7), Assert.Single(result.DamageSegments!));
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        Assert.Equal(element, Assert.Single(player.Combat.Deck.Discard, value => value.CardId == "M-BOXSPIRIT").ElementOverride);
        Assert.Equal(200, GameConfigCatalog.Current.Cards.Count(value => value.IsCodex));
    }

    [Fact]
    public void Treasure_reward_promotes_only_equipment_and_refresh_preserves_that_rule_after_restart()
    {
        for (var seed = 0; seed < 100; seed++)
        {
            var normal = RewardChoiceState.Create(ChaosMapLayer.Outer, new Random(seed));
            var treasure = RewardChoiceState.Create(ChaosMapLayer.Outer, new Random(seed), isTreasure: true);
            AssertOnlyEquipmentPromoted(normal, treasure);
            var restored = RewardChoiceState.Restore(treasure.Capture());
            var normalRandom = new Random(seed + 1000);
            var treasureRandom = new Random(seed + 1000);
            normal.Refresh(normalRandom);
            restored.Refresh(treasureRandom);
            AssertOnlyEquipmentPromoted(normal, restored);
            Assert.True(restored.Capture().IsTreasure);
            Assert.False(restored.IsBoss);
            Assert.Equal(1, restored.RefreshCount);
        }
    }

    [Fact]
    public void Treasure_clear_keeps_outer_resource_drops_and_refresh_receipts_replay_after_restart()
    {
        var treasure = CreateRoom(CardElement.Fire);
        var regular = CreateRoom(null);
        var playerId = treasure.Capture().Players[0].PlayerId;
        var regularPlayer = regular.Capture().Players[0].PlayerId;
        KillCurrentMonster(treasure, playerId);
        KillCurrentMonster(regular, regularPlayer);
        var resources = treasure.GetPlayer(playerId).Inventory.Items.OrderBy(item => item.ItemId).ToArray();
        Assert.Equivalent(regular.GetPlayer(regularPlayer).Inventory.Items.OrderBy(item => item.ItemId).ToArray(), resources, strict: true);
        var loot = GameConfigCatalog.Current.LootLayer(ChaosMapLayer.Outer, false);
        Assert.Equal(loot.Gold, resources.Single(item => item.Kind == ExplorationItemKind.Gold).Quantity);
        Assert.Equal(loot.ClassSoul, resources.Single(item => item.Kind == ExplorationItemKind.ClassSoul).Quantity);
        treasure.GetPlayer(playerId).Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 1000));
        var restored = BattleRoom.Restore(treasure.Capture(), Catalog, 99);
        var first = treasure.RefreshRewardChoice(playerId, treasure.Revision, requestId: "treasure-refresh");
        var replay = restored.RefreshRewardChoice(playerId, restored.Revision, requestId: "treasure-refresh");
        Assert.Equivalent(first, replay, strict: true);
        Assert.True(first.Choice.IsTreasure);
        Assert.Equal(loot.HealPercentagePoints, first.Choice.Options.Single(option => option.Kind == RewardChoiceKind.ImmediateHeal).HealPercent);
    }

    [Fact]
    public void Hidden_map_projection_contains_neither_treasure_positions_nor_elements()
    {
        var room = CreateRoom(null);
        var snapshot = room.Capture();
        var player = snapshot.Players[0];
        var hidden = snapshot.Map!.Cells.First(cell => cell.Layer == ChaosMapLayer.Outer && cell.Position != player.Position);
        snapshot = snapshot with
        {
            Map = snapshot.Map with
            {
                Cells = snapshot.Map.Cells.Select(cell => cell.Position == hidden.Position
                    ? cell with { MonsterGroupId = "BOX", TreasureElement = CardElement.Fire } : cell).ToArray()
            }
        };
        room = BattleRoom.Restore(snapshot, Catalog, 44);
        var projected = JsonSerializer.Serialize(room.GetMapProjection(player.PlayerId));
        Assert.DoesNotContain("BOX", projected, StringComparison.Ordinal);
        Assert.DoesNotContain("Treasure", projected, StringComparison.Ordinal);
        Assert.DoesNotContain("Fire", projected, StringComparison.Ordinal);
        Assert.Equal(CardElement.Fire, room.Map!.GetCell(hidden.Position).TreasureElement);
    }

    [Fact]
    public void Element_overrides_cannot_be_applied_to_codex_cards_or_upgraded_monster_cards()
    {
        Assert.Throws<DomainValidationException>(() => Catalog.Get("C01", elementOverride: CardElement.Fire));
        Assert.Throws<DomainValidationException>(() => Catalog.Get("M-BOXSPIRIT", 1, CardElement.Fire));
        Assert.Throws<DomainValidationException>(() => Catalog.Get("M-BOXSPIRIT", 0, (CardElement)8));
        var deck = CombatDeck.Create(["C01"], new Random(42));
        Assert.Throws<DomainValidationException>(() => deck.Restore(new([new(Guid.NewGuid(), "C01", ElementOverride: CardElement.Fire)], [], [], 0)));
        Assert.Throws<DomainValidationException>(() => deck.AddToDiscard(new(Guid.NewGuid(), "M-BOXSPIRIT", 2, CardElement.Water)));
    }

    private static void AssertOnlyEquipmentPromoted(RewardChoiceState normal, RewardChoiceState treasure)
    {
        var source = normal.Options.Single(option => option.Kind == RewardChoiceKind.Equipment).Item!.Equipment!;
        var promoted = treasure.Options.Single(option => option.Kind == RewardChoiceKind.Equipment).Item!.Equipment!;
        var qualities = new[] { "White", "Green", "Blue", "Purple", "Orange" };
        Assert.Equal(qualities[Math.Min(4, Array.IndexOf(qualities, source.Quality) + 1)], promoted.Quality);
        Assert.True(EquipmentRewardRules.IsValid(promoted));
        Assert.Equal(normal.Options.Single(option => option.Kind == RewardChoiceKind.EquipmentFragments).Item!.Quantity,
            treasure.Options.Single(option => option.Kind == RewardChoiceKind.EquipmentFragments).Item!.Quantity);
        Assert.Equal(normal.Options.Single(option => option.Kind == RewardChoiceKind.ImmediateHeal).HealPercent,
            treasure.Options.Single(option => option.Kind == RewardChoiceKind.ImmediateHeal).HealPercent);
    }

    private static ChaosMapCell TreasureCell(CardElement element) => new(new(0, 0), ChaosMapLayer.Outer, false, false, false, "BOX", element);

    private static BattleRoom CreateRoom(CardElement? element)
    {
        var room = new BattleRoom(Guid.NewGuid(), "treasure-test", Catalog, 91);
        var playerId = Guid.NewGuid();
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Repeat("common-11", 20).ToArray(), null));
        var map = ChaosMapGenerator.Generate(77, 1).Capture();
        var spawn = map.SpawnPositions[0];
        map = map with
        {
            Cells = map.Cells.Select(cell => cell.Position == spawn
                ? cell with { MonsterGroupId = element is null ? "O1" : "BOX", TreasureElement = element }
                : cell).ToArray()
        };
        room.InitializeMap(ChaosMapState.Restore(map));
        return room;
    }

    private static void KillCurrentMonster(BattleRoom room, Guid playerId)
    {
        var player = room.GetPlayer(playerId);
        var monster = Assert.Single(player.Pve!.Monsters);
        monster.TakeDamage(monster.Hp + monster.Shield - 1);
        room.PlayCards(playerId, player.Pve.BattleId, monster.MonsterId, [player.Combat.Deck.Hand[0].InstanceId], room.Revision, Now);
    }
}
