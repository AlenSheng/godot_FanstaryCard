using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

public sealed class SeasonCohortMaintenanceTests
{
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D03_MAINTENANCE") == "1";
    private static GameConfigCatalog Config => GameConfigCatalog.Current;
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];

    private static void Add(SeasonCohortBank bank, string slot, string quality, string element, string? effect, int level = 0)
    {
        var id = Guid.NewGuid().ToString("D");
        bank.SeenIds.Add(id);
        bank.Items.Add(new(new(id, ExplorationItemKind.Equipment, Equipment: new(slot, quality, element, effect, "DrawInterval", level,
            StatsVersion: "season-equipment-v1"), IsGenerated: false), "NaturalDrop"));
    }

    [Fact]
    public void SelectionPrefersTwoActivatableTargetEffectsBeforeSpendingOnUnrelatedLevels()
    {
        var bank = new SeasonCohortBank();
        foreach (var slot in Slots)
        {
            Add(bank, slot, slot == "Head" ? "Orange" : "Purple", "Metal", "Bulwark", 3);
            Add(bank, slot, slot == "Head" ? "Orange" : "Purple", slot is "Head" or "Chest" or "Hands" ? "Water" : "Fire",
                slot is "Head" or "Chest" ? "Piercing" : "Vitality");
        }
        var legacy = bank.Select(Config, 2);
        Assert.All(legacy, x => Assert.Equal("Bulwark", x.Equipment!.EffectAffix));
        var actualBefore = JsonSerializer.Serialize(bank.Items);
        bank.SelectionPolicy = SeasonCohortMaintenance.Policy;
        var selected = bank.Select(Config, 2);
        Assert.Equal(5, selected.Count(x => SeasonCohortMaintenance.Exact(x.Equipment!)));
        Assert.Equal(2, SeasonCohortMaintenance.Effects(SeasonCohortMaintenance.Profile(selected, Config, false)));
        Assert.All(selected, x => Assert.Equal(0, x.Equipment!.Level));
        Assert.Equal(actualBefore, JsonSerializer.Serialize(bank.Items));
        Assert.Equal(0, bank.FragmentsSpent);
    }

    [Fact]
    public void EffectAwareLobbyPaysActualSixtyFragmentsForFiveAlreadyCorrectBodies()
    {
        var bank = new SeasonCohortBank { Hero = "Mage", Cohort = "skilled", Fragments = 60, FragmentsEarned = 60, SelectionPolicy = SeasonCohortMaintenance.Policy };
        foreach (var slot in Slots)
            Add(bank, slot, slot == "Head" ? "Orange" : "Purple", slot is "Head" or "Chest" or "Hands" ? "Water" : "Fire", slot is "Head" or "Chest" ? "Piercing" : "Vitality");
        var ids = bank.Items.Select(x => x.Item.ItemId).Order().ToArray();
        using var trace = new StreamWriter(new MemoryStream());
        bank.Lobby(Config, trace);
        Assert.Equal(0, bank.Fragments); Assert.Equal(60, bank.FragmentsSpent);
        Assert.Equal(ids, bank.Items.Select(x => x.Item.ItemId).Order());
        Assert.All(bank.Items, x => Assert.Equal(3, x.Item.Equipment!.Level));
        Assert.Equal(1, bank.FirstReadyAttempt);
    }

    [Fact]
    public void DisposalPreservesBodiesAndVersionsWithoutRefundAndRejectsDuplicateAtomically()
    {
        var bank = new SeasonCohortBank { Gold = 100, GoldEarned = 100, Fragments = 70, FragmentsEarned = 70 };
        for (var i = 0; i < 50; i++) Add(bank, "Feet", "Blue", "Fire", null);
        bank.StopReason = "warehouse_full";
        var requested = SeasonCohortMaintenance.PlanDisposal(bank, Config);
        Assert.Equal(15, requested.Length);
        var before = JsonSerializer.Serialize(bank);
        Assert.ThrowsAny<Exception>(() => SeasonCohortMaintenance.ApplyDisposal(bank, [requested[0], requested[0]]));
        Assert.Equal(before, JsonSerializer.Serialize(bank));
        var moved = SeasonCohortMaintenance.ApplyDisposal(bank, requested);
        Assert.Equal(35, bank.Items.Count); Assert.Empty(bank.Overflow); Assert.Null(bank.StopReason);
        Assert.All(moved, x => { Assert.Equal(x.Before.Item, x.After.Item); Assert.Equal(x.Before.Version + 1, x.After.Version); });
        Assert.Equal(100, bank.Gold); Assert.Equal(70, bank.Fragments); Assert.Equal(0, bank.FragmentsSpent);
        bank.Check();
    }

    [Fact]
    public void UniqueUnlearnedSamplesAreProtectedAndCapacityIsNotForcedToPass()
    {
        var bank = new SeasonCohortBank();
        foreach (var slot in Slots)
        foreach (var element in new[] { "Water", "Fire", "Wood", "Earth", "Metal" })
        foreach (var effect in new[] { "Piercing", "Vitality", "Bulwark" })
            Add(bank, slot, "Purple", element, effect);
        bank.Overflow = bank.Items.Skip(50).ToList(); bank.Items = bank.Items.Take(50).ToList(); bank.StopReason = "warehouse_full";
        Assert.Empty(SeasonCohortMaintenance.PlanDisposal(bank, Config));
        Assert.Equal("warehouse_full", bank.StopReason); Assert.Equal(25, bank.Overflow.Count);
    }

    [Fact]
    public void SelectionHonorsEntryCapsOneHighQualityAndOriginalPhysicalIds()
    {
        var bank = new SeasonCohortBank { SelectionPolicy = SeasonCohortMaintenance.Policy };
        foreach (var slot in Slots)
        {
            Add(bank, slot, "Orange", "Water", "Piercing");
            Add(bank, slot, "Blue", "Fire", null);
        }
        for (var d = 0; d < 3; d++)
        {
            var selected = bank.Select(Config, d);
            Assert.All(selected, x => { Assert.Contains(x.ItemId, bank.SeenIds); Assert.True(SeasonLootConfig.Rank(x.Equipment!.Quality) <= Config.SeasonDifficulty(d).EntryQualityCap); });
            Assert.True(selected.Count(x => x.Equipment!.Quality is "Orange" or "Red") <= 1);
        }
    }

    [Fact(Skip = "Explicit original nine-bank maintenance audit; no match clock.", SkipUnless = nameof(Enabled))]
    public void OriginalBanksAreHashPinnedAndMaintenanceNeverGrantsIncomeOrLosesHistory()
    {
        var inputs = SeasonCohortMaintenance.Inputs(); Assert.Equal(9, inputs.Length);
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_D03_MAINTENANCE_OUTPUT") ?? throw new InvalidOperationException("Owned proof output required.");
        Assert.False(Directory.Exists(output)); Directory.CreateDirectory(output);
        var summaries = new List<object>();
        foreach (var row in inputs)
        {
            var bank = SeasonCohortMaintenance.Load(row);
            var before = JsonSerializer.Serialize(bank);
            var old = bank.Select(Config, 2);
            var requested = SeasonCohortMaintenance.PlanDisposal(bank, Config);
            var moves = requested.Length == 0 ? [] : SeasonCohortMaintenance.ApplyDisposal(bank, requested);
            bank.SelectionPolicy = SeasonCohortMaintenance.Policy;
            var selected = bank.Select(Config, 2);
            var initial = JsonSerializer.Deserialize<SeasonCohortBank>(before)!;
            Assert.Equal(initial.Attempts, bank.Attempts); Assert.Equal(initial.Deaths, bank.Deaths);
            Assert.Equal(initial.Gold, bank.Gold); Assert.Equal(initial.Fragments, bank.Fragments);
            Assert.Equal(initial.Blueprints, bank.Blueprints); Assert.Equal(initial.OrangeBlueprints, bank.OrangeBlueprints);
            Assert.Equal(initial.Recipes, bank.Recipes); Assert.Equal(initial.Wishes, bank.Wishes);
            Assert.Equal(initial.LostIds.Order(), bank.LostIds.Order());
            Assert.Equal(initial.Items.Concat(initial.Overflow).Select(x => x.Item.ItemId).Order(), bank.Items.Concat(bank.Overflow).Concat(moves.Select(x => x.After)).Select(x => x.Item.ItemId).Order());
            Assert.Equal(before, JsonSerializer.Serialize(SeasonCohortMaintenance.Load(row)));
            File.WriteAllText(Path.Combine(output, row.Id + ".model-preview.original.json"), JsonSerializer.Serialize(new { row, before = initial, requested, moves, after = bank, old, selected }));
            summaries.Add(new { bank.Id, bank.Attempts, original_censor = initial.StopReason, model_censor = bank.StopReason, discarded = moves.Length,
                remaining = bank.Items.Count, old_effects = SeasonCohortMaintenance.Effects(SeasonCohortMaintenance.Profile(old, Config, false)),
                selected_effects = SeasonCohortMaintenance.Effects(SeasonCohortMaintenance.Profile(selected, Config, false)),
                selected_exact = selected.Count(x => SeasonCohortMaintenance.Exact(x.Equipment!)) });
        }
        File.WriteAllText(Path.Combine(output, "summary.original.json"), JsonSerializer.Serialize(new { new_matches = 0, policy = SeasonCohortMaintenance.Policy, summaries }));
    }
}
