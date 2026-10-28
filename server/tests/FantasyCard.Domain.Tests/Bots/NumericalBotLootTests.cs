using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Bots;

public sealed class NumericalBotLootTests
{
    [Fact]
    public void Loot_budget_is_deterministic_and_never_copies_high_level_combat_gear()
    {
        var room = Guid.NewGuid(); var player = Guid.NewGuid();
        var first = BotLootRules.Generate(room, player, 2);
        Assert.Equivalent(first, BotLootRules.Generate(room, player, 2), strict: true);
        BotLootRules.Validate(first, 2);
        Assert.Equal(2, first.Count);
        Assert.All(first, item => { Assert.Equal(0, item.Equipment!.Level); Assert.Contains(item.Equipment.Quality, new List<string> { "White", "Green" }); });
        Assert.NotEqual(first[0].ItemId, BotLootRules.Generate(room, Guid.NewGuid(), 2)[0].ItemId);
        Assert.Throws<DomainValidationException>(() => BotLootRules.Generate(room, player, 4));
    }

    [Fact]
    public void Room_snapshot_preserves_candidate_rules_and_bot_budget()
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 31, new(BudgetedBotLoot: true, MortalBotPve: true));
        var id = Guid.NewGuid();
        room.AddPlayer(new(id, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null, IsBot: true));
        var snapshot = room.Capture();
        var restored = BattleRoom.Restore(snapshot, catalog, 999);
        Assert.Equivalent(snapshot, restored.Capture(), strict: true);
        Assert.Equal(2, restored.GetPlayer(id).BotLoot.Count);
    }

    [Fact]
    public void Low_health_candidate_bot_can_die_in_pve_without_receiving_rewards()
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 31, new(BudgetedBotLoot: true, MortalBotPve: true));
        var human = Guid.NewGuid(); var bot = Guid.NewGuid();
        room.AddPlayer(new(human, HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null));
        room.AddPlayer(new(bot, HeroClass.Guardian, Enumerable.Repeat("common-01", 20).ToArray(), null, IsBot: true));
        room.InitializeMap(ChaosMapGenerator.Generate(31, 2));
        var player = room.GetPlayer(bot);
        player.Combat.TakeDamage(99);
        room.Advance(TimeSpan.FromSeconds(90), DateTimeOffset.UnixEpoch.AddSeconds(90));
        Assert.Equal(RoomPlayerPhase.Dead, player.Phase);
        Assert.Null(player.RewardChoice);
        var pile = Assert.Single(room.Capture().RelicPiles!, value => value.VictimId == bot.ToString("D"));
        Assert.Equal(2, pile.Items.Count);
        Assert.All(pile.Items, item => Assert.Equal(ExplorationItemKind.Equipment, item.Kind));
    }
}
