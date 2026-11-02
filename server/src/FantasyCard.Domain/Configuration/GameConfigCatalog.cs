using System.Buffers.Binary;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Configuration;

public sealed record CardConfigDefinition(
    string CardId,
    string Name,
    string Source,
    string Category,
    HeroClass? HeroClass,
    string? MonsterType,
    string? Quality,
    CombatCardEffect Effect,
    bool IsCodex,
    bool InitiallyUnlocked,
    int UnlockCost,
    int CopyCost,
    bool Enabled)
{
    public short Rarity => Quality switch
    {
        "White" => 1,
        "Green" => 2,
        "Blue" => 3,
        "Purple" => 4,
        "Orange" => 5,
        null when !IsCodex => 1,
        _ => throw new InvalidDataException($"Card '{CardId}' has unsupported quality '{Quality}'.")
    };
}

public sealed record CardLevelConfig(
    string CardId,
    int Level,
    int ValueBonus,
    double DurationBonus,
    int SoulCost,
    bool RequiresCopy);

public sealed record EquipmentQualityConfig(
    string Quality, int Rank, double Damage, double Resistance,
    double DamagePerLevel, double ResistancePerLevel,
    double Piercing, double BulwarkReduction, double BulwarkShield,
    double VitalityHeal, double VitalityOvercap, double AffixPerLevel,
    double PiercingCap, double BulwarkReductionCap, double BulwarkShieldCap,
    double DrawInterval, double DrawIntervalPerLevel, double ForcedEscape,
    double AffixDropRate, int EnhanceCost1, int EnhanceCost2, int EnhanceCost3,
    int EnhanceCost4, int EnhanceCost5, int EnhanceTotalCost, bool EnabledInPrototype)
{
    public int EnhancementCost(int targetLevel) => targetLevel switch
    {
        1 => EnhanceCost1, 2 => EnhanceCost2, 3 => EnhanceCost3,
        4 => EnhanceCost4, 5 => EnhanceCost5,
        _ => throw new DomainValidationException("Equipment target level must be between one and five.")
    };
}

public sealed record LootLayerConfig(
    string Layer, double HealPercent, int Gold,
    int WarriorSoulMin, int WarriorSoulMax, int ClassSoul,
    int FragmentMin, int FragmentMax,
    double WhiteRate, double GreenRate, double BlueRate, double PurpleRate, double OrangeRate)
{
    public int HealPercentagePoints => checked((int)Math.Round(HealPercent * 100, MidpointRounding.AwayFromZero));

    public string RollEquipmentQuality(int roll)
    {
        if (roll is < 0 or >= 100) throw new ArgumentOutOfRangeException(nameof(roll));
        var threshold = 0;
        foreach (var entry in new[]
                 {
                     (Quality: "White", Rate: WhiteRate), (Quality: "Green", Rate: GreenRate),
                     (Quality: "Blue", Rate: BlueRate), (Quality: "Purple", Rate: PurpleRate),
                     (Quality: "Orange", Rate: OrangeRate)
                 })
        {
            threshold += checked((int)Math.Round(entry.Rate * 100, MidpointRounding.AwayFromZero));
            if (roll < threshold) return entry.Quality;
        }
        throw new InvalidDataException($"Loot layer '{Layer}' equipment rates do not cover roll {roll}.");
    }
}

public sealed record RewardRefreshConfig(int Index, int Gold);

public sealed record BackpackConfig(string Id, int Capacity, int SafeSlots, int PriceGold);

public sealed record ShopCardPriceConfig(string Quality, int PriceGold, int DailyLimit);

public sealed record ItemConfigDefinition(string Id, string Kind, int Quality, string? IconKey, bool Enabled)
{
    public string QualityName => Quality switch
    {
        1 => "White", 2 => "Green", 3 => "Blue", 4 => "Purple", 5 => "Orange", 6 => "Red",
        _ => throw new InvalidDataException($"Item '{Id}' has unsupported quality rank '{Quality}'.")
    };
}

public sealed record EconomyConfig(
    int MarketActiveListings,
    int MarketDurationHours,
    double MarketFeeRate,
    int HealthPotionPrice,
    double HealthPotionHealRate,
    int DailyCardSlots,
    int DailyShopRefreshLimit);

public sealed record SeasonBorrowedDeckConfig(string TemplateId, HeroClass HeroClass, IReadOnlyList<string> CardIds);

public sealed class GameConfigCatalog
{
    private const string ResourceName = "FantasyCard.Config.fantasycard.config.bytes";
    private static readonly Lazy<GameConfigCatalog> Active = new(LoadEmbedded);
    private readonly byte[] _publishedBytes;

