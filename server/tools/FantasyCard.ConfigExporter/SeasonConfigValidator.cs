using System.Globalization;

namespace FantasyCard.ConfigExporter;

/// <summary>Validates the seasonal configuration group before either bundle is published.</summary>
public static class SeasonConfigValidator
{
    private static readonly Dictionary<string, string> Schemas = new(StringComparer.Ordinal)
    {
        ["SeasonDifficulty"] = "difficulty_id:s,name_key:s,hp_scale:d,shield_scale:d,damage_scale:d,interval_scale:d,gold_scale:d,soul_scale:d,fragment_scale:d,quality_cap:i,purple_affix_chance:d,entry_quality_cap:i,red_boss_enabled:b",
        ["SeasonLoot"] = "loot_rule_id:s,difficulty_id:s,layer_id:s,white_weight:d,green_weight:d,blue_weight:d,purple_weight:d,orange_weight:d,quality_cap:i,promotion_cap:i",
        ["SeasonEquipment"] = "quality_id:s,damage_base:d,resist_base:d,damage_per_level:d,resist_per_level:d,speed_base:d,speed_per_level:d,cost_1:i,cost_2:i,cost_3:i,cost_4:i,cost_5:i",
        ["SeasonProgression"] = "level_id:s,level:i,xp_to_next_42:i",
        ["SeasonRedRules"] = "rule_id:s,weekly_quota:i,min_difficulty:i,boss_chance:d,chest_enabled:b,chest_chance:d,timezone:s,week_start_hour:i",
        ["SeasonMarketRules"] = "rule_id:s,currency:s,tax_rate:d,min_fee:i,listing_hours:i,shared_slots:i,orange_price_cap:i,red_price_cap:i",
        ["SeasonActivityExchange"] = "rule_id:s,cost_tokens:i,reward_kind:s,reward_count:i,per_event_limit:i"
    };
    private static readonly string[] DifficultyIds = ["D0", "D1", "D2", "D3", "D4", "D5"];
    private static readonly string[] Layers = ["outer", "middle", "elite", "boss"];
    private static readonly string[] Qualities = ["white", "green", "blue", "purple", "orange"];
    private static readonly string[] Weights = ["white_weight", "green_weight", "blue_weight", "purple_weight", "orange_weight"];
    private static readonly string[] DifficultyScales = ["hp_scale", "shield_scale", "damage_scale", "interval_scale", "gold_scale", "soul_scale", "fragment_scale"];
    private static readonly string[] EquipmentStats = ["damage_base", "resist_base", "damage_per_level", "resist_per_level", "speed_base", "speed_per_level"];
    private static readonly string[] Currencies = ["gold", "diamond"];

    public static void Validate(IReadOnlyList<ConfigTable> tables)
    {
        var present = tables.Where(t => Schemas.ContainsKey(t.Name)).ToDictionary(t => t.Name, StringComparer.Ordinal);
        if (present.Count == 0)
        {
            if (tables.Any(table => table.Name == "SeasonBorrowedDecks"))
                throw new InvalidDataException("Borrowed templates require the seasonal configuration group.");
            return; // Archived pre-season workbooks remain valid.
        }
        foreach (var (name, schema) in Schemas)
        {
            if (!present.TryGetValue(name, out var table)) throw new InvalidDataException($"Season configuration is missing table '{name}'.");
            var scope = name is "SeasonRedRules" or "SeasonMarketRules" or "SeasonActivityExchange" ? PublishScope.Server : PublishScope.Both;
            foreach (var entry in schema.Split(','))
            {
                var parts = entry.Split(':');
                var column = table.Columns.SingleOrDefault(c => c.Name == parts[0]);
                var type = parts[1] switch { "s" => ConfigValueType.Text, "d" => ConfigValueType.FloatingPoint, "i" => ConfigValueType.WholeNumber, "b" => ConfigValueType.Logical, _ => throw new InvalidOperationException() };
                if (column is null || column.Type != type || !column.Required || column.Scope != scope)
                    throw new InvalidDataException($"{name}.{parts[0]}: required seasonal column has an invalid type, required flag or publish scope.");
            }
        }
        ValidateDifficulties(present["SeasonDifficulty"]);
        ValidateLoot(present["SeasonLoot"], present["SeasonDifficulty"]);
        ValidateEquipment(present["SeasonEquipment"]);
        ValidateProgression(present["SeasonProgression"]);
        ValidateRed(present["SeasonRedRules"]);
        ValidateMarket(present["SeasonMarketRules"]);
        ValidateBorrowedDecks(tables);
        foreach (var row in present["SeasonActivityExchange"].Rows)
        {
            var table = present["SeasonActivityExchange"];
            Check(N(table,row,"cost_tokens") > 0 && N(table,row,"reward_count") > 0 && N(table,row,"per_event_limit") > 0, table, "exchange cost, quantity and limit must be positive");
            Check(S(table,row,"reward_kind") is "bound_fragments" or "bound_warrior_soul" or "bound_class_soul" or "potion", table, "unsupported activity reward kind");
        }
    }

