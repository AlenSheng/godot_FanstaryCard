using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class BattleRoomSeasonContextTests
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public void FullRoomJsonRecoveryRetainsItsSeasonAndEffectiveLevels(int difficulty)
    {
        var context = new SeasonContext("original", difficulty, "season-v1", "pinned", "stats-v1");
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), context.ConfigVersion, catalog, 73, season: context);
        var player = Guid.NewGuid();
        var cards = Enumerable.Range(1, 13).Select(i => $"C{i:D2}")
            .Concat(Enumerable.Range(1, 7).Select(i => $"MAG-{i:D2}")).ToArray();
        Assert.Equal(20, cards.Distinct().Count());
        Assert.All(cards, id => Assert.Equal(difficulty, CardEconomyRules.Level(id, difficulty).Level));
        room.AddPlayer(new(player, HeroClass.Mage, cards,
            null, WeaponLevel: difficulty, CardLevels: Enumerable.Repeat(difficulty, 20).ToArray()));
        room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        var persisted = JsonSerializer.Deserialize<BattleRoomSnapshot>(JsonSerializer.Serialize(room.Capture(), Json), Json)!;
        var restored = BattleRoom.Restore(persisted, catalog, 73);
        Assert.Equal(context, restored.Season);
        Assert.Equal(70, restored.GetPlayer(player).Combat.MaximumHp);
        Assert.Equal(difficulty, restored.GetPlayer(player).Combat.WeaponLevel);
        Assert.Equivalent(persisted, restored.Capture(), strict: true);
    }

    [Fact]
    public void ConstructingOrRestoringAnotherConfigCannotRelabelTheSeason()
    {
        var context = new SeasonContext("original", 0, "season-v1", "pinned", "stats-v1");
        var catalog = CombatCardCatalog.CreatePrototype();
        Assert.Throws<DomainValidationException>(() => new BattleRoom(Guid.NewGuid(), "different", catalog, 73, season: context));
        var room = new BattleRoom(Guid.NewGuid(), "pinned", catalog, 73, season: context);
        Assert.Throws<DomainValidationException>(() => BattleRoom.Restore(room.Capture() with { ConfigVersion = "different" }, catalog, 73));
    }

    [Fact]
    public void LegacyJsonWithoutSeasonRemainsLegacyWhenRestored()
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "legacy", catalog, 73);
        var json = System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(room.Capture(), Json))!.AsObject();
        json.Remove("season");
        var restored = BattleRoom.Restore(json.Deserialize<BattleRoomSnapshot>(Json)!, catalog, 73);
        Assert.Null(restored.Season);
        Assert.Equal("legacy", restored.ConfigVersion);
    }
}