    private GameConfigCatalog(
        string version,
        string contentHash,
        byte[] publishedBytes,
        IReadOnlyList<CardConfigDefinition> cards,
        IReadOnlyList<CardLevelConfig> cardLevels,
        IReadOnlyList<EquipmentQualityConfig> equipmentQualities,
        IReadOnlyList<LootLayerConfig> lootLayers,
        IReadOnlyList<RewardRefreshConfig> rewardRefreshes,
        IReadOnlyList<BackpackConfig> backpacks,
        IReadOnlyList<ShopCardPriceConfig> shopCardPrices,
        IReadOnlyList<ItemConfigDefinition> items,
        EconomyConfig economy)
    {
        Version = version;
        ContentHash = contentHash;
        _publishedBytes = publishedBytes;
        Cards = cards;
        CardLevels = cardLevels;
        EquipmentQualities = equipmentQualities;
        LootLayers = lootLayers;
        RewardRefreshes = rewardRefreshes;
        Backpacks = backpacks;
        ShopCardPrices = shopCardPrices;
        Items = items;
        Economy = economy;
    }

    public static GameConfigCatalog Current => Active.Value;
    public NumericalRules Numerics { get; private init; } = NumericalRules.Legacy;
    public string Version { get; }
    public string ContentHash { get; }
    public byte[] ExportPublishedBytes() => _publishedBytes.ToArray();
    public IReadOnlyList<CardConfigDefinition> Cards { get; }
    public IReadOnlyList<CardLevelConfig> CardLevels { get; }
    public IReadOnlyList<EquipmentQualityConfig> EquipmentQualities { get; }
    public IReadOnlyList<LootLayerConfig> LootLayers { get; }
    public IReadOnlyList<RewardRefreshConfig> RewardRefreshes { get; }
    public IReadOnlyList<BackpackConfig> Backpacks { get; }
    public IReadOnlyList<ShopCardPriceConfig> ShopCardPrices { get; }
    public IReadOnlyList<ItemConfigDefinition> Items { get; }
    public EconomyConfig Economy { get; }
    public IReadOnlyList<SeasonDifficultyConfig> SeasonDifficulties { get; private init; } = [];
    public IReadOnlyList<SeasonBorrowedDeckConfig> SeasonBorrowedDecks { get; private init; } = [];
    public IReadOnlyList<SeasonLootConfig> SeasonLootRules { get; private init; } = [];
    public SeasonEquipmentConfig? SeasonEquipment { get; private init; }
    public SeasonEquipmentConfig? ResolveSeasonEquipment(string statsVersion)
    {
        // Pre-C05 archives have no explicit equipment-version policy and keep their legacy values.
        if(SeasonEquipment is null)return null;
        return SeasonEquipment.StatsVersion==statsVersion ? SeasonEquipment
            : throw new DomainValidationException("The selected equipment stats version is not published in this configuration.");
    }
    private static readonly string[] SeasonLootWeightFields = ["white_weight","green_weight","blue_weight","purple_weight","orange_weight"];
    public SeasonLootConfig SeasonLoot(int difficulty,string layerId) =>
        SeasonLootRules.SingleOrDefault(rule=>rule.Difficulty==difficulty && rule.LayerId==layerId)
        ?? throw new InvalidDataException("The frozen seasonal loot rule is not published.");
    public SeasonBorrowedDeckConfig BorrowedDeck(HeroClass heroClass) =>
        SeasonBorrowedDecks.SingleOrDefault(value => value.HeroClass == heroClass)
        ?? throw new InvalidDataException("The selected seasonal borrowed deck is not published.");
    public SeasonDifficultyConfig SeasonDifficulty(int difficulty) =>
        SeasonDifficulties.SingleOrDefault(value => value.Id == $"D{difficulty}")
        ?? throw new InvalidDataException($"Season difficulty D{difficulty} is not published in configuration '{Version}'.");

    public EquipmentQualityConfig EquipmentQuality(string quality,string? statsVersion = null) =>
        (statsVersion is null ? null : ResolveSeasonEquipment(statsVersion))?.Quality(quality)
        ?? EquipmentQualities.SingleOrDefault(item => string.Equals(item.Quality, quality, StringComparison.Ordinal))
        ?? throw new DomainValidationException($"Unknown equipment quality '{quality}'.");

    public LootLayerConfig LootLayer(ChaosMapLayer layer, bool isBoss = false)
    {
        var name = isBoss ? "Boss" : layer.ToString();
        return LootLayers.SingleOrDefault(item => string.Equals(item.Layer, name, StringComparison.Ordinal))
            ?? throw new InvalidDataException($"Loot layer '{name}' is missing from active config.");
    }

    public int RewardRefreshGold(int refreshIndex) =>
        RewardRefreshes.SingleOrDefault(item => item.Index == refreshIndex)?.Gold
        ?? throw new DomainValidationException("The reward refresh limit has been reached.");

    public BackpackConfig Backpack(string id) =>
        Backpacks.SingleOrDefault(item => string.Equals(item.Id, id, StringComparison.Ordinal))
        ?? throw new DomainValidationException($"Unknown backpack tier '{id}'.");

    public ShopCardPriceConfig ShopCardPrice(string quality) =>
        ShopCardPrices.SingleOrDefault(item => string.Equals(item.Quality, quality, StringComparison.Ordinal))
        ?? throw new DomainValidationException($"Unknown shop card quality '{quality}'.");

