using System.Globalization;
using FantasyCard.ConfigExporter;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonConfigCompilerTests
{
    [Fact]
    public void FormalWorkbookCompilesDeterministicallyWithoutChangingLegacyTables()
    {
        var tables = Read();
        Assert.Equal(32, tables.Count); // _README stays private; journey policy and weekly contracts are compiled together.
        Assert.Equal(2,tables.Single(table=>table.Name=="SeasonCrafting").Rows.Count);
        Assert.Equal(6,tables.Single(table=>table.Name=="SeasonMarkRules").Rows.Count);
        Assert.Equal(6, tables.Single(t => t.Name == "SeasonDifficulty").Rows.Count);
        Assert.Equal(24, tables.Single(t => t.Name == "SeasonLoot").Rows.Count);
        var first = ConfigCompiler.Compile("season-config-stage-1", tables, out var hash);
        var again = ConfigCompiler.Compile("season-config-stage-1", tables, out var againHash);
        Assert.Equal(hash, againHash);
        Assert.Equal(first, again);
        Assert.Contains(Convert.FromHexString(hash), first);
    }

    [Theory]
    [InlineData("Economy","daily-shop-refresh-limit","int_value",5L)]
    [InlineData("Backpacks","Advanced","price_gold",799L)]
    [InlineData("ShopCardPrices","White","price_gold",79L)]
    [InlineData("CardLevels","C01:4","requires_copy",false)]
    public void ShopDependenciesMustRetainOriginalPricesLimitsAndCopyRequirements(string name,string key,string field,object value)
    {
        var tables=Read();var table=tables.Single(t=>t.Name==name);var index=table.Columns.Select((c,i)=>(c,i)).Single(x=>x.c.Name==field).i;
        var rows=table.Rows.Select(row=>
        {
            if(!Equals(row[0].Value,key))return row;
            var changed=row.ToArray();changed[index]=new(changed[index].Type,value);return changed;
        }).ToArray();
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("invalid-shop",tables.Select(t=>t==table?t with {Rows=rows}:t).ToArray(),out _));
    }

    [Theory]
    [InlineData("SeasonDifficulty", "hp_scale", 0)]
    [InlineData("SeasonDifficulty", "entry_quality_cap", 6)]
    [InlineData("SeasonDifficulty", "purple_affix_chance", -0.1)]
    [InlineData("SeasonLoot", "white_weight", 0.71)]
    [InlineData("SeasonLoot", "promotion_cap", 3)]
    [InlineData("SeasonLoot", "quality_cap", 0)]
    [InlineData("SeasonEquipment", "cost_1", 0)]
    [InlineData("SeasonEquipment", "speed_base", 1)]
    [InlineData("SeasonProgression", "xp_to_next_42", 0)]
    [InlineData("SeasonJourneyRules", "outer_xp", 7)]
    [InlineData("SeasonJourneyRules", "catch_up_multiplier", 3)]
    [InlineData("SeasonJourneyRules", "reference_days", 0)]
    [InlineData("SeasonJourneyRules", "main_reward_levels", 30)]
    [InlineData("SeasonWeeklyContracts", "target", 0)]
    [InlineData("SeasonWeeklyContracts", "xp_reward", 600)]
    [InlineData("SeasonRedRules", "weekly_quota", 2)]
    [InlineData("SeasonRedRules", "min_difficulty", 1)]
    [InlineData("SeasonRedRules", "boss_chance", 1.01)]
    [InlineData("SeasonRedRules", "week_start_hour", 24)]
    [InlineData("SeasonMarketRules", "shared_slots", 9)]
    [InlineData("SeasonMarketRules", "tax_rate", -0.01)]
    [InlineData("SeasonMarketRules", "orange_price_cap", 0)]
    [InlineData("SeasonActivityExchange", "cost_tokens", 0)]
    [InlineData("SeasonBotRewards", "gold", 6)]
    [InlineData("SeasonBotRewards", "fragments", 2)]
    [InlineData("SeasonBotRewards", "equipment_chance_bp", 1001)]
    [InlineData("SeasonBotRewards", "equipment_level", 1)]
    [InlineData("SeasonBotRewards", "maximum_per_human", 2)]
    [InlineData("SeasonLootPreference", "preferred_weight", 3999)]
    [InlineData("SeasonLootPreference", "other_weight", 1501)]
    [InlineData("SeasonCrafting", "mark_cost", 0)]
    [InlineData("SeasonCrafting", "reforge_fragment_cost", 0)]
    [InlineData("SeasonCrafting", "wish_attempts", 4)]
    [InlineData("SeasonMarkRules", "match_cap", 5)]
    [InlineData("SeasonMarkRules", "elite_marks", 2)]
    [InlineData("SeasonShopRules", "reset_hour", 0)]
    [InlineData("SeasonShopRules", "white_weight", 51)]
    [InlineData("SeasonShopRules", "class_soul_daily_limit", 3)]
    [InlineData("SeasonShopRules", "paid_bag_cap", 4)]
    [InlineData("SeasonShopProducts", "amount", 4)]
    [InlineData("SeasonShopProducts", "price_gold", 249)]
    [InlineData("SeasonShopProducts", "daily_limit", 6)]
    [InlineData("SeasonActivityRules", "token_cap", 24)]
    [InlineData("SeasonActivityRules", "tokens_per_completion", 12)]
    [InlineData("SeasonActivityRules", "direct_gold", 1)]
    [InlineData("SeasonActivityRules", "direct_red_materials", 1)]
    [InlineData("SeasonActivityCalendar", "days", 4)]
    public void InvalidSeasonNumbersAreRejectedBeforePublishing(string table, string field, double value)
    {
        var tables = Change(Read(),table,field,value);
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("invalid",tables,out _));
    }

    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(double.NegativeInfinity)]
    public void NonfiniteValuesCannotEnterEitherBundle(double value)
    {
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("invalid",Change(Read(),"SeasonDifficulty","hp_scale",value),out _));
    }

    [Theory]
    [InlineData("SeasonLoot", "difficulty_id", "D9")]
    [InlineData("SeasonLoot", "layer_id", "unknown")]
    [InlineData("SeasonDifficulty", "difficulty_id", "D9")]
    [InlineData("SeasonEquipment", "quality_id", "red")]
    [InlineData("SeasonRedRules", "timezone", "UTC")]
    [InlineData("SeasonMarketRules", "currency", "fragments")]
    [InlineData("SeasonActivityExchange", "reward_kind", "red-equipment")]
    [InlineData("SeasonCrafting", "quality_id", "Red")]
    [InlineData("SeasonCrafting", "mark_kind", "opaque-marks")]
    [InlineData("SeasonMarkRules", "mark_kind", "opaque-marks")]
    public void UnknownSeasonReferencesAreRejected(string table, string field, string value)
    {
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("invalid",Change(Read(),table,field,value),out _));
    }

    [Fact]
    public void SeasonTablesMustBePublishedAsOneValidatedGroup()
    {
        var tables = Read();
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Validate(tables.Where(t => t.Name != "SeasonLoot").ToArray()));
        ConfigCompiler.Validate(tables.Where(t => !t.Name.StartsWith("Season",StringComparison.Ordinal)).ToArray());
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Validate(tables.Where(t => t.Name == "SeasonBorrowedDecks" || !t.Name.StartsWith("Season",StringComparison.Ordinal)).ToArray()));
    }

    [Theory]
    [InlineData("slot_index", -1L)]
    [InlineData("slot_index", 1L)]
    [InlineData("hero_class", "Mage")]
    [InlineData("card_id", "unknown")]
    [InlineData("card_id", "MAG-01")]
    [InlineData("card_id", "M-FIREBAT")]
    [InlineData("template_id", "other")]
    public void BorrowedTemplatesCannotPublishMissingSlotsWrongClassesOrNoncollectibleCards(string field, object value)
    {
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Compile("invalid-loan",Change(Read(),"SeasonBorrowedDecks",field,value),out _));
    }

    [Fact]
    public void ServerOnlyQuotaMetadataCannotBeChangedToClientOrOptional()
    {
        var tables = Read();
        var table = tables.Single(t => t.Name == "SeasonRedRules");
        var columns = table.Columns.ToArray();
        columns[1] = columns[1] with { Scope = PublishScope.Both };
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Validate(tables.Select(t => t == table ? t with { Columns = columns } : t).ToArray()));
        columns[1] = table.Columns[1] with { Required = false };
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Validate(tables.Select(t => t == table ? t with { Columns = columns } : t).ToArray()));
    }

    [Theory]
    [InlineData("None")] [InlineData("fire")]
    public void InvalidLootPreferenceDefaultsAreRejected(string element) =>
        Assert.Throws<InvalidDataException>(()=>ConfigCompiler.Compile("invalid",Change(Read(),"SeasonLootPreference","default_element",element),out _));

    [Fact]
    public void DuplicateDifficultyLayerPairsCannotHideAMissingPair()
    {
        var tables = Read();
        var table = tables.Single(t => t.Name == "SeasonLoot");
        var rows = table.Rows.ToArray();
        var changed = rows[1].ToArray();
        changed[2] = rows[0][2];
        rows[1] = changed;
        Assert.Throws<InvalidDataException>(() => ConfigCompiler.Validate(tables.Select(t => t == table ? t with { Rows = rows } : t).ToArray()));
    }

    private static ConfigTable[] Change(IReadOnlyList<ConfigTable> tables, string name, string field, object value)
    {
        var table = tables.Single(t => t.Name == name);
        var column = table.Columns.Select((c,i) => (c,i)).Single(x => x.c.Name == field);
        var rows = table.Rows.ToArray();
        var changed = rows[0].ToArray();
        object converted = column.c.Type == ConfigValueType.WholeNumber ? Convert.ToInt64(value,CultureInfo.InvariantCulture) : value;
        changed[column.i] = new(column.c.Type,converted);
        rows[0] = changed;
        return tables.Select(t => t == table ? t with { Rows = rows } : t).ToArray();
    }

    private static IReadOnlyList<ConfigTable> Read()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            var path = Path.Combine(directory.FullName,"config/FantasyCard_Config.xlsx");
            if (File.Exists(path)) return XlsxConfigReader.Read(path);
            directory = directory.Parent;
        }
        throw new FileNotFoundException("The formal source workbook must be included in the pinned test input.");
    }
}
