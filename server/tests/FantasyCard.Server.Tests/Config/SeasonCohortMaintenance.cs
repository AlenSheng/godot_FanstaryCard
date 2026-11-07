using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Declared simulation policy; no grants, price changes, or implicit disposal.</summary>
internal static class SeasonCohortMaintenance
{
    internal const string Policy = "effect-aware-maintenance-v1";
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];
    internal sealed record Input(string Id, string Source, string Sha256);
    internal sealed record Disposal(SeasonCohortBank.Owned Before, SeasonCohortBank.Owned After);

    internal static Input[] Inputs()
    {
        using var json = JsonDocument.Parse(File.ReadAllText(Environment.GetEnvironmentVariable("FANTASYCARD_D03_MAINTENANCE_PLAN")
            ?? throw new InvalidOperationException("Frozen bank maintenance plan required.")));
        Assert.Equal(218, json.RootElement.GetProperty("prior_used").GetInt32());
        Assert.Equal(Policy, json.RootElement.GetProperty("policy").GetString());
        return json.RootElement.GetProperty("banks").EnumerateArray().Select(x => new Input(
            x.GetProperty("id").GetString()!, x.GetProperty("source").GetString()!, x.GetProperty("sha256").GetString()!)).ToArray();
    }

    internal static SeasonCohortBank Load(Input row)
    {
        var bytes = File.ReadAllBytes(row.Source);
        Assert.Equal(row.Sha256, Convert.ToHexStringLower(SHA256.HashData(bytes)));
        var bank = JsonSerializer.Deserialize<SeasonCohortBank>(bytes)!;
        Assert.Equal(row.Id, bank.Id);
        bank.Check();
        return bank;
    }

    internal static ExplorationItem[] Select(SeasonCohortBank bank, GameConfigCatalog config, int difficulty)
    {
        var cap = config.SeasonDifficulty(difficulty).EntryQualityCap;
        // Identical combat attributes are dominated by their highest real level; no invented upgrades.
        var groups = Slots.Select(slot => bank.Items.Where(x => x.Item.Equipment!.Slot == slot &&
                SeasonLootConfig.Rank(x.Item.Equipment.Quality) <= cap)
            .GroupBy(x => x.Item.Equipment! with { Level = 0 })
            .Select(g => g.OrderByDescending(x => x.Item.Equipment!.Level).ThenBy(x => x.Item.ItemId, StringComparer.Ordinal).First().Item)
            .OrderBy(x => x.ItemId, StringComparer.Ordinal).ToArray()).ToArray();
        ExplorationItem[] best = [];
        (int Slots, int QualitySet, int ProjectedEffects, int Exact, int ActiveEffects, double Damage, double Draw, int Rank, int Level) bestScore = default;
        var chosen = new List<ExplorationItem>();
        void Visit(int slot, bool high)
        {
            if (slot == Slots.Length)
            {
                var array = chosen.ToArray();
                var profile = Profile(array, config, false);
                var projected = Profile(array, config, true);
                var qualitySet = array.Length == 5 && array.All(x => SeasonLootConfig.Rank(x.Equipment!.Quality) >= 3) && array.Count(x => x.Equipment!.Quality == "Orange") == 1;
                var score = (array.Length, qualitySet ? 1 : 0, Effects(projected), array.Count(x => Exact(x.Equipment!)), Effects(profile),
                    profile.DamageBonus(CardElement.Water) + profile.DamageBonus(CardElement.Fire), -profile.DrawIntervalModifier,
                    array.Sum(x => SeasonLootConfig.Rank(x.Equipment!.Quality)), array.Sum(x => x.Equipment!.Level));
                if (best.Length == 0 || score.CompareTo(bestScore) > 0) { best = array; bestScore = score; }
                return;
            }
            if (groups[slot].Length == 0) { Visit(slot + 1, high); return; }
            var legal = false;
            foreach (var item in groups[slot])
            {
                var isHigh = item.Equipment!.Quality is "Orange" or "Red";
                if (high && isHigh) continue;
                legal = true; chosen.Add(item); Visit(slot + 1, high || isHigh); chosen.RemoveAt(chosen.Count - 1);
            }
            if (!legal) Visit(slot + 1, high);
        }
        Visit(0, false);
        return best;
    }

    internal static CombatEquipmentProfile Profile(IReadOnlyList<ExplorationItem> items, GameConfigCatalog config, bool projectThree) =>
        EquipmentCombatRules.Calculate(items.Select(x => new CombatEquipmentItem(Guid.Parse(x.ItemId), x.Equipment!.Slot,
            x.Equipment.Quality, projectThree ? Math.Max(3, x.Equipment.Level) : x.Equipment.Level,
            Enum.Parse<CardElement>(x.Equipment.Element), x.Equipment.EffectAffix, x.Equipment.SecondaryTrait,
            x.Equipment.UniqueAffix, x.Equipment.UniqueElement is null ? null : Enum.Parse<CardElement>(x.Equipment.UniqueElement))).ToArray(), config, "season-equipment-v1");

    internal static int Effects(CombatEquipmentProfile profile) => (profile.PiercingBonus > 0 ? 1 : 0) + (profile.VitalityOvercapBonus > 0 ? 1 : 0);
    internal static bool Exact(EquipmentRewardData item) => item.Quality == (item.Slot == "Head" ? "Orange" : "Purple") &&
        item.Element == (item.Slot is "Head" or "Chest" or "Hands" ? "Water" : "Fire") &&
        item.EffectAffix == (item.Slot is "Head" or "Chest" ? "Piercing" : "Vitality");

    /// <summary>Plan only. Preserve selected gear, unlearned unique samples and two real material bodies per quality.</summary>
    internal static SeasonCohortBank.Owned[] PlanDisposal(SeasonCohortBank bank, GameConfigCatalog config)
    {
        Assert.True(bank.StopReason is null or "warehouse_full");
        var all = bank.Items.Concat(bank.Overflow).ToArray();
        Assert.Equal(all.Length, all.Select(x => x.Item.ItemId).Distinct(StringComparer.Ordinal).Count());
        var selectionBank = new SeasonCohortBank { Items = all.ToList() };
        var protectedIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var group in all.Where(x => !x.Learned && (x.Source is "NaturalDrop" or "MarkCraft") && (x.Item.Equipment!.Quality is "Purple" or "Orange"))
            .GroupBy(x => (x.Item.Equipment!.Quality, x.Item.Equipment.Slot, x.Item.Equipment.Element, x.Item.Equipment.EffectAffix)))
        {
            var e = group.First().Item.Equipment!;
            if (!bank.Recipes.Any(r => r.Quality == e.Quality && r.Slot == e.Slot && r.Element == e.Element && r.Effect == e.EffectAffix))
                protectedIds.Add(group.OrderBy(x => x.Item.ItemId, StringComparer.Ordinal).First().Item.ItemId);
        }
        if (protectedIds.Count == all.Length) return [];
        foreach (var difficulty in new[] { 0, 1, 2 })
            protectedIds.UnionWith(Select(selectionBank, config, difficulty).Select(x => x.ItemId));
        foreach (var quality in all.GroupBy(x => x.Item.Equipment!.Quality))
            protectedIds.UnionWith(quality.Where(x => !protectedIds.Contains(x.Item.ItemId)).OrderByDescending(x => Exact(x.Item.Equipment!))
                .ThenByDescending(x => x.Item.Equipment!.Level).ThenBy(x => x.Item.ItemId, StringComparer.Ordinal).Take(2).Select(x => x.Item.ItemId));
        // Start maintenance at 40, target 35 to leave room for real reward/craft arrivals. No useful item is forced out.
        if (all.Length < 40 && bank.StopReason is null) return [];
        return all.Where(x => !protectedIds.Contains(x.Item.ItemId) && x.Item.IsGenerated != true && x.Source is not ("Borrowed" or "BotReward"))
            .OrderBy(x => SeasonLootConfig.Rank(x.Item.Equipment!.Quality)).ThenBy(x => x.Item.Equipment!.Level)
            .ThenBy(x => x.Item.ItemId, StringComparer.Ordinal).Take(Math.Max(0, all.Length - 35)).ToArray();
    }

    /// <summary>Explicit receipt-shaped model transition. The PG bridge separately proves these same IDs/versions through the real repository.</summary>
    internal static Disposal[] ApplyDisposal(SeasonCohortBank bank, IReadOnlyList<SeasonCohortBank.Owned> requested)
    {
        Assert.InRange(requested.Count, 1, 50);
        var all = bank.Items.Concat(bank.Overflow).ToList();
        var ids = requested.Select(x => x.Item.ItemId).ToHashSet(StringComparer.Ordinal);
        Assert.Equal(requested.Count, ids.Count);
        var moves = requested.Select(x =>
        {
            Assert.Equal(x, Assert.Single(all, a => a.Item.ItemId == x.Item.ItemId));
            Assert.False(x.Item.IsGenerated); Assert.True(x.Source is not ("Borrowed" or "BotReward"));
            return new Disposal(x, x with { Version = checked(x.Version + 1) });
        }).ToArray();
        all.RemoveAll(x => ids.Contains(x.Item.ItemId));
        bank.Recycled.AddRange(moves.Select(x => x.After));
        bank.Items = all.Take(50).ToList(); bank.Overflow = all.Skip(50).ToList();
        if (bank.StopReason == "warehouse_full" && all.Count < 50) bank.StopReason = null;
        bank.Check();
        return moves;
    }
}
