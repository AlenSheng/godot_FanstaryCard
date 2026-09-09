using System.Buffers.Binary;
using System.Reflection;
using System.Text;
using FantasyCard.Domain.Combat;
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

public sealed record EconomyConfig(
    int MarketActiveListings,
    int MarketDurationHours,
    double MarketFeeRate,
    int HealthPotionPrice,
    double HealthPotionHealRate,
    int DailyCardSlots);

public sealed class GameConfigCatalog
{
    private const string ResourceName = "FantasyCard.Config.fantasycard.config.bytes";
    private static readonly Lazy<GameConfigCatalog> Active = new(LoadEmbedded);

    private GameConfigCatalog(
        string version,
        IReadOnlyList<CardConfigDefinition> cards,
        IReadOnlyList<CardLevelConfig> cardLevels,
        IReadOnlyList<EquipmentQualityConfig> equipmentQualities,
        IReadOnlyList<LootLayerConfig> lootLayers,
        IReadOnlyList<RewardRefreshConfig> rewardRefreshes,
        IReadOnlyList<BackpackConfig> backpacks,
        IReadOnlyList<ShopCardPriceConfig> shopCardPrices,
        EconomyConfig economy)
    {
        Version = version;
        Cards = cards;
        CardLevels = cardLevels;
        EquipmentQualities = equipmentQualities;
        LootLayers = lootLayers;
        RewardRefreshes = rewardRefreshes;
        Backpacks = backpacks;
        ShopCardPrices = shopCardPrices;
        Economy = economy;
    }

    public static GameConfigCatalog Current => Active.Value;
    public string Version { get; }
    public IReadOnlyList<CardConfigDefinition> Cards { get; }
    public IReadOnlyList<CardLevelConfig> CardLevels { get; }
    public IReadOnlyList<EquipmentQualityConfig> EquipmentQualities { get; }
    public IReadOnlyList<LootLayerConfig> LootLayers { get; }
    public IReadOnlyList<RewardRefreshConfig> RewardRefreshes { get; }
    public IReadOnlyList<BackpackConfig> Backpacks { get; }
    public IReadOnlyList<ShopCardPriceConfig> ShopCardPrices { get; }
    public EconomyConfig Economy { get; }

    public EquipmentQualityConfig EquipmentQuality(string quality) =>
        EquipmentQualities.SingleOrDefault(item => string.Equals(item.Quality, quality, StringComparison.Ordinal))
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

    private static GameConfigCatalog LoadEmbedded()
    {
        using var stream = typeof(GameConfigCatalog).Assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException($"Embedded game config '{ResourceName}' is missing.");
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        var bundle = ConfigBundleReader.Read(memory.ToArray());
        var cardsTable = bundle.Table("Cards");
        var levelsTable = bundle.Table("CardLevels");
        var equipmentTable = bundle.Table("EquipmentQuality");
        var lootTable = bundle.Table("LootRules");
        var backpackTable = bundle.Table("Backpacks");
        var shopCardPriceTable = bundle.Table("ShopCardPrices");
        var economyTable = bundle.Table("Economy");
        var cards = cardsTable.Rows.Select(row => ReadCard(cardsTable, row)).Where(card => card.Enabled).ToArray();
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
                EconomyDouble("health-potion-heal-rate"), EconomyInt("daily-card-slots"));
        }
        catch (KeyNotFoundException exception)
        {
            throw new InvalidDataException("Economy is missing a required runtime value.", exception);
        }

        if (cards.Count(card => card.IsCodex) != 200 || cards.Count(card => !card.IsCodex) != 12)
            throw new InvalidDataException("Active config must contain 200 codex cards and 12 monster cards.");
        if (cards.Count(card => card.InitiallyUnlocked) != 51)
            throw new InvalidDataException("Active config must contain exactly 51 initially unlocked cards.");
        if (levels.Length != 1200)
            throw new InvalidDataException("Active config must contain 1200 card-level rows.");
        ValidateEquipment(equipment);
        ValidateLoot(lootLayers, refreshes);
        ValidateBackpacks(backpacks);
        ValidateEconomy(economy, shopCardPrices, cards);
        return new GameConfigCatalog(
            bundle.Version, cards, levels, equipment, lootLayers, refreshes, backpacks, shopCardPrices, economy);
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
            economy.HealthPotionHealRate is <= 0 or > 1 || economy.DailyCardSlots != 3)
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

    private static CardConfigDefinition ReadCard(ConfigTable table, object?[] row) => new(
        table.Text(row, "id"),
        table.Text(row, "name"),
        table.Text(row, "source"),
        table.Text(row, "category"),
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
            table.Bool(row, "is_class_reveal")),
        table.Bool(row, "is_codex"),
        table.Bool(row, "initially_unlocked"),
        table.Int(row, "unlock_cost"),
        table.Int(row, "copy_cost"),
        table.Bool(row, "enabled"));

    private static HeroClass? ParseHeroClass(string? value) => value is null
        ? null
        : Enum.Parse<HeroClass>(value, ignoreCase: false);

    private static CardElement ParseElement(string? value) => string.IsNullOrEmpty(value) || value == "None"
        ? CardElement.None
        : Enum.Parse<CardElement>(value, ignoreCase: false);
}

internal sealed record ConfigBundle(string Version, IReadOnlyList<ConfigTable> Tables)
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
    public string? OptionalText(object?[] row, string name) => row[_indexes[name]] as string;
    public int Int(object?[] row, string name) => checked((int)(long)(row[_indexes[name]] ?? 0L));
    public double Double(object?[] row, string name) => row[_indexes[name]] is double value ? value : 0;
    public bool Bool(object?[] row, string name) => row[_indexes[name]] is true;
}

internal static class ConfigBundleReader
{
    public static ConfigBundle Read(ReadOnlySpan<byte> data)
    {
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
        return new ConfigBundle(version, tables);
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
            var length = checked((int)Varint());
            if (_offset + length > _data.Length) throw new InvalidDataException("Invalid protobuf length.");
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