    public ItemConfigDefinition Item(string id, string kind) =>
        Items.SingleOrDefault(item => string.Equals(item.Id, id, StringComparison.Ordinal))
        ?? Items.FirstOrDefault(item => string.Equals(item.Kind, kind, StringComparison.Ordinal))
        ?? throw new DomainValidationException($"Unknown item '{id}' ({kind}).");

    private static GameConfigCatalog LoadEmbedded()
    {
        using var stream = typeof(GameConfigCatalog).Assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException($"Embedded game config '{ResourceName}' is missing.");
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        return Load(memory.ToArray());
    }

    /// <summary>Loads a complete published bundle after checking its embedded content hash.</summary>
    public static GameConfigCatalog Load(ReadOnlySpan<byte> bytes)
    {
        var bundle = ConfigBundleReader.Read(bytes);
        var cardsTable = bundle.Table("Cards");
        var levelsTable = bundle.Table("CardLevels");
        var equipmentTable = bundle.Table("EquipmentQuality");
        var lootTable = bundle.Table("LootRules");
        var backpackTable = bundle.Table("Backpacks");
        var shopCardPriceTable = bundle.Table("ShopCardPrices");
        var itemsTable = bundle.Table("Items");
        var economyTable = bundle.Table("Economy");
        var cards = cardsTable.Rows
            .Select(row => ReadCard(cardsTable, row))
            .Where(card => card.Enabled)
            .OrderBy(card => card.IsCodex ? 0 : 1)
            .ThenBy(card => card.IsCodex ? card.Rarity : short.MaxValue)
            .ThenBy(card => card.HeroClass is null ? 0 : 1)
            .ThenBy(card => card.HeroClass ?? (HeroClass)short.MaxValue)
            .ThenBy(card => card.CardId, StringComparer.Ordinal)
            .ToArray();
        var levels = levelsTable.Rows.Select(row => new CardLevelConfig(
            levelsTable.Text(row, "card_id"),
            levelsTable.Int(row, "level"),
            levelsTable.Int(row, "value_bonus"),
            levelsTable.Double(row, "duration_bonus"),
            levelsTable.Int(row, "soul_cost"),
            levelsTable.Bool(row, "requires_copy"))).ToArray();
        var equipment = equipmentTable.Rows.Select(row => new EquipmentQualityConfig(
            equipmentTable.Text(row, "id"), equipmentTable.Int(row, "rank"),
            equipmentTable.Double(row, "damage_percent"), equipmentTable.Double(row, "resistance_percent"),
            equipmentTable.Double(row, "damage_per_level"), equipmentTable.Double(row, "resistance_per_level"),
            equipmentTable.Double(row, "piercing_percent"), equipmentTable.Double(row, "bulwark_reduction_percent"),
            equipmentTable.Double(row, "bulwark_shield_percent"), equipmentTable.Double(row, "vitality_heal_percent"),
            equipmentTable.Double(row, "vitality_overcap_percent"), equipmentTable.Double(row, "affix_per_level"),
            equipmentTable.Double(row, "piercing_cap_percent"), equipmentTable.Double(row, "bulwark_reduction_cap_percent"),
            equipmentTable.Double(row, "bulwark_shield_cap_percent"), equipmentTable.Double(row, "draw_interval_percent"),
            equipmentTable.Double(row, "draw_interval_per_level"), equipmentTable.Double(row, "forced_escape_percent"),
            equipmentTable.Double(row, "affix_drop_rate"), equipmentTable.Int(row, "enhance_cost_1"),
            equipmentTable.Int(row, "enhance_cost_2"), equipmentTable.Int(row, "enhance_cost_3"),
            equipmentTable.Int(row, "enhance_cost_4"), equipmentTable.Int(row, "enhance_cost_5"),
            equipmentTable.Int(row, "enhance_total_cost"), equipmentTable.Bool(row, "enabled_in_prototype"))).ToArray();
        var lootLayers = lootTable.Rows.Where(row => lootTable.OptionalText(row, "layer") is not null)
            .Select(row => new LootLayerConfig(
                lootTable.Text(row, "layer"), lootTable.Double(row, "heal_percent"), lootTable.Int(row, "gold"),
                lootTable.Int(row, "warrior_soul_min"), lootTable.Int(row, "warrior_soul_max"), lootTable.Int(row, "class_soul"),
                lootTable.Int(row, "fragment_min"), lootTable.Int(row, "fragment_max"),
                lootTable.Double(row, "white_rate"), lootTable.Double(row, "green_rate"), lootTable.Double(row, "blue_rate"),
                lootTable.Double(row, "purple_rate"), lootTable.Double(row, "orange_rate"))).ToArray();
        var refreshes = lootTable.Rows.Where(row => lootTable.Int(row, "refresh_index") > 0)
            .Select(row => new RewardRefreshConfig(
                lootTable.Int(row, "refresh_index"), lootTable.Int(row, "refresh_gold"))).ToArray();
        var backpacks = backpackTable.Rows.Select(row => new BackpackConfig(
            backpackTable.Text(row, "id"), backpackTable.Int(row, "capacity"),
            backpackTable.Int(row, "safe_slots"), backpackTable.Int(row, "price_gold"))).ToArray();
        var shopCardPrices = shopCardPriceTable.Rows.Select(row => new ShopCardPriceConfig(
            shopCardPriceTable.Text(row, "id"), shopCardPriceTable.Int(row, "price_gold"),
            shopCardPriceTable.Int(row, "daily_limit"))).ToArray();
        var items = itemsTable.Rows.Select(row => new ItemConfigDefinition(
            itemsTable.Text(row, "id"), itemsTable.Text(row, "kind"), itemsTable.Int(row, "quality"),
            itemsTable.OptionalText(row, "icon_key"), itemsTable.Bool(row, "enabled")))
            .Where(item => item.Enabled).ToArray();
        var economyValues = economyTable.Rows.ToDictionary(
            row => economyTable.Text(row, "id"), row => row, StringComparer.Ordinal);
        int EconomyInt(string id) => economyTable.Int(economyValues[id], "int_value");
        double EconomyDouble(string id) => economyTable.Double(economyValues[id], "double_value");
        EconomyConfig economy;
        try
        {
            economy = new EconomyConfig(
                EconomyInt("market-active-listings"), EconomyInt("market-duration-hours"),
                EconomyDouble("market-fee-rate"), EconomyInt("health-potion-price"),
                EconomyDouble("health-potion-heal-rate"), EconomyInt("daily-card-slots"),
                EconomyInt("daily-shop-refresh-limit"));
        }
        catch (KeyNotFoundException exception)
        {
            throw new InvalidDataException("Economy is missing a required runtime value.", exception);
        }

        if (cards.Count(card => card.IsCodex) != 220 || cards.Count(card => !card.IsCodex) != 12)
            throw new InvalidDataException("Active config must contain 220 codex cards and 12 monster cards.");
        if (cards.Count(card => card.InitiallyUnlocked) != 51)
            throw new InvalidDataException("Active config must contain exactly 51 initially unlocked cards.");
        if (levels.Length != 1320)
            throw new InvalidDataException("Active config must contain 1320 card-level rows.");
        ValidateEquipment(equipment);
        ValidateLoot(lootLayers, refreshes);
        ValidateBackpacks(backpacks);
        ValidateEconomy(economy, shopCardPrices, cards);
        ValidateItems(items);
        return new GameConfigCatalog(
            bundle.Version, bundle.ContentHash, bytes.ToArray(), cards, levels, equipment, lootLayers, refreshes, backpacks, shopCardPrices, items, economy)
            { Numerics = ReadNumerics(bundle), SeasonDifficulties = ReadSeasonDifficulties(bundle), SeasonBorrowedDecks = ReadBorrowedDecks(bundle,cards), SeasonLootRules = ReadSeasonLoot(bundle),SeasonEquipment=ReadSeasonEquipment(bundle,equipment) };
    }