    private static void ValidateBorrowedDecks(IReadOnlyList<ConfigTable> tables)
    {
        var table = tables.SingleOrDefault(value => value.Name == "SeasonBorrowedDecks");
        if (table is null) return;
        foreach (var field in new[] {"id","template_id","hero_class","slot_index","card_id"})
        {
            var column = table.Columns.SingleOrDefault(value => value.Name == field);
            Check(column is not null && column.Required && column.Scope == PublishScope.Both &&
                column.Type == (field == "slot_index" ? ConfigValueType.WholeNumber : ConfigValueType.Text),table,"invalid borrowed-template metadata");
        }
        var cards = tables.Single(value => value.Name == "Cards");
        var cardIds = cards.Rows.Where(row => B(cards,row,"enabled") && B(cards,row,"is_codex"))
            .ToDictionary(row => S(cards,row,"id"),StringComparer.Ordinal);
        var classes = new HashSet<string>(StringComparer.Ordinal);
        Check(table.Rows.Count == 60,table,"borrowed templates require sixty card rows");
        foreach (var group in table.Rows.GroupBy(row => S(table,row,"template_id"),StringComparer.Ordinal))
        {
            var rows = group.OrderBy(row => N(table,row,"slot_index")).ToArray();
            Check(rows.Length == 20 && rows.Select(row => N(table,row,"slot_index")).SequenceEqual(Enumerable.Range(0,20).Select(value => (double)value)),table,"borrowed slots must be zero through nineteen");
            var hero = S(table,rows[0],"hero_class");
            Check(hero is "Mage" or "Priest" or "Guardian" && classes.Add(hero) && rows.All(row => S(table,row,"hero_class") == hero),table,"requires one template per class");
            Check(rows.Select(row => S(table,row,"card_id")).Distinct(StringComparer.Ordinal).Count()==20,table,"borrowed cards must use unique legal slots");
            foreach (var row in rows)
            {
                Check(cardIds.TryGetValue(S(table,row,"card_id"),out var card),table,"borrowed card is not a published collectible");
                var ownerIndex = cards.Columns.Select((column,index) => (column,index)).Single(value => value.column.Name == "hero_class").index;
                Check(card![ownerIndex].Value is null || (string)card[ownerIndex].Value! == hero,table,"borrowed card belongs to another class");
            }
        }
        Check(classes.Count == 3,table,"requires all three class templates");
    }

    private static void ValidateDifficulties(ConfigTable table)
    {
        Check(table.Rows.Count == DifficultyIds.Length && table.Rows.Select(r => S(table,r,"difficulty_id")).ToHashSet(StringComparer.Ordinal).SetEquals(DifficultyIds), table, "must contain exactly D0 through D5");
        foreach (var row in table.Rows)
        {
            Check(DifficultyScales.All(f => N(table,row,f) > 0), table, "scales must be positive");
            Check(DifficultyScales.All(f => N(table,row,f) <= int.MaxValue / 10000d &&
                (decimal)N(table,row,f) * 10000 >= 1 &&
                (decimal)N(table,row,f) * 10000 == decimal.Truncate((decimal)N(table,row,f) * 10000)), table,
                "scales must fit positive basis points with at most four decimal places");
            Check(N(table,row,"quality_cap") is >= 0 and <= 4 && N(table,row,"entry_quality_cap") is >= 0 and <= 5, table, "quality caps are outside ordinary/entry ranks");
            Probability(table,row,"purple_affix_chance");
            Check(!B(table,row,"red_boss_enabled") || S(table,row,"difficulty_id") is not ("D0" or "D1"), table, "red Boss rewards require at least D2");
        }
    }

