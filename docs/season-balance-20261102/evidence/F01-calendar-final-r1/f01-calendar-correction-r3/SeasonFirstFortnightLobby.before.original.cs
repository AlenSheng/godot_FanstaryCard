using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Config;

/// <summary>F01 lobby decisions call real account repositories; no model balance or body is assigned.</summary>
internal sealed class SeasonFirstFortnightLobby(NpgsqlDataSource source, SeasonFirstFortnightTimeProvider clock,
    SeasonDefinition season, StreamWriter trace)
{
    private static readonly string[] Slots = ["Head", "Chest", "Hands", "Legs", "Feet"];
    private readonly PublishedConfigCatalogs _catalogs = new(GameConfigCatalog.Current);

    internal sealed record PreparedDecision(CreatePreparationRequest Request, int Difficulty, object Checkpoint);

    internal async Task<PreparedDecision> RunAsync(Guid player, SeasonFirstFortnightInputsTests.Actor actor,
        string caseId, int consecutiveDeaths, CancellationToken ct)
    {
        var config = GameConfigCatalog.Current;
        var progression = new ProgressionRepository(source, clock, _catalogs);
        var seasons = new SeasonRepository(source, clock);
        await seasons.EnsurePlayerAsync(player, season.ContextFor(0), ct);
        string Key(string targetAndVersion) => caseId + "-lobby-" + targetAndVersion;
        void Log(string kind, object value)
        {
            trace.WriteLine(JsonSerializer.Serialize(new { kind, caseId, player, now = clock.GetUtcNow(), value }));
            trace.Flush();
        }
        var journey = new SeasonJourneyRepository(source, clock, _catalogs);
        var rewards = await journey.GetRewardsAsync(player, season.SeasonId, ct);
        foreach (var reward in rewards.Rewards.Where(value => value.CanClaim && value.RewardId is not null))
        {
            var receipt = await journey.ClaimRewardAsync(player, reward.RewardId!.Value, Key("journey-" + reward.Level),
                new(season.SeasonId, reward.RequiresClassChoice ? actor.Hero.ToString() : null), ct);
            Log("journey-claimed", receipt);
        }
        var activity = new SeasonActivityRepository(source, clock, _catalogs);
        foreach (var entry in (await activity.GetAsync(player, ct, season.SeasonId)).Events.Where(value => value.CanExchange))
        {
            var current = entry;
            for (var exchange = 0; exchange < 5; exchange++)
            {
                var potion = current.Options.Single(value => value.RuleId == "event-potion");
                var fragments = current.Options.Single(value => value.RuleId == "event-fragments");
                var chosen = actor.Cohort == "novice" && potion.Used == 0 && current.Available >= potion.CostTokens
                    ? potion : fragments;
                if (current.Available < chosen.CostTokens || chosen.Used >= chosen.EventLimit) break;
                var offered = await activity.ExchangeAsync(player, current.EventId, Key("event-" + current.EventId + "-" + chosen.RuleId + "-v" + current.AccountVersion),
                    new(season.SeasonId, chosen.RuleId, current.AccountVersion), ct);
                Log("activity-exchanged", offered);
                Log("activity-claimed", await activity.ClaimAsync(player, offered.Reward.RewardId, Key("event-claim-" + offered.Reward.RewardId.ToString("N")), ct));
                current = (await activity.GetAsync(player, ct, season.SeasonId)).Events.Single(value => value.EventId == entry.EventId);
            }
        }
        var inventory = await progression.GetInventoryAsync(player, ct);
        var crafting = await progression.GetSeasonCraftingAsync(player, ct);
        foreach (var item in Available(inventory).Where(value => value.Quality is "Purple" or "Orange"
                     && value.RecipeExtracted != true && value.SourceKind is "NaturalDrop" or "MarkCraft"))
        {
            if (crafting.Recipes.Any(recipe => recipe.Quality == item.Quality && recipe.Slot == item.Slot
                && recipe.Element == item.Element && recipe.EffectAffix == item.EffectAffix)) continue;
            Log("recipe-learned", await progression.LearnSeasonRecipeAsync(player, Key("learn-" + item.InstanceId.ToString("N") + "-v" + item.Version),
                new(season.SeasonId, item.InstanceId, item.Version), ct));
            crafting = await progression.GetSeasonCraftingAsync(player, ct);
        }
        for (var index = 0; index < Slots.Length; index++)
        {
            inventory = await progression.GetInventoryAsync(player, ct);
            crafting = await progression.GetSeasonCraftingAsync(player, ct);
            var slot = Slots[index];
            var quality = slot == "Head" ? "Orange" : "Purple";
            var element = index < 3 ? "Water" : "Fire";
            var effect = index < 2 ? "Piercing" : "Vitality";
            if (Available(inventory).Any(item => item.Quality == quality && item.Slot == slot && item.Element == element && item.EffectAffix == effect)) continue;
            var recipe = crafting.Recipes.FirstOrDefault(value => value.Quality == quality && value.Slot == slot && value.Element == element && value.EffectAffix == effect);
            var body = Available(inventory).Where(item => item.Location == "Inventory" && item.Quality == quality)
                .OrderBy(item => item.Level).ThenBy(item => item.InstanceId).FirstOrDefault();
            if (recipe is not null && body is not null)
            {
                var quote = await progression.GetReforgeQuoteAsync(player, season.SeasonId, recipe.RecipeId, body.InstanceId, ct);
                if (quote.CanReforge)
                {
                    Log("reforged", await progression.ReforgeSeasonEquipmentAsync(player, Key("reforge-" + body.InstanceId.ToString("N") + "-v" + body.Version),
                        new(season.SeasonId, recipe.RecipeId, body.InstanceId, body.Version, quote.ExpectedWalletVersion), ct));
                    continue;
                }
            }
            var offer = crafting.Offers.Single(value => value.Quality == quality);
            var wallet = crafting.Wallet;
            if (wallet is null || crafting.MaximumDifficulty < offer.MinimumDifficulty) continue;
            var paymentAvailable = quality == "Orange" ? wallet.OrangeBlueprintMarks
                : wallet.BlueprintMarks + (Available(inventory).Any(item => item.Quality == "Orange") ? wallet.OrangeBlueprintMarks : 0);
            if (paymentAvailable >= offer.MarkCost)
                Log("crafted", await progression.CraftSeasonEquipmentAsync(player, Key("craft-" + quality + "-" + slot + "-v" + wallet.Version),
                    new(season.SeasonId, quality, slot, element, effect, wallet.Version), ct));
        }
        var unlocked = await seasons.GetUnlockedDifficultyAsync(player, season.SeasonId, ct);
        var targetPermanentLevel = Math.Min(5, unlocked + 1);
        if (actor.Cohort == "novice")
        {
            foreach (var cardId in actor.Cards)
            {
                var card = (await progression.GetCardsAsync(player, ct)).Single(value => value.CardId == cardId);
                long availableSoul;
                await using (var balanceQuery = source.CreateCommand("SELECT warrior_soul,priest_soul,mage_soul,guardian_soul FROM player_materials WHERE player_id=$1"))
                {
                    balanceQuery.Parameters.AddWithValue(player);
                    await using var balances = await balanceQuery.ExecuteReaderAsync(ct);
                    if (!await balances.ReadAsync(ct)) throw new InvalidOperationException("F01 actual materials are missing.");
                    var column = card.CurrencyKind switch { "WarriorSoul" => 0, "PriestSoul" => 1, "MageSoul" => 2, "GuardianSoul" => 3,
                        _ => throw new InvalidOperationException("Unknown actual upgrade currency: " + card.CurrencyKind) };
                    availableSoul = balances.GetInt64(column);
                }
                if (card.Level < targetPermanentLevel && card.CanUpgrade && availableSoul >= card.UpgradeCost)
                    Log("card-upgraded", await progression.UpgradeCardAsync(player, cardId, Key("card-" + cardId + "-v" + card.Version), new(card.Version), ct));
            }
            var weapon = await progression.GetWeaponEnhancementQuoteAsync(player, actor.Hero, season.ContextFor(0), ct);
            if (weapon is { CanEnhance: true } && weapon.CurrentLevel < targetPermanentLevel)
                Log("weapon-upgraded", await progression.EnhanceWeaponAsync(player, actor.Hero, Key("weapon-" + actor.Hero + "-v" + weapon.ExpectedVersion), weapon.ExpectedVersion, season.ContextFor(0), ct));
        }
        using (var economy = new EconomyRepository(source, clock, _catalogs))
        {
            foreach (var kind in new[] { "equipment_fragments", "health_potion", "warrior_soul", actor.Hero.ToString().ToLowerInvariant() + "_soul" })
            {
                var shop = await economy.GetShopAsync(player, ct);
                var product = shop.Products.FirstOrDefault(value => value.ProductId == kind);
                if (product is null || product.Purchased > 0 || product.Limit <= product.Purchased || shop.Policy?.CanPurchase != true) continue;
                var balance = shop.Policy.Wallet.Gold;
                var wallet = await seasons.GetWalletAsync(player, season.ContextFor(0), ct);
                inventory = await progression.GetInventoryAsync(player, ct);
                var shouldBuy = kind == "equipment_fragments" ? wallet!.EquipmentFragments < 20 && balance >= product.PriceGold
                    : kind == "health_potion" ? inventory.Consumables.HealthPotionCount == 0 && balance >= product.PriceGold + 120
                    : actor.Cohort == "novice" && balance >= product.PriceGold + 120
                      && (await progression.GetCardsAsync(player, ct)).Any(card => actor.Cards.Contains(card.CardId, StringComparer.Ordinal)
                           && card.Level < targetPermanentLevel && !card.CanUpgrade && card.UpgradeCopyCost <= card.CopyCount
                           && card.CurrencyKind == (kind == "warrior_soul" ? "WarriorSoul" : actor.Hero + "Soul"));
                if (!shouldBuy) continue;
                Log("shop-purchased", await economy.PurchaseAsync(player, Key("shop-" + product.ProductId + "-" + shop.ResetKey + "-p" + product.Purchased), new(product.ProductId, 1, season.SeasonId,
                    shop.ResetKey, shop.RotationKey, product.PriceGold, shop.Policy.CatalogVersion), ct));
            }
        }
        inventory = await progression.GetInventoryAsync(player, ct);
        var maximum = Math.Min(unlocked, season.HighestOpenDifficulty);
        var riskMaximum = consecutiveDeaths >= 2 ? Math.Max(0, maximum - 1) : maximum;
        var difficulty = 0;
        var selected = Select(inventory, config, 0);
        for (var tier = riskMaximum; tier >= 1; tier--)
        {
            var candidate = Select(inventory, config, tier);
            var blue = candidate.Count(item => SeasonLootConfig.Rank(item.Equipment!.Quality) >= 2);
            var purple = candidate.Count(item => SeasonLootConfig.Rank(item.Equipment!.Quality) >= 3);
            var profile = SeasonCohortMaintenance.Profile(candidate, config, projectThree: false);
            var active = profile.PiercingBonus > 0 || profile.VitalityOvercapBonus > 0 || profile.BulwarkDamageReduction > 0 || profile.BulwarkShieldBonus > 0;
            var mature = candidate.Length == 5 && purple == 5 && candidate.Count(item => item.Equipment!.Quality == "Orange") == 1
                && candidate.All(item => item.Equipment!.Level >= 3) && active;
            if (tier == 1 && blue >= 3 || tier == 2 && candidate.Length == 5 && blue == 5 && purple >= 3 && active || tier >= 3 && mature)
            { difficulty = tier; selected = candidate; break; }
        }
        var qualitySet = selected.Length == 5 && selected.All(item => SeasonLootConfig.Rank(item.Equipment!.Quality) >= 3)
            && selected.Count(item => item.Equipment!.Quality == "Orange") == 1;
        foreach (var item in selected)
        {
            var limit = qualitySet ? 3 : SeasonLootConfig.Rank(item.Equipment!.Quality) >= 1 ? 1 : 0;
            for (var level = item.Equipment!.Level; level < limit; level++)
            {
                var quote = await progression.GetEquipmentEnhancementQuoteAsync(player, Guid.Parse(item.ItemId), ct);
                if (quote is not { CanEnhance: true }) break;
                Log("armor-enhanced", await progression.EnhanceEquipmentAsync(player, Guid.Parse(item.ItemId), Key("armor-" + item.ItemId + "-v" + quote.ExpectedVersion),
                    new(quote.ExpectedVersion), ct));
            }
        }
        var ids = Slots.Select(slot => selected.FirstOrDefault(item => item.Equipment!.Slot == slot)?.ItemId)
            .Select(id => id is null ? (Guid?)null : Guid.Parse(id)).ToArray();
        var loadout = await progression.GetLoadoutAsync(player, actor.Hero, ct) ?? throw new InvalidOperationException("F01 actual loadout missing.");
        if (!loadout.EquipmentIds.SequenceEqual(ids))
        {
            var saved = await progression.SaveLoadoutAsync(player, actor.Hero, ids, Key("equip-v" + loadout.Version), loadout.Version, clock.GetUtcNow(), ct);
            if (saved.Status != SaveLoadoutStatus.Updated) throw new InvalidOperationException("F01 actual equip failed: " + saved.Status);
            Log("loadout-saved", saved);
        }
        var deck = (await progression.GetDecksAsync(player, ct)).Single(value => value.HeroClass == (HeroClassDto)(int)actor.Hero);
        inventory = await progression.GetInventoryAsync(player, ct);
        var request = new CreatePreparationRequest((HeroClassDto)(int)actor.Hero, deck.Version, ids, BackpackTierDto.Free,
            Array.Empty<int>(), inventory.Consumables.HealthPotionCount > 0 ? 1 : 0, "D" + difficulty, season.SeasonId);
        var checkpoint = new { request, wallet = await seasons.GetWalletAsync(player, season.ContextFor(0), ct),
            inventory, cards = await progression.GetCardsAsync(player, ct), unlocked, consecutiveDeaths, selection_candidate_bound_per_slot = 4 };
        return new(request, difficulty, checkpoint);
    }

    private static IEnumerable<EquipmentResponse> Available(InventoryResponse inventory) => inventory.Equipments
        .Where(item => (item.Location is "Inventory" or "Equipped") && item.AssetScope == "ActiveSeason");

    private static ExplorationItem[] Select(InventoryResponse inventory, GameConfigCatalog config, int difficulty)
    {
        var entryCap = config.SeasonDifficulty(difficulty).EntryQualityCap;
        var candidates = Available(inventory).Where(item => SeasonLootConfig.Rank(item.Quality) <= entryCap)
            .GroupBy(item => item.Slot).SelectMany(group => group
            .OrderByDescending(item => item.Element is "Water" or "Fire")
            .ThenByDescending(item => item.EffectAffix is "Piercing" or "Vitality")
            .ThenByDescending(item => SeasonLootConfig.Rank(item.Quality)).ThenByDescending(item => item.Level)
            .ThenBy(item => item.InstanceId).Take(4)).ToArray();
        var bank = new SeasonCohortBank { SelectionPolicy = SeasonCohortMaintenance.Policy };
        foreach (var item in candidates)
            bank.Items.Add(new(new(item.InstanceId.ToString("D"), ExplorationItemKind.Equipment, Equipment: new(
                item.Slot, item.Quality, item.Element ?? throw new InvalidOperationException("Current F01 owned armor has no original element."), item.EffectAffix, item.SecondaryTrait, item.Level,
                UniqueAffix: item.UniqueAffix, UniqueElement: item.UniqueElement, StatsVersion: item.StatsVersion), IsGenerated: false),
                item.SourceKind ?? throw new InvalidOperationException("Current F01 owned armor has no original source kind."), Version: checked((int)item.Version)));
        return SeasonCohortMaintenance.Select(bank, config, difficulty);
    }
}