    private static SeasonEquipmentConfig? ReadSeasonEquipment(ConfigBundle bundle,EquipmentQualityConfig[] legacy)
    {
        var rules=bundle.Tables.SingleOrDefault(value=>value.Name=="SeasonEquipmentRules");
        if(rules is null)return null;
        if(rules.Rows.Count!=1)throw new InvalidDataException("SeasonEquipmentRules must contain one active stats version.");
        var row=rules.Rows[0];var version=rules.Text(row,"stats_version");var table=bundle.Table("SeasonEquipment");
        var qualities=table.Rows.Select(values=>
        {
            if(table.Text(values,"stats_version")!=version)throw new InvalidDataException("Season equipment and rule versions differ.");
            var id=table.Text(values,"quality_id");var original=legacy.SingleOrDefault(value=>value.Quality.Equals(id,StringComparison.OrdinalIgnoreCase))
                ??throw new InvalidDataException("Unknown seasonal equipment quality.");
            return original with {Damage=table.Double(values,"damage_base"),Resistance=table.Double(values,"resist_base"),
                DamagePerLevel=table.Double(values,"damage_per_level"),ResistancePerLevel=table.Double(values,"resist_per_level"),
                DrawInterval=-table.Double(values,"speed_base"),DrawIntervalPerLevel=-table.Double(values,"speed_per_level"),
                EnhanceCost1=table.Int(values,"cost_1"),EnhanceCost2=table.Int(values,"cost_2"),EnhanceCost3=table.Int(values,"cost_3"),
                EnhanceCost4=table.Int(values,"cost_4"),EnhanceCost5=table.Int(values,"cost_5"),
                EnhanceTotalCost=Enumerable.Range(1,5).Sum(level=>table.Int(values,$"cost_{level}"))};
        }).ToArray();
        var chance=rules.Double(row,"chain_draw_chance");
        if(!double.IsFinite(chance) || chance is <0 or >1)throw new InvalidDataException("Invalid chain-draw probability.");
        var fixedChance=(decimal)chance*10000;
        if(fixedChance!=decimal.Truncate(fixedChance))throw new InvalidDataException("Invalid chain-draw probability.");
        var config=new SeasonEquipmentConfig(version,qualities,rules.Double(row,"resistance_cap"),rules.Double(row,"draw_floor_seconds"),
            rules.Double(row,"draw_ceiling_seconds"),rules.Double(row,"inferno_bonus"),rules.Double(row,"rapid_draw_reduction"),
            rules.Double(row,"rapid_draw_floor_seconds"),checked((int)fixedChance),rules.Int(row,"opening_draw_count"),rules.Double(row,"golden_cicada_bonus"));
        config.Validate();return config;
    }