    private static void ValidateLoot(ConfigTable table, ConfigTable difficulty)
    {
        Check(table.Rows.Count == DifficultyIds.Length * Layers.Length, table, "must contain all six difficulties and four cell types");
        var pairs = new HashSet<(string Difficulty, string Layer)>();
        foreach (var row in table.Rows)
        {
            var id = S(table,row,"difficulty_id"); var layer = S(table,row,"layer_id");
            Check(DifficultyIds.Contains(id,StringComparer.Ordinal) && Layers.Contains(layer,StringComparer.Ordinal) && pairs.Add((id,layer)), table, "unknown or duplicate difficulty/cell reference");
            foreach (var field in Weights)
            {
                Probability(table,row,field);
                var fixedPoint=(decimal)N(table,row,field)*10000;
                Check(fixedPoint==decimal.Truncate(fixedPoint),table,"loot probabilities support at most four decimal places");
            }
            Check(Math.Abs(Weights.Sum(f => N(table,row,f)) - 1) < 1e-9, table, "quality weights must sum to one");
            var cap = N(table,row,"quality_cap");
            var parent = difficulty.Rows.Single(r => S(difficulty,r,"difficulty_id") == id);
            Check(cap is >= 0 and <= 4 && cap <= N(difficulty,parent,"quality_cap") && N(table,row,"promotion_cap") >= 0 && N(table,row,"promotion_cap") <= cap, table, "loot/promotion cap exceeds its allowed rank");
            Check(N(table,row,"promotion_cap")<=3 && (layer!="outer" || cap<=3),table,"promotion and outer-layer caps cannot exceed purple");
            Check(Weights.Select((field,rank)=>(field,rank)).All(value=>value.rank<=cap || N(table,row,value.field)==0),table,"base weights cannot exceed the final cap");
            Check(Weights.Select((field,rank) => rank <= cap || N(table,row,field) == 0).All(x => x), table, "probability exists above the final quality cap");
        }
    }

    private static void ValidateEquipment(ConfigTable table)
    {
        Check(table.Rows.Count == Qualities.Length && table.Rows.Select(r => S(table,r,"quality_id")).ToHashSet(StringComparer.Ordinal).SetEquals(Qualities), table, "must contain exactly five ordinary qualities; red rules are separate");
        foreach (var row in table.Rows)
        {
            foreach (var field in EquipmentStats)
                Check(N(table,row,field) >= 0, table, $"{field} must be nonnegative");
            for (var level = 1; level <= 5; level++) Check(N(table,row,$"cost_{level}") > 0, table, "enhancement costs must be positive");
            Check(N(table,row,"resist_base") <= 1 && N(table,row,"speed_base") < 1, table, "base resistance or interval reduction is outside bounds");
        }
    }

    private static void ValidateProgression(ConfigTable table)
    {
        Check(table.Rows.Count == 30, table, "requires thirty progression levels");
        Check(table.Rows.Select(r => N(table,r,"level")).ToHashSet().SetEquals(Enumerable.Range(0,30).Select(x => (double)x)), table, "requires unique levels zero through twenty-nine");
        Check(table.Rows.All(r => N(table,r,"xp_to_next_42") > 0), table, "progression XP must be positive");
    }

    private static void ValidateRed(ConfigTable table)
    {
        Check(table.Rows.Count == 1, table, "requires one shared red quota policy");
        foreach (var row in table.Rows)
        {
            Check(N(table,row,"weekly_quota") == 1 && N(table,row,"min_difficulty") is >= 2 and <= 5, table, "red quota must be one per logical server/week and Boss access at least D2");
            Probability(table,row,"boss_chance"); Probability(table,row,"chest_chance");
            Check(S(table,row,"timezone") == "Asia/Shanghai" && N(table,row,"week_start_hour") is >= 0 and <= 23, table, "invalid weekly quota timezone/hour");
        }
    }

    private static void ValidateMarket(ConfigTable table)
    {
        Check(table.Rows.Count == 2 && table.Rows.Select(r => S(table,r,"currency")).ToHashSet(StringComparer.Ordinal).SetEquals(Currencies), table, "requires separate gold and diamond policies");
        double? slots = null;
        foreach (var row in table.Rows)
        {
            Probability(table,row,"tax_rate");
            Check(N(table,row,"min_fee") >= 1 && N(table,row,"listing_hours") > 0 && N(table,row,"shared_slots") > 0 && N(table,row,"orange_price_cap") > 0 && N(table,row,"red_price_cap") > 0, table, "market limits, fees and price caps must be positive");
            slots ??= N(table,row,"shared_slots");
            Check(slots == N(table,row,"shared_slots"), table, "currencies must share the same total listing slots");
        }
    }

    private static object Value(ConfigTable table, IReadOnlyList<ConfigValue> row, string field) =>
        row[table.Columns.Select((column,index) => (column,index)).Single(x => x.column.Name == field).index].Value
        ?? throw new InvalidDataException($"{table.Name}.{field}: null seasonal value.");
    private static string S(ConfigTable table, IReadOnlyList<ConfigValue> row, string field) => (string)Value(table,row,field);
    private static double N(ConfigTable table, IReadOnlyList<ConfigValue> row, string field) => Convert.ToDouble(Value(table,row,field),CultureInfo.InvariantCulture);
    private static bool B(ConfigTable table, IReadOnlyList<ConfigValue> row, string field) => (bool)Value(table,row,field);
    private static void Probability(ConfigTable table, IReadOnlyList<ConfigValue> row, string field) => Check(N(table,row,field) is >= 0 and <= 1, table, $"{field} must be a probability");
    private static void Check(bool condition, ConfigTable table, string message)
    {
        if (!condition) throw new InvalidDataException($"{table.Name}: {message}.");
    }
}
