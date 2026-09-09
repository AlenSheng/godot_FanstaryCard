using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RewardChoiceTests
{
    [Fact]
    public void Player_refresh_budget_survives_claim_restore_and_next_cell_victory()
    {
        var catalog = new CombatCardCatalog([new("test-hit", new CombatCardEffect(DirectDamage: 10000))]);
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 7);
        var id = Guid.NewGuid();
        var otherId = Guid.NewGuid();
        room.AddPlayer(new(id, HeroClass.Mage, Enumerable.Repeat("test-hit", 20).ToArray(), null));
        room.AddPlayer(new(otherId, HeroClass.Priest, Enumerable.Repeat("test-hit", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(7, 2));
        ClearPve(room, id);
        var player = room.GetPlayer(id);
        player.Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 1000));
        foreach (var cost in new[] { 60, 180, 450 })
        {
            var before = player.Inventory.GoldQuantity;
            room.RefreshRewardChoice(id, room.Revision);
            Assert.Equal(before - cost, player.Inventory.GoldQuantity);
        }
        room.ClaimReward(id, room.GetRewardChoice(id).Options.Single(o => o.Kind == RewardChoiceKind.ImmediateHeal).OptionId);
        room = BattleRoom.Restore(room.Capture(), catalog, 7);
        Assert.Equal(3, room.GetPlayer(id).RewardRefreshCount);
        Assert.Equal(0, room.GetPlayer(otherId).RewardRefreshCount);

        var start = room.GetPlayer(id).Position!.Value;
        var next = room.Map!.GetNeighbors(start).First(p => room.Map.GetCell(p).Layer == ChaosMapLayer.Outer);
        var previousBattle = room.GetPlayer(id).Pve!.BattleId;
        room.GetPlayer(id).Combat.GainShield(10);
        room.MovePlayer(id, next, room.Revision);
        Assert.Equal(RoomPlayerPhase.Pve, room.GetPlayer(id).Phase);
        Assert.NotEqual(previousBattle, room.GetPlayer(id).Pve!.BattleId);
        Assert.Equal(0, room.GetPlayer(id).Combat.Shield);
        ClearPve(room, id);
        Assert.Equal(3, room.GetRewardChoice(id).RefreshCount);
        var beforeRejected = room.Capture();
        Assert.Throws<DomainValidationException>(() => room.RefreshRewardChoice(id, room.Revision));
        Assert.Equivalent(beforeRejected, room.Capture(), strict: true);
        room.ClaimReward(id, room.GetRewardChoice(id).Options.Single(o => o.Kind == RewardChoiceKind.ImmediateHeal).OptionId);
        room = BattleRoom.Restore(room.Capture(), catalog, 7);
        var goldBeforeReturn = room.GetPlayer(id).Inventory.GoldQuantity;
        room.MovePlayer(id, start, room.Revision);
        Assert.Equal(RoomPlayerPhase.ActionBar, room.GetPlayer(id).Phase);
        Assert.Null(room.GetPlayer(id).Pve);
        Assert.Null(room.GetPlayer(id).RewardChoice);
        Assert.Equal(goldBeforeReturn, room.GetPlayer(id).Inventory.GoldQuantity);
    }

    private static void ClearPve(BattleRoom room, Guid id)
    {
        var player = room.GetPlayer(id);
        foreach (var monster in player.Pve!.Monsters.ToArray())
        {
            if (player.Combat.Deck.Hand.Count == 0) player.Combat.DrawImmediate(1);
            room.PlayCards(id, player.Pve.BattleId, monster.MonsterId,
                [player.Combat.Deck.Hand[0].InstanceId], room.Revision, DateTimeOffset.UnixEpoch);
        }
    }

    [Fact]
    public void Refresh_request_receipt_is_idempotent_and_survives_room_restore()
    {
        var catalog = new CombatCardCatalog([new("test-hit", new CombatCardEffect(DirectDamage: 10000))]);
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 71);
        var playerId = Guid.NewGuid();
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Repeat("test-hit", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(71, 1));
        ClearPve(room, playerId);
        room.GetPlayer(playerId).Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 30));
        var expectedRevision = room.Revision;

        var applied = room.RefreshRewardChoice(playerId, expectedRevision, 30, "refresh-durable-01");
        var revisionAfterApply = room.Revision;
        var replay = room.RefreshRewardChoice(playerId, expectedRevision, 30, "refresh-durable-01");

        Assert.Equal(0, room.GetPlayer(playerId).Inventory.GoldQuantity);
        Assert.Equal(revisionAfterApply, room.Revision);
        Assert.Equivalent(applied, replay, strict: true);

        room = BattleRoom.Restore(room.Capture(), catalog, 71);
        var restoredReplay = room.RefreshRewardChoice(playerId, expectedRevision, 30, "refresh-durable-01");
        Assert.Equal(revisionAfterApply, room.Revision);
        Assert.Equivalent(applied, restoredReplay, strict: true);
    }

    [Fact]
    public void Duel_freezes_reward_refresh_without_spending_gold()
    {
        var catalog = new CombatCardCatalog([new("test-hit", new CombatCardEffect(DirectDamage: 10000))]);
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 8);
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        foreach (var id in new[] { first, second })
            room.AddPlayer(new(id, HeroClass.Mage, Enumerable.Repeat("test-hit", 20).ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(8, 2));
        ClearPve(room, first);
        room.GetPlayer(first).Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 1000));
        room.StartDuel(first, second, DateTimeOffset.UnixEpoch);
        var before = room.Capture();
        Assert.Throws<DomainValidationException>(() => room.RefreshRewardChoice(first, room.Revision));
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Theory]
    [InlineData(ChaosMapLayer.Outer, 14)]
    [InlineData(ChaosMapLayer.Middle, 20)]
    [InlineData(ChaosMapLayer.Core, 28)]
    public void Create_has_fixed_three_categories_and_layer_heal(ChaosMapLayer layer, int healPercent)
    {
        var choice = RewardChoiceState.Create(layer, new Random(7));
        Assert.Equal(3, choice.Options.Count);
        Assert.Equal([RewardChoiceKind.Equipment, RewardChoiceKind.EquipmentFragments, RewardChoiceKind.ImmediateHeal],
            choice.Options.Select(option => option.Kind).OrderBy(kind => kind).ToArray());
        Assert.Equal(healPercent, choice.Options.Single(option => option.Kind == RewardChoiceKind.ImmediateHeal).HealPercent);
        Assert.Equal(0, choice.RefreshCount);
    }

    [Fact]
    public void Refresh_cost_progression_is_limited_to_three_refreshes()
    {
        var choice = RewardChoiceState.Create(ChaosMapLayer.Outer, new Random(7));
        choice.Refresh(new Random(8));
        choice.Refresh(new Random(9));
        choice.Refresh(new Random(10));
        Assert.Equal(3, choice.RefreshCount);
        Assert.Throws<FantasyCard.Domain.Players.DomainValidationException>(() => choice.Refresh(new Random(11)));
    }

    [Theory]
    [InlineData(ChaosMapLayer.Outer, false, "White", 0.70)]
    [InlineData(ChaosMapLayer.Outer, false, "Green", 0.30)]
    [InlineData(ChaosMapLayer.Middle, false, "Green", 0.50)]
    [InlineData(ChaosMapLayer.Middle, false, "Blue", 0.45)]
    [InlineData(ChaosMapLayer.Middle, false, "Purple", 0.05)]
    [InlineData(ChaosMapLayer.Core, false, "Blue", 0.50)]
    [InlineData(ChaosMapLayer.Core, false, "Purple", 0.45)]
    [InlineData(ChaosMapLayer.Core, false, "Orange", 0.05)]
    [InlineData(ChaosMapLayer.Core, true, "Purple", 0.60)]
    [InlineData(ChaosMapLayer.Core, true, "Orange", 0.40)]
    public void Equipment_quality_follows_layer_table(
        ChaosMapLayer layer,
        bool isBoss,
        string quality,
        double expectedRate)
    {
        const int samples = 20_000;
        var random = new Random(31 + (int)layer * 7 + (isBoss ? 1 : 0));
        var count = 0;
        for (var index = 0; index < samples; index++)
        {
            var item = RewardChoiceState.Create(layer, random, isBoss).Options
                .Single(option => option.Kind == RewardChoiceKind.Equipment).Item!;
            Assert.True(Guid.TryParse(item.ItemId, out _));
            Assert.NotNull(item.Equipment);
            Assert.True(EquipmentRewardRules.IsValid(item.Equipment));
            if (item.Equipment.Quality == quality) count++;
        }
        Assert.InRange(count / (double)samples, expectedRate - 0.015, expectedRate + 0.015);
    }

    [Fact]
    public void Equipment_attributes_follow_affix_and_shoe_rules_and_are_replayable()
    {
        var first = RewardChoiceState.Create(ChaosMapLayer.Core, new Random(177), isBoss: true).Capture();
        var replay = RewardChoiceState.Create(ChaosMapLayer.Core, new Random(177), isBoss: true).Capture();
        Assert.Equivalent(first, replay, strict: true);

        var random = new Random(81);
        var purple = 0;
        var purpleAffixed = 0;
        var feet = 0;
        var escapeFeet = 0;
        for (var index = 0; index < 30_000; index++)
        {
            var equipment = RewardChoiceState.Create(ChaosMapLayer.Core, random, isBoss: true).Options
                .Single(option => option.Kind == RewardChoiceKind.Equipment).Item!.Equipment!;
            Assert.NotEqual("Red", equipment.Quality);
            if (equipment.Quality == "Orange") Assert.NotNull(equipment.EffectAffix);
            if (equipment.Quality == "Purple")
            {
                purple++;
                if (equipment.EffectAffix is not null) purpleAffixed++;
            }
            if (equipment.Slot == "Feet")
            {
                feet++;
                if (equipment.SecondaryTrait == "ForcedEscape") escapeFeet++;
            }
            else Assert.Equal("DrawInterval", equipment.SecondaryTrait);
        }
        Assert.InRange(purpleAffixed / (double)purple, 0.385, 0.415);
        Assert.InRange(escapeFeet / (double)feet, 0.485, 0.515);
    }
}