    private static SeasonLootConfig[] ReadSeasonLoot(ConfigBundle bundle)
    {
        var table=bundle.Tables.SingleOrDefault(value=>value.Name=="SeasonLoot");
        if(table is null)return [];
        var rows=table.Rows.Select(row=>new SeasonLootConfig(table.Text(row,"loot_rule_id"),
            table.Text(row,"difficulty_id") is {Length:2} id && id[0]=='D' && id[1] is >= '0' and <= '5' ? id[1]-'0' : -1,
            table.Text(row,"layer_id"),
            SeasonLootWeightFields.Select(field=>
            {
                var value=table.Double(row,field);
                if(!double.IsFinite(value) || value<0 || value>1)
                    throw new InvalidDataException("Seasonal loot probabilities must have at most four decimal places.");
                var scaled=(decimal)value*SeasonLootConfig.ProbabilityBasis;
                if(scaled!=decimal.Truncate(scaled))throw new InvalidDataException("Seasonal loot probabilities must have at most four decimal places.");
                return checked((int)scaled);
            }).ToArray(),table.Int(row,"quality_cap"),table.Int(row,"promotion_cap"))).ToArray();
        foreach(var row in rows)row.Validate();
        if(rows.Length!=24 || rows.Select(row=>(row.Difficulty,row.LayerId)).Distinct().Count()!=24)
            throw new InvalidDataException("All twenty-four seasonal loot rules must be published together.");
        return rows;
    }

    private static SeasonBorrowedDeckConfig[] ReadBorrowedDecks(ConfigBundle bundle, CardConfigDefinition[] cards)
    {
        var table = bundle.Tables.SingleOrDefault(value => value.Name == "SeasonBorrowedDecks");
        if (table is null) return [];
        var available = cards.Where(card => card.IsCodex).ToDictionary(card => card.CardId,
            card => new OwnedCard(card.CardId,card.HeroClass,(CardRarity)card.Rarity,1,false),StringComparer.Ordinal);
        var templates = new List<SeasonBorrowedDeckConfig>();
        foreach (var group in table.Rows.GroupBy(row => table.Text(row,"template_id"),StringComparer.Ordinal))
        {
            var ordered = group.OrderBy(row => table.Int(row,"slot_index")).ToArray();
            if (ordered.Length != 20 || !ordered.Select(row => table.Int(row,"slot_index")).SequenceEqual(Enumerable.Range(0,20)) ||
                ordered.Select(row => table.Text(row,"hero_class")).Distinct(StringComparer.Ordinal).Count() != 1 ||
                !Enum.TryParse<HeroClass>(table.Text(ordered[0],"hero_class"),out var hero) || !Enum.IsDefined(hero))
                throw new InvalidDataException("Borrowed templates require one class and twenty ordered slots.");
            var ids = ordered.Select(row => table.Text(row,"card_id")).ToArray();
            DeckRules.Validate(hero,ids,available);
            templates.Add(new(group.Key,hero,ids));
        }
        if (templates.Count != 3 || templates.Select(value => value.HeroClass).Distinct().Count() != 3)
            throw new InvalidDataException("Borrowed templates require exactly one legal deck per class.");
        return templates.ToArray();
    }

