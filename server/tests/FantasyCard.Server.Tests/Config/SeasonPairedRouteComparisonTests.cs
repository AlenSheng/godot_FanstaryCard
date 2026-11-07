using System.Text.Json;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Prepared D2 paired full-route comparison. Input checks never authorize the additional encounter budget.</summary>
public sealed class SeasonPairedRouteComparisonTests
{
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_PAIRED_ROUTES") == "1";
    private static readonly MapPosition[] Route = [new(0, 0), new(0, 1), new(0, 2), new(0, 3), new(0, 4), new(1, 4), new(2, 4), new(2, 3)];
    private static readonly string[] Heroes = ["Mage", "Priest", "Guardian"];
    private static readonly JsonSerializerOptions EvidenceJson = new() { WriteIndented = true };

    [Fact(Skip = "Paired-route map/deck preflight only; no combat, clocks, admission or budget writes.", SkipUnless = nameof(Enabled))]
    public void PrepareLegalIndependentR1MapsAndMatchedMatureD2Inputs()
    {
        var config = GameConfigCatalog.Current;
        Assert.Equal("season-v1-config-17", config.Version);
        var maps = new List<object>();
        var seeds = new List<int>();
        for (var seed = 2000; seed < 4000 && seeds.Count < 3; seed++)
        {
            var map = ChaosMapGenerator.Generate(seed, 1, config.SeasonThemes);
            if (map.SpawnPositions[0] != Route[0] || map.BossPosition != Route[^1]) continue;
            Assert.All(Route.Zip(Route.Skip(1)), pair => Assert.True(map.CanMove(pair.First, pair.Second) && pair.First.ManhattanDistance(pair.Second) == 1));
            seeds.Add(seed);
            maps.Add(new { seed, snapshot = map.Capture(), path = Route, map_edited = false });
        }
        Assert.Equal(3, seeds.Count);
        foreach (var hero in Enum.GetValues<HeroClass>())
        {
            var deck = SeasonClassEfficiencyPilotTests.Deck(hero, "flow-offense");
            var available = config.Cards.Where(card => card.IsCodex).ToDictionary(card => card.CardId,
                card => new OwnedCard(card.CardId, card.HeroClass, (CardRarity)card.Rarity, 1, false));
            DeckRules.Validate(hero, deck, available);
            var armor = SeasonClassEfficiencyPilotTests.MatchedSustainArmor();
            SeasonLootRules.RequireEntry(new("d03-paired-routes", 2, "season-v1", config.Version, "season-equipment-v1"), armor.Select(item => item.Equipment!), config);
            Assert.All(armor, item => Assert.Equal(3, item.Equipment!.Level));
        }
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_D03_PAIRED_INPUTS") ?? throw new InvalidOperationException("New paired-route proof path required.");
        Assert.False(File.Exists(output));
        File.WriteAllText(output, JsonSerializer.Serialize(new { config.Version, config.ContentHash, prior_used = 308, maximum = 317,
            cases = seeds.SelectMany(seed => Heroes.Select(hero => new { id = $"D03-PAIRED-D2-{hero}-{seed}", hero, seed })), maps,
            difficulty = 2, deck = "flow-offense", armor = "counter-balanced", effective_card_weapon_level = 2, armor_level = 3,
            class_ratio_limit = 1.15, original_pacing_targets_not_changed = true, no_new_gameplay_starts = true,
            pve_only_domain_route_fixture = true, not_normal_multiplayer_capacity = true, red_quota_exhausted_fixture = true,
            execution_authorized_by_preflight = false }, EvidenceJson));
    }

    [Fact(Skip = "Requires explicit additional D03 paired-route authorization; never runs as an ordinary test.", SkipUnless = nameof(Enabled))]
    public void RunExplicitlyAuthorizedMatchedD2FullRoutes()
    {
        using var plan = JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_PAIRED_INPUTS") ?? throw new InvalidOperationException("Frozen paired-route inputs required.")));
        using var budget = JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_BUDGET_FILE") ?? throw new InvalidOperationException("Actual D03 budget required.")));
        var quota = budget.RootElement;
        if (quota.GetProperty("used").GetInt32() != 308 || quota.GetProperty("maximum").GetInt32() != 317
            || !quota.TryGetProperty("paired_routes_user_reply_received", out var approved) || approved.ValueKind != JsonValueKind.True
            || !quota.TryGetProperty("paired_routes_authorization_reference", out var reference) || string.IsNullOrWhiteSpace(reference.GetString()))
            throw new InvalidOperationException("Paired full-route execution requires a separate explicit D03317 budget authorization.");
        Assert.Equal(GameConfigCatalog.Current.Version, plan.RootElement.GetProperty("Version").GetString());
        Assert.Equal(GameConfigCatalog.Current.ContentHash, plan.RootElement.GetProperty("ContentHash").GetString());
        Assert.Equal(308, plan.RootElement.GetProperty("prior_used").GetInt32());
        Assert.Equal(317, plan.RootElement.GetProperty("maximum").GetInt32());
        var cases = plan.RootElement.GetProperty("cases").EnumerateArray().ToArray();
        Assert.Equal(9, cases.Length);
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_D03_PAIRED_OUTPUT") ?? throw new InvalidOperationException("Owned paired-route output required.");
        Assert.False(Directory.Exists(output));
        Directory.CreateDirectory(output);
        using var attempts = new StreamWriter(Path.Combine(output, "attempts.original.jsonl"));
        using var trace = new StreamWriter(Path.Combine(output, "events.original.jsonl"));
        using var results = new StreamWriter(Path.Combine(output, "routes.original.jsonl"));
        foreach (var row in cases)
        {
            attempts.WriteLine(row.GetRawText());
            attempts.Flush();
            ((FileStream)attempts.BaseStream).Flush(flushToDisk: true);
            var scenario = new SeasonCohortRouteTests.Scenario(row.GetProperty("id").GetString()!, row.GetProperty("hero").GetString()!,
                "skilled", row.GetProperty("seed").GetInt32(), Difficulty: 2, Route: "R1", Loadout: "flow-offense");
            SeasonCohortRouteTests.Run(scenario, trace, results, SeasonClassEfficiencyPilotTests.MatchedSustainArmor());
            trace.Flush();
            results.Flush();
        }
    }
}
