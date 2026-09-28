using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Configuration;

public sealed class GameConfigCatalogTests
{
    private static readonly string[] TuningQualities = ["White", "Green", "Blue", "Purple"];

    [Fact]
    public void EmbeddedCatalogContainsCompleteGdd068CardSet()
    {
        var catalog = GameConfigCatalog.Current;

        Assert.Equal("gdd-0.68-element-tuning-1", catalog.Version);
        Assert.Equal(232, catalog.Cards.Count);
        Assert.Equal(220, catalog.Cards.Count(card => card.IsCodex));
        Assert.Equal(12, catalog.Cards.Count(card => !card.IsCodex));
        Assert.Equal(51, catalog.Cards.Count(card => card.InitiallyUnlocked));
        Assert.Equal(1320, catalog.CardLevels.Count);
        var orderedCodex = catalog.Cards.Where(card => card.IsCodex).ToArray();
        Assert.Equal(
            orderedCodex
                .OrderBy(card => card.Rarity)
                .ThenBy(card => card.HeroClass is null ? 0 : 1)
                .ThenBy(card => card.HeroClass ?? (HeroClass)short.MaxValue)
                .ThenBy(card => card.CardId, StringComparer.Ordinal),
            orderedCodex);
        var tuningCards = catalog.Cards.Where(card => card.Effect.IsElementTuning).ToArray();
        Assert.Equal(20, tuningCards.Length);
        Assert.All(Enum.GetValues<CardElement>().Where(element => element != CardElement.None),
            element => Assert.Equal(4, tuningCards.Count(card => card.Effect.Element == element)));
        Assert.All(TuningQualities,
            quality => Assert.Equal(5, tuningCards.Count(card => card.Quality == quality)));

        var apocalypse = Assert.Single(catalog.Cards, card => card.CardId == "PRI-10");
        Assert.Equal(8, apocalypse.Effect.Heal);
        Assert.Equal(8, apocalypse.Effect.Shield);
        Assert.Equal(1, apocalypse.Effect.ImmediateDraw);
        Assert.Equal(1.2, apocalypse.Effect.StunSeconds);
        Assert.Equal(240, apocalypse.UnlockCost);

        var finalLevel = Assert.Single(catalog.CardLevels, row => row.CardId == "GO10" && row.Level == 5);
        Assert.Equal(600, finalLevel.SoulCost);
        Assert.True(finalLevel.RequiresCopy);
        Assert.Equal(0.4, finalLevel.DurationBonus);
        Assert.True(catalog.Cards.Single(card => card.CardId == "GO10").Effect.IsClassReveal);
        var voidCore = catalog.Cards.Single(card => card.CardId == "M-VOIDCORE").Effect;
        Assert.Equal((8, CardElement.Fire, 8, CardElement.Metal, 8),
            (voidCore.ElementalDamage, voidCore.Element, voidCore.SecondaryElementalDamage,
                voidCore.SecondaryElement, voidCore.Shield));

    }

    [Fact]
    public void EmbeddedCatalogVersionMatchesPublishedClientPackage()
    {
        AssertPublishedConfigMatchesCatalog(GameConfigCatalog.Current.Version);
    }

    private static void AssertPublishedConfigMatchesCatalog(string embeddedVersion)
    {
        var (serverGenerated, repoRoot) = FindPublishedConfigRoots();
        Assert.Equal(embeddedVersion, File.ReadAllText(Path.Combine(serverGenerated, "fantasycard.config.version.txt")).Trim());
        if (repoRoot is null) return;

        var clientGenerated = Path.Combine(repoRoot, "client", "data", "generated");
        var catalogPath = Path.Combine(repoRoot, "client", "data", "catalog.json");
        if (!Directory.Exists(clientGenerated) || !File.Exists(catalogPath)) return;

        Assert.Equal(embeddedVersion, File.ReadAllText(Path.Combine(clientGenerated, "fantasycard.config.version.txt")).Trim());
        Assert.Equal(
            File.ReadAllBytes(Path.Combine(serverGenerated, "fantasycard.config.bytes")),
            File.ReadAllBytes(Path.Combine(clientGenerated, "fantasycard.config.bytes")));
        using var document = System.Text.Json.JsonDocument.Parse(File.ReadAllText(catalogPath));
        Assert.Equal(embeddedVersion, document.RootElement.GetProperty("version").GetString());
    }