    private static SeasonDifficultyConfig[] ReadSeasonDifficulties(ConfigBundle bundle)
    {
        var table = bundle.Tables.SingleOrDefault(value => value.Name == "SeasonDifficulty");
        if (table is null) return [];
        var rows = table.Rows.Select(row => new SeasonDifficultyConfig(table.Text(row,"difficulty_id"),table.Text(row,"name_key"),
            SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"hp_scale")),SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"shield_scale")),
            SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"damage_scale")),SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"interval_scale")),
            SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"gold_scale")),SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"soul_scale")),
            SeasonDifficultyConfig.ToBasisPoints(table.Double(row,"fragment_scale")),table.Int(row,"quality_cap"),table.Int(row,"entry_quality_cap"),
            table.Double(row,"purple_affix_chance"),table.Bool(row,"red_boss_enabled"))).ToArray();
        if (rows.Length != 6 || !rows.Select(value => value.Id).ToHashSet(StringComparer.Ordinal).SetEquals(Enumerable.Range(0,6).Select(value => $"D{value}")) ||
            rows.Any(value => value.QualityCap is < 0 or > 4 || value.EntryQualityCap is < 0 or > 5 || !double.IsFinite(value.PurpleAffixChance) || value.PurpleAffixChance is < 0 or > 1))
            throw new InvalidDataException("SeasonDifficulty must contain valid D0 through D5 rows.");
        return rows;
    }

    private static NumericalRules ReadNumerics(ConfigBundle bundle)
    {
        var table = bundle.Tables.SingleOrDefault(value => value.Name == "NumericalRules");
        if (table is null) return NumericalRules.Legacy;
        if (table.Rows.Count != 1) throw new InvalidDataException("NumericalRules must contain one active row.");
        var row = table.Rows[0];
        var rules = new NumericalRules(table.Bool(row, "cards_spent_draw"), table.Bool(row, "fractional_guardian"),
            table.Bool(row, "optional_monster_pool"), table.Int(row, "monster_capacity"),
            table.Bool(row, "budgeted_bot_loot"), table.Int(row, "bot_loot_count"), table.Bool(row, "mortal_bot_pve"));
        rules.Validate();
        return rules;
    }

    private static void ValidateItems(ItemConfigDefinition[] items)
    {
        if (items.Length == 0 || items.Any(item => item.Quality is < 1 or > 6 || string.IsNullOrWhiteSpace(item.Kind)))
            throw new InvalidDataException("Items must contain enabled rows with quality ranks from one to six.");
    }

    private static void ValidateEquipment(IReadOnlyList<EquipmentQualityConfig> equipment)
    {
        string[] expected = ["White", "Green", "Blue", "Purple", "Orange", "Red"];
        if (!equipment.Select(item => item.Quality).SequenceEqual(expected, StringComparer.Ordinal) ||
            !equipment.Select(item => item.Rank).SequenceEqual(Enumerable.Range(1, 6)))
            throw new InvalidDataException("EquipmentQuality must contain ordered White through Red rows.");
        foreach (var item in equipment)
        {
            var costs = Enumerable.Range(1, 5).Select(item.EnhancementCost).ToArray();
            if (costs.Any(cost => cost <= 0) || costs.Sum() != item.EnhanceTotalCost)
                throw new InvalidDataException($"Equipment quality '{item.Quality}' enhancement costs are invalid.");
            double[] rates = [item.Damage, item.Resistance, item.DamagePerLevel, item.ResistancePerLevel,
                item.Piercing, item.BulwarkReduction, item.BulwarkShield, item.VitalityHeal, item.VitalityOvercap,
                item.AffixPerLevel, item.PiercingCap, item.BulwarkReductionCap, item.BulwarkShieldCap,
                -item.DrawInterval, -item.DrawIntervalPerLevel, item.ForcedEscape, item.AffixDropRate];
            if (rates.Any(rate => rate is < 0 or > 1))
                throw new InvalidDataException($"Equipment quality '{item.Quality}' contains an invalid percentage.");
        }
        if (equipment.Single(item => item.Quality == "Red").EnabledInPrototype ||
            equipment.Where(item => item.Quality != "Red").Any(item => !item.EnabledInPrototype))
            throw new InvalidDataException("Only Red equipment may be disabled in the prototype.");
    }

    private static void ValidateLoot(IReadOnlyList<LootLayerConfig> layers, IReadOnlyList<RewardRefreshConfig> refreshes)
    {
        string[] expected = ["Outer", "Middle", "Core", "Boss"];
        if (!layers.Select(item => item.Layer).SequenceEqual(expected, StringComparer.Ordinal))
            throw new InvalidDataException("LootRules must contain ordered Outer through Boss layer rows.");
        foreach (var layer in layers)
        {
            var rate = layer.WhiteRate + layer.GreenRate + layer.BlueRate + layer.PurpleRate + layer.OrangeRate;
            if (Math.Abs(rate - 1) > 0.000001 || layer.HealPercent is <= 0 or > 1 || layer.Gold <= 0 ||
                layer.WarriorSoulMin <= 0 || layer.WarriorSoulMax < layer.WarriorSoulMin ||
                layer.ClassSoul <= 0 || layer.FragmentMin <= 0 || layer.FragmentMax < layer.FragmentMin)
                throw new InvalidDataException($"Loot layer '{layer.Layer}' is invalid.");
        }
        if (!refreshes.Select(item => item.Index).SequenceEqual([1, 2, 3]) || refreshes.Any(item => item.Gold <= 0))
            throw new InvalidDataException("LootRules must contain three positive reward refresh costs.");
    }

    private static void ValidateBackpacks(BackpackConfig[] backpacks)
    {
        string[] expected = ["Free", "Advanced", "Top"];
        if (!backpacks.Select(item => item.Id).SequenceEqual(expected, StringComparer.Ordinal))
            throw new InvalidDataException("Backpacks must contain ordered Free, Advanced, and Top rows.");
        if (backpacks.Any(item => item.Capacity <= 0 || item.SafeSlots < 0 ||
                                  item.SafeSlots > item.Capacity || item.PriceGold < 0) ||
            backpacks[0].PriceGold != 0 || backpacks.Skip(1).Any(item => item.PriceGold == 0))
            throw new InvalidDataException("Backpacks contains an invalid capacity, safe-slot count, or price.");
    }

    private static void ValidateEconomy(
        EconomyConfig economy,
        IReadOnlyList<ShopCardPriceConfig> shopCardPrices,
        IReadOnlyList<CardConfigDefinition> cards)
    {
        if (economy.MarketActiveListings <= 0 || economy.MarketDurationHours <= 0 ||
            economy.MarketFeeRate is <= 0 or >= 1 || economy.HealthPotionPrice <= 0 ||
            economy.HealthPotionHealRate is <= 0 or > 1 || economy.DailyCardSlots != 3 ||
            economy.DailyShopRefreshLimit <= 0)
            throw new InvalidDataException("Economy contains an invalid market or health-potion value.");

        string[] expectedQualities = ["White", "Green", "Blue", "Purple"];
        if (!shopCardPrices.Select(item => item.Quality).SequenceEqual(expectedQualities, StringComparer.Ordinal) ||
            shopCardPrices.Any(item => item.PriceGold <= 0 || item.DailyLimit != 1) ||
            !shopCardPrices.Select(item => item.PriceGold).SequenceEqual([80, 150, 280, 500]))
            throw new InvalidDataException("ShopCardPrices must contain the GDD White-through-Purple prices and limit one.");
        if (cards.Count(card => card.IsCodex && card.Quality is not null &&
                                expectedQualities.Contains(card.Quality, StringComparer.Ordinal)) < economy.DailyCardSlots)
            throw new InvalidDataException("The active card catalog cannot fill the daily shop card slots.");
    }

    private static CardConfigDefinition ReadCard(ConfigTable table, object?[] row)
    {
        var category = table.Text(row, "category");
        return new(
            table.Text(row, "id"),
            table.Text(row, "name"),
            table.Text(row, "source"),
            category,
            ParseHeroClass(table.OptionalText(row, "hero_class")),
            table.OptionalText(row, "monster_type"),
            table.OptionalText(row, "quality"),
            new CombatCardEffect(
                table.Int(row, "elemental_damage"),
                ParseElement(table.OptionalText(row, "element")),
                table.Int(row, "direct_damage"),
                table.Int(row, "heal"),
                table.Int(row, "shield"),
                table.Double(row, "draw_charge"),
                table.Int(row, "immediate_draw"),
                table.Double(row, "draw_speed_modifier"),
                table.Double(row, "draw_speed_seconds"),
                table.Double(row, "stun_seconds"),
                table.Double(row, "draw_block_seconds"),
                table.Int(row, "health_cost"),
                table.Int(row, "same_element_bonus"),
                table.Int(row, "resonance_bonus"),
                table.Double(row, "conflict_cancel_bonus"),
                table.Double(row, "conflict_heal_coefficient"),
                table.Bool(row, "is_class_reveal"),
                table.OptionalInt(row, "secondary_elemental_damage"),
                ParseElement(table.OptionalText(row, "secondary_element")),
                IsElementTuning: string.Equals(category, "ElementTune", StringComparison.Ordinal)),
            table.Bool(row, "is_codex"),
            table.Bool(row, "initially_unlocked"),
            table.Int(row, "unlock_cost"),
            table.Int(row, "copy_cost"),
            table.Bool(row, "enabled"));
    }

    private static HeroClass? ParseHeroClass(string? value) => value is null
        ? null
        : Enum.Parse<HeroClass>(value, ignoreCase: false);

    private static CardElement ParseElement(string? value) => string.IsNullOrEmpty(value) || value == "None"
        ? CardElement.None
        : Enum.Parse<CardElement>(value, ignoreCase: false);
}

