using System.IO.Compression;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

internal static class ElementMarginals
{
    internal static readonly string[] Replacements = ["ET-WOOD-G", "ET-EARTH-G", "ET-METAL-G", "ET-WATER-G"];
    private static readonly string[] Groups = ["O1", "O6", "E1", "BOSS"];
    public static int Run(string[] args)
    {
        string Option(string name, string fallback)
        {
            var i = Array.IndexOf(args, name);return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
        }
        var output = Path.GetFullPath(Option("--output", "element-marginals"));
        var sha = Option("--source-sha", "");
        var start = int.Parse(Option("--seed-start", "400001"), CultureInfo.InvariantCulture);
        var samples = int.Parse(Option("--samples", "3"), CultureInfo.InvariantCulture);
        var block = int.Parse(Option("--block-index", "0"), CultureInfo.InvariantCulture);
        var heroes = Option("--heroes", "Mage,Priest,Guardian").Split(',').Select(Enum.Parse<HeroClass>).ToArray();
        var groups = Option("--groups", "O1,O6,E1,BOSS").Split(',');
        var alternatives = Option("--replacements", string.Join(',', Replacements)).Split(',');
        if (!Regex.IsMatch(sha, "^[0-9a-f]{40}$") || start < 1 || start > int.MaxValue - 1000 || samples is < 3 or > 1000 || block is < 0 or > 2 ||
            heroes.Length == 0 || heroes.Distinct().Count() != heroes.Length || heroes.Any(hero => !Enum.IsDefined(hero)) ||
            groups.Length == 0 || groups.Distinct().Count() != groups.Length || groups.Any(group => !Groups.Contains(group)) ||
            alternatives.Length == 0 || alternatives.Distinct().Count() != alternatives.Length || alternatives.Any(card => !Replacements.Contains(card)) || Directory.Exists(output))
            throw new ArgumentException("Exact source, bounded declared strata and new output required.");
        var config = GameConfigCatalog.Current;var catalog = CombatCardCatalog.CreatePrototype();
        var decks = heroes.ToDictionary(hero => hero, hero => Baseline(config, hero));
        foreach (var hero in heroes)
        foreach (var card in alternatives) PairedDeckBudget.Validate(config, hero, decks[hero], Swap(decks[hero], card));
        Directory.CreateDirectory(output);
        Write(Path.Combine(output, "manifest.json"), new { schema = "actual_element_marginals_v1", source_sha = sha, seed_start = start, samples, block_index = block,
            heroes = heroes.Select(h => h.ToString()), groups, alternatives, card_level = 0, weapon_level = 0, strategy = "basic", cutoff_seconds = 600,
            config_version = config.Version, baseline_card = "ET-FIRE-G", paired_budget_guard_passed = true, candidate_activation = false,
            primary_metrics = new[] { "Damage30", "ImmediateCardsDrawn", "ObservedAliveControlUnionTicks", "EffectiveHeal", "EffectiveShield", "HealOverflow", "ShieldOverflow" },
            draws_scope = "ImmediateCardsDrawn is actual on-play hand arrivals, including charge conversions; RequestedImmediateCards is the immediate request only. No inferred immediate-only overflow.",
            control_scope = "Observed live-target union clips each post-play target timer to the actual next 100ms observation tick; sums independent targets, not printed durations.",
            scope = "Actual encounter simulation with one same-quality Green replacement and fixed resource budget; not a full expedition, LIVE, human or capacity proof.",
            tune_table = config.Cards.Where(c => Replacements.Append("ET-FIRE-G").Contains(c.CardId)).Select(c => new { c.CardId, c.Quality, c.Rarity, c.UnlockCost, c.Effect }),
            baseline_decks = decks.Select(p => new { hero = p.Key.ToString(), cards = p.Value, budget = CombatExperience.Budget(config, p.Value) }) });
        var rawPath = Path.Combine(output, "encounters.jsonl.gz");long rawBytes = 0;var rows = 0;var errors = 0;
        using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        using (var file = new FileStream(rawPath, FileMode.CreateNew))
        using (var gzip = new GZipStream(file, CompressionLevel.Fastest))
        {
            foreach (var hero in heroes)
            foreach (var group in groups)
            foreach (var alternative in alternatives)
            for (var seed = start; seed < start + samples; seed++)
            foreach (var swapped in new[] { false, true })
            {
                var deck = swapped ? Swap(decks[hero], alternative) : decks[hero];
                var row = CombatExperience.Simulate(config, catalog, hero, alternative, deck, group, "basic", swapped ? "SingleGreenReplacement" : "BaselineGreenFire",
                    config.Numerics, seed, block, 600, 0, marginalAudit: true);
                if (row.Outcome == "Error") errors++;
                var text = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(row) + "\n");
                if (rawBytes + text.Length > 512L * 1024 * 1024) throw new InvalidOperationException("Raw evidence bound reached; original partial file retained.");
                gzip.Write(text);digest.AppendData(text);rawBytes += text.Length;rows++;
            }
        }
        var expected = heroes.Length * groups.Length * alternatives.Length * samples * 2;
        var summary = new { passed = errors == 0 && rows == expected, source_sha = sha, rows, errors, seed_start = start, samples, block_index = block,
            raw_bytes = rawBytes, raw_sha256 = Convert.ToHexString(digest.GetHashAndReset()).ToLowerInvariant(), stored_bytes = new FileInfo(rawPath).Length,
            stored_sha256 = HashFile(rawPath), candidate_activation = false };
        Write(Path.Combine(output, "summary.json"), summary);Console.WriteLine(JsonSerializer.Serialize(summary));return summary.passed ? 0 : 1;
    }

    internal static string[] Baseline(GameConfigCatalog config, HeroClass hero)
    {
        var deck = CombatExperience.CreateDecks(config, hero)["default"].Select(id => id == "C01" ? "ET-FIRE-G" : id).ToArray();
        CombatExperience.ValidateDeck(config, hero, deck);return deck;
    }
    internal static string[] Swap(string[] deck, string card) => deck.Select(id => id == "ET-FIRE-G" ? card : id).ToArray();
    private static string HashFile(string path) { using var stream = File.OpenRead(path);return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant(); }
    private static void Write(string path, object value) => File.WriteAllText(path, JsonSerializer.Serialize(value));
}
