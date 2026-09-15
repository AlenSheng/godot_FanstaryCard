using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Cards;

public sealed class CardUpgradeTests
{
    [Theory]
    [InlineData("C01", 5, 80)]
    [InlineData("MAG-01", 8, 120)]
    [InlineData("PRI-10", 80, 1000)]
    public void Upgrade_quotes_use_corresponding_config_and_require_copies_only_at_four_and_five(
        string cardId, int firstCost, int lastCost)
    {
        Assert.Equal(firstCost, CardEconomyRules.Level(cardId, 1).SoulCost);
        Assert.Equal(lastCost, CardEconomyRules.Level(cardId, 5).SoulCost);
        for (var level = 1; level <= 5; level++)
            Assert.Equal(level >= 4, CardEconomyRules.Level(cardId, level).RequiresCopy);
        Assert.Throws<DomainValidationException>(() => CardEconomyRules.Level(cardId, 6));
    }

    [Fact]
    public void Upgrades_strengthen_existing_components_without_adding_damage_or_changing_card_structure()
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var apocalypse = catalog.Get("PRI-10", 5).Effect;
        Assert.Equal(13, apocalypse.Heal);
        Assert.Equal(13, apocalypse.Shield);
        Assert.Equal(1.6, apocalypse.StunSeconds, 8);
        Assert.Equal(1, apocalypse.ImmediateDraw);
        Assert.Equal(0, apocalypse.ElementalDamage);
        Assert.Equal(0, apocalypse.DirectDamage);
        Assert.Equal(CardElement.None, apocalypse.Element);
        Assert.Equal(8, catalog.Get("PRI-10").Effect.Heal);
        Assert.Equal(13, catalog.Get("MAG-01", 5).Effect.ElementalDamage);
        Assert.Equal(12, catalog.Get("PRI-01", 5).Effect.Heal);
        Assert.Equal(14, catalog.Get("GUA-01", 5).Effect.Shield);
        Assert.Equal(catalog.Get("GO10").Effect, catalog.Get("GO10", 5).Effect);
    }

    [Theory]
    [InlineData(1, 8.0)]
    [InlineData(2, 8.2)]
    [InlineData(3, 8.2)]
    [InlineData(4, 8.4)]
    [InlineData(5, 8.4)]
    public void Support_duration_grows_every_two_levels_without_changing_rate(int level, double seconds)
    {
        var effect = CombatCardCatalog.CreatePrototype().Get("C18", level).Effect;
        Assert.Equal(seconds, effect.DrawSpeedSeconds, 8);
        Assert.Equal(-0.15, effect.DrawSpeedModifier);
        Assert.Equal(0, effect.Heal);
        Assert.Equal(0, effect.Shield);
    }

    [Fact]
    public void Upgrade_requires_only_an_activated_card_below_maximum_level()
    {
        Assert.Null(CardEconomyRules.UpgradeBlockedReason("C01", true, 1, 2, 1));
        Assert.Null(CardEconomyRules.UpgradeBlockedReason("C01", true, 1, 3, 0));
        Assert.Null(CardEconomyRules.UpgradeBlockedReason("C01", true, 1, 4, 1));
        Assert.NotNull(CardEconomyRules.UpgradeBlockedReason("C01", true, 10, 5, 0));
        Assert.NotNull(CardEconomyRules.UpgradeBlockedReason("C01", false, 0, 0, 0));
    }

    [Fact]
    public void One_trained_copy_keeps_its_level_through_shuffle_duel_and_room_restart()
    {
        string[] ids = ["C01", "C01", "C02", "C03"];
        var levels = CardEconomyRules.DeckLevels(ids, new Dictionary<string, int> { ["C01"] = 5, ["C02"] = 2 });
        Assert.Equal([5, 0, 2, 0], levels);
        var catalog = CombatCardCatalog.CreatePrototype();
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 42);
        var player = room.AddPlayer(new(playerId, HeroClass.Mage, ids, null, CardLevels: levels));
        var initialCards = AllCards(player.Combat.Deck).ToDictionary(card => card.InstanceId);
        player.Combat.Deck.DiscardPlayed(player.Combat.Deck.Hand.ToArray());
        player.Combat.DrawImmediate(4);
        player.Combat.PrepareForDuel(new Random(9));
        var json = JsonSerializer.Serialize(room.Capture());
        var restored = BattleRoom.Restore(JsonSerializer.Deserialize<BattleRoomSnapshot>(json)!, catalog, 42);
        var restoredCards = AllCards(restored.GetPlayer(playerId).Combat.Deck).ToArray();
        Assert.Equal(initialCards.Count, restoredCards.Length);
        Assert.All(restoredCards, card => Assert.Equal(initialCards[card.InstanceId], card));
        Assert.Equal([0, 5], restoredCards.Where(card => card.CardId == "C01").Select(card => card.Level).Order());
        var trained = Assert.Single(restoredCards, card => card.CardId == "C01" && card.Level == 5);
        var damage = CombatResolver.Resolve([catalog.Get(trained.CardId, trained.Level)], restored.GetPlayer(playerId).Combat);
        Assert.Equal(13, damage.Damage);
    }

    [Fact]
    public void Legacy_card_instances_restore_as_level_zero_and_invalid_levels_are_rejected()
    {
        var card = JsonSerializer.Deserialize<CombatCardInstance>(
            "{\"InstanceId\":\"00000000-0000-0000-0000-000000000001\",\"CardId\":\"C01\"}")!;
        Assert.Equal(0, card.Level);
        Assert.Throws<DomainValidationException>(() => CombatDeck.Create(["C01"], new Random(1), [6]));
        Assert.Throws<DomainValidationException>(() => CombatDeck.Create(["C01"], new Random(1), []));
    }

    private static IEnumerable<CombatCardInstance> AllCards(CombatDeck deck) =>
        deck.Hand.Concat(deck.Library).Concat(deck.Discard);
}