internal sealed record ConfigBundle(string Version, string ContentHash, IReadOnlyList<ConfigTable> Tables)
{
    public ConfigTable Table(string name) => Tables.Single(table => table.Name == name);
}

internal sealed class ConfigTable(string name, IReadOnlyList<string> columns, IReadOnlyList<object?[]> rows)
{
    private readonly Dictionary<string, int> _indexes = columns.Select((column, index) => (column, index))
        .ToDictionary(item => item.column, item => item.index, StringComparer.Ordinal);
    public string Name { get; } = name;
    public IReadOnlyList<object?[]> Rows { get; } = rows;
    public string Text(object?[] row, string name) => OptionalText(row, name) ?? throw new InvalidDataException($"{Name}.{name} is required.");
    public string? OptionalText(object?[] row, string name) => _indexes.TryGetValue(name, out var index) ? row[index] as string : null;
    public int OptionalInt(object?[] row, string name) => _indexes.TryGetValue(name, out var index)
        ? checked((int)(long)(row[index] ?? 0L)) : 0;
    public int Int(object?[] row, string name) => checked((int)(long)(row[_indexes[name]] ?? 0L));
    public double Double(object?[] row, string name) => row[_indexes[name]] is double value ? value : 0;
    public bool Bool(object?[] row, string name) => row[_indexes[name]] is true;
}

internal static class ConfigBundleReader
{
    public static ConfigBundle Read(ReadOnlySpan<byte> data)
    {
        var contentHash = ValidateContentHash(data);
        var reader = new ProtoReader(data);
        var version = string.Empty;
        var tables = new List<ConfigTable>();
        while (reader.TryTag(out var field, out var wire))
        {
            if (field == 1 && wire == 2) version = reader.String();
            else if (field == 3 && wire == 2) tables.Add(ReadTable(reader.Bytes()));
            else reader.Skip(wire);
        }
        if (string.IsNullOrWhiteSpace(version)) throw new InvalidDataException("Config bundle version is missing.");
        return new ConfigBundle(version, contentHash, tables);
    }

