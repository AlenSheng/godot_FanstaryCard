using System.Globalization;
using FantasyCard.ConfigExporter;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonConfigCompilerTests
{
    [Fact]
    public void FormalWorkbookCompilesDeterministicallyWithoutChangingLegacyTables()
    {
        var tables = Read();
        Assert.Equal(21, tables.Count); // The original _README remains non-published; the loan sheet adds sixty slots.
        Assert.Equal(6, tables.Single(t => t.Name == "SeasonDifficulty").Rows.Count);
        Assert.Equal(24, tables.Single(t => t.Name == "SeasonLoot").Rows.Count);
        var first = ConfigCompiler.Compile("season-config-stage-1", tables, out var hash);
        var again = ConfigCompiler.Compile("season-config-stage-1", tables, out var againHash);
        Assert.Equal(hash, againHash);
        Assert.Equal(first, again);
        Assert.Contains(Convert.FromHexString(hash), first);
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
    [InlineData("SeasonRedRules", "weekly_quota", 2)]
    [InlineData("SeasonRedRules", "min_difficulty", 1)]
    [InlineData("SeasonRedRules", "boss_chance", 1.01)]
    [InlineData("SeasonRedRules", "week_start_hour", 24)]
    [InlineData("SeasonMarketRules", "shared_slots", 9)]
    [InlineData("SeasonMarketRules", "tax_rate", -0.01)]
    [InlineData("SeasonMarketRules", "orange_price_cap", 0)]
    [InlineData("SeasonActivityExchange", "cost_tokens", 0)]
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