    private static (string ServerGenerated, string? RepoRoot) FindPublishedConfigRoots()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var nested = Path.Combine(directory.FullName, "server", "config", "generated", "fantasycard.config.version.txt");
            if (File.Exists(nested))
                return (Path.GetDirectoryName(nested)!, directory.FullName);

            var local = Path.Combine(directory.FullName, "config", "generated", "fantasycard.config.version.txt");
            if (File.Exists(local))
            {
                var serverGenerated = Path.GetDirectoryName(local)!;
                var repoRoot = Path.GetFullPath(Path.Combine(directory.FullName, ".."));
                return (serverGenerated, Directory.Exists(Path.Combine(repoRoot, "client", "data")) ? repoRoot : null);
            }

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate the published server config version file.");
    }

    [Fact]
    public void EmbeddedCatalogContainsEquipmentAndLootRules()
    {
        var catalog = GameConfigCatalog.Current;

        Assert.Equal(6, catalog.EquipmentQualities.Count);
        var orange = catalog.EquipmentQuality("Orange");
        Assert.Equal(.22, orange.Damage);
        Assert.Equal(.13, orange.Resistance);
        Assert.Equal(.03, orange.DamagePerLevel);
        Assert.Equal(1024, orange.EnhancementCost(5));
        Assert.Equal(1984, orange.EnhanceTotalCost);
        Assert.True(orange.EnabledInPrototype);
        Assert.False(catalog.EquipmentQuality("Red").EnabledInPrototype);

        var outer = catalog.LootLayer(ChaosMapLayer.Outer);
        Assert.Equal(14, outer.HealPercentagePoints);
        Assert.Equal(10, outer.Gold);
        Assert.Equal((1, 3), (outer.WarriorSoulMin, outer.WarriorSoulMax));
        Assert.Equal("White", outer.RollEquipmentQuality(69));
        Assert.Equal("Green", outer.RollEquipmentQuality(70));

        var boss = catalog.LootLayer(ChaosMapLayer.Core, isBoss: true);
        Assert.Equal(32, boss.HealPercentagePoints);
        Assert.Equal(60, boss.Gold);
        Assert.Equal("Purple", boss.RollEquipmentQuality(59));
        Assert.Equal("Orange", boss.RollEquipmentQuality(60));
        Assert.Equal([60, 180, 450], catalog.RewardRefreshes.Select(item => item.Gold).ToArray());
    }

    [Fact]
    public void EmbeddedCatalogContainsBackpackAndEconomyRules()
    {
        var catalog = GameConfigCatalog.Current;

        Assert.Equal(
            [("Free", 20, 0, 0), ("Advanced", 28, 1, 800), ("Top", 36, 3, 2200)],
            catalog.Backpacks.Select(item => (item.Id, item.Capacity, item.SafeSlots, item.PriceGold)).ToArray());
        Assert.Equal(8, catalog.Economy.MarketActiveListings);
        Assert.Equal(48, catalog.Economy.MarketDurationHours);
        Assert.Equal(.1, catalog.Economy.MarketFeeRate);
        Assert.Equal(100, catalog.Economy.HealthPotionPrice);
        Assert.Equal(.2, catalog.Economy.HealthPotionHealRate);
        Assert.Equal(3, catalog.Economy.DailyCardSlots);
        Assert.Equal(
            [("White", 80, 1), ("Green", 150, 1), ("Blue", 280, 1), ("Purple", 500, 1)],
            catalog.ShopCardPrices.Select(item => (item.Quality, item.PriceGold, item.DailyLimit)).ToArray());
    }
}