    private static string ValidateContentHash(ReadOnlySpan<byte> data)
    {
        var reader = new ProtoReader(data);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        byte[]? expected = null;
        while (true)
        {
            var start = reader.Position;
            if (!reader.TryTag(out var field, out var wire)) break;
            if (field == 2)
            {
                if (wire != 2 || expected is not null)
                    throw new InvalidDataException("Config bundle must contain one SHA-256 content hash.");
                expected = reader.Bytes().ToArray();
                if (expected.Length != 32)
                    throw new InvalidDataException("Config bundle content hash must have 32 bytes.");
            }
            else
            {
                reader.Skip(wire);
                hash.AppendData(data.Slice(start, reader.Position - start));
            }
        }
        if (expected is null || !CryptographicOperations.FixedTimeEquals(expected, hash.GetHashAndReset()))
            throw new InvalidDataException("Config bundle content hash is missing or does not match its data.");
        return Convert.ToHexString(expected).ToLowerInvariant();
    }

    private static ConfigTable ReadTable(ReadOnlySpan<byte> data)
    {
        var reader = new ProtoReader(data);
        var name = string.Empty;
        var columns = new List<string>();
        var rows = new List<object?[]>();
        while (reader.TryTag(out var field, out var wire))
        {
            if (field == 1 && wire == 2) name = reader.String();
            else if (field == 2 && wire == 2) columns.Add(ReadColumn(reader.Bytes()));
            else if (field == 3 && wire == 2) rows.Add(ReadRow(reader.Bytes(), columns.Count));
            else reader.Skip(wire);
        }
        return new ConfigTable(name, columns, rows);
    }

    private static string ReadColumn(ReadOnlySpan<byte> data)
    {
        var reader = new ProtoReader(data);
        var name = string.Empty;
        while (reader.TryTag(out var field, out var wire))
        {
            if (field == 1 && wire == 2) name = reader.String();
            else reader.Skip(wire);
        }
        return name;
    }

    private static object?[] ReadRow(ReadOnlySpan<byte> data, int columnCount)
    {
        var reader = new ProtoReader(data);
        var values = new List<object?>();
        while (reader.TryTag(out var field, out var wire))
        {
            if (field == 1 && wire == 2) values.Add(ReadValue(reader.Bytes()));
            else reader.Skip(wire);
        }
        if (values.Count != columnCount) throw new InvalidDataException("Config row column count mismatch.");
        return [.. values];
    }

    private static object? ReadValue(ReadOnlySpan<byte> data)
    {
        var reader = new ProtoReader(data);
        object? value = false;
        var isNull = false;
        while (reader.TryTag(out var field, out var wire))
        {
            switch (field)
            {
                case 1 when wire == 2: value = reader.String(); break;
                case 2 when wire == 0: value = checked((long)reader.Varint()); break;
                case 3 when wire == 1: value = reader.Double(); break;
                case 4 when wire == 0: value = reader.Varint() != 0; break;
                case 5 when wire == 0: isNull = reader.Varint() != 0; break;
                default: reader.Skip(wire); break;
            }
        }
        return isNull ? null : value;
    }

    private ref struct ProtoReader(ReadOnlySpan<byte> data)
    {
        private readonly ReadOnlySpan<byte> _data = data;
        private int _offset;
        public int Position => _offset;
        public bool TryTag(out int field, out int wire)
        {
            if (_offset >= _data.Length) { field = wire = 0; return false; }
            var tag = Varint(); field = checked((int)(tag >> 3)); wire = checked((int)(tag & 7)); return true;
        }
        public ulong Varint()
        {
            ulong value = 0; var shift = 0;
            while (_offset < _data.Length && shift < 64)
            {
                var current = _data[_offset++]; value |= (ulong)(current & 0x7F) << shift;
                if ((current & 0x80) == 0) return value;
                shift += 7;
            }
            throw new InvalidDataException("Invalid protobuf varint.");
        }
        public ReadOnlySpan<byte> Bytes()
        {
            var encodedLength = Varint();
            if (encodedLength > (ulong)(_data.Length - _offset)) throw new InvalidDataException("Invalid protobuf length.");
            var length = (int)encodedLength;
            var result = _data.Slice(_offset, length); _offset += length; return result;
        }
        public string String() => Encoding.UTF8.GetString(Bytes());
        public double Double()
        {
            if (_offset + 8 > _data.Length) throw new InvalidDataException("Invalid protobuf double.");
            var bits = BinaryPrimitives.ReadInt64LittleEndian(_data.Slice(_offset, 8)); _offset += 8;
            return BitConverter.Int64BitsToDouble(bits);
        }
        public void Skip(int wire)
        {
            switch (wire)
            {
                case 0: Varint(); break;
                case 1: _offset = checked(_offset + 8); break;
                case 2: Bytes(); break;
                case 5: _offset = checked(_offset + 4); break;
                default: throw new InvalidDataException($"Unsupported protobuf wire type {wire}.");
            }
            if (_offset > _data.Length) throw new InvalidDataException("Protobuf field exceeds input.");
        }
    }
}
