using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresAssetDomainCompositeTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private const string Required = "Requires isolated PostgreSQL.";
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    private static async Task<JourneyPlayer> EarnAndClaim(PostgresTestSchema db)
    {
        var p = await JourneyTestInputs.Create(db);
        // The declared earned aggregate isolates persistence/asset domains.
        // This is not a completed level-30 combat route or human session.
        await PostgresJourneyRewardEntitlementTests.SeedExperience(db, p, p.Config.SeasonJourney!.Threshold(30, 42));
        await PostgresJourneyRewardEntitlementTests.Unlock(db, p, _ => 0);
        foreach (var reward in (await p.Journey.GetRewardsAsync(p.Player, p.Season.SeasonId, Ct)).Rewards)
            await p.Journey.ClaimRewardAsync(p.Player, reward.RewardId!.Value, "claim-" + reward.Level,
                new(p.Season.SeasonId, reward.RequiresClassChoice ? "Mage" : null), Ct);
        return p;
    }

    private static async Task<SeasonDefinition> StartNext(PostgresTestSchema db, JourneyPlayer p)
    {
        var next = SeasonDefinition.FromCalendarDays("composite-next", DateOnly.FromDateTime(p.Season.EndsAtUtc.AddHours(8).DateTime),
            p.Config.Version, p.Season.StatsVersion, highestOpenDifficulty: 5);
        await p.Seasons.PublishAsync(next, p.Config.ContentHash, Ct);p.Clock.Now = next.StartsAtUtc;
        await p.Seasons.EnsurePlayerAsync(p.Player, next.ContextFor(0), Ct);
        return next;
    }

    private static CraftingPlayer Crafting(PostgresTestSchema db, JourneyPlayer p, SeasonDefinition season) =>
        new(p.Player, season, p.Clock, p.Seasons, new ProgressionRepository(db.DataSource, p.Clock));

    private static Task<string> Permanent(PostgresTestSchema db, Guid player) => db.ScalarAsync<string>("""
        SELECT jsonb_build_object(
          'wallet',(SELECT to_jsonb(w) FROM player_wallets w WHERE player_id=$1),
          'materials',(SELECT to_jsonb(m) FROM player_materials m WHERE player_id=$1),
          'consumables',(SELECT to_jsonb(c) FROM player_consumables c WHERE player_id=$1),
          'cards',(SELECT jsonb_agg(to_jsonb(c) ORDER BY card_id) FROM player_cards c WHERE player_id=$1),
          'reserves',(SELECT jsonb_agg(to_jsonb(r) ORDER BY card_id) FROM player_card_reserves r WHERE player_id=$1),
          'copyMode',(SELECT to_jsonb(m) FROM player_card_copy_modes m WHERE player_id=$1),
          'weapons',(SELECT jsonb_agg(to_jsonb(w) ORDER BY hero_class) FROM class_weapons w WHERE player_id=$1),
          'decks',(SELECT jsonb_agg(to_jsonb(d) ORDER BY hero_class) FROM player_decks d WHERE player_id=$1),
          'deckCards',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.deck_id,c.slot_index)
              FROM player_deck_cards c JOIN player_decks d USING(deck_id) WHERE d.player_id=$1),
          'cosmetics',(SELECT jsonb_agg(to_jsonb(c) ORDER BY cosmetic_id) FROM player_cosmetics c WHERE player_id=$1),
          'selection',(SELECT to_jsonb(p) FROM player_cosmetic_profiles p WHERE player_id=$1))::text
        """, player);

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task ActualArchivePagesPreserveClaimedCopiesCosmeticSelectionAndAllPermanentFamilies()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var p = await EarnAndClaim(db);
        var oldItem = await CraftingTestInputs.ItemAsync(db, Crafting(db, p, p.Season), level: 3);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_consumables SET health_potion_count=2,advanced_bag_count=1,top_bag_count=1 WHERE player_id=$1", p.Player);
        await CraftingTestInputs.SqlAsync(db, "UPDATE class_weapons SET level=3 WHERE player_id=$1 AND hero_class=2", p.Player);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_wallets SET diamond=777 WHERE player_id=$1", p.Player);
        var owned = await p.Journey.GetCosmeticsAsync(p.Player, Ct);
        var selected = await p.Journey.SelectCosmeticAsync(p.Player, "frame", new("AvatarFrame", "trail-seeker", owned.Selection.Version), Ct);
        selected = await p.Journey.SelectCosmeticAsync(p.Player, "back", new("CardBack", "waymark-seal", selected.Version), Ct);
        await p.Journey.SelectCosmeticAsync(p.Player, "title", new("Title", "relic-seeker", selected.Version), Ct);
        var snapshot = await Permanent(db, p.Player);
        var next = await StartNext(db, p);var newItem = await CraftingTestInputs.ItemAsync(db, Crafting(db, p, next), slot: "Head");
        var page = await p.Seasons.AdvanceArchivePageAsync(p.Player, p.Season.SeasonId, 1, Ct);
        Assert.Equal("Completed", page.Status);Assert.Equal(1, page.ArchivedItems);
        Assert.Equal(snapshot, await Permanent(db, p.Player));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='SeasonArchive' AND asset_scope='ArchivedSeason' AND level=3", oldItem));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='Inventory' AND asset_scope='ActiveSeason'", newItem));
        Assert.Equal(0, (await p.Seasons.GetWalletAsync(p.Player, next.ContextFor(0), Ct))!.EquipmentFragments);
        var cosmetics = await new SeasonJourneyRepository(db.DataSource, p.Clock, p.Configurations).GetCosmeticsAsync(p.Player, Ct);
        Assert.Equal(10, cosmetics.Owned.Count);Assert.Equal("trail-seeker", cosmetics.Selection.AvatarFrameId);
        Assert.Equal("waymark-seal", cosmetics.Selection.CardBackId);Assert.Equal("relic-seeker", cosmetics.Selection.TitleId);
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task ArchivedFragmentsCanFundPermanentWeaponButNeitherOldNorLegacyFragmentsFundNewArmor()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var p = await EarnAndClaim(db);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_materials SET equipment_fragments=1000 WHERE player_id=$1", p.Player);
        var next = await StartNext(db, p);
        await p.Seasons.AdvanceArchivePageAsync(p.Player, p.Season.SeasonId, 10, Ct);
        var item = await CraftingTestInputs.ItemAsync(db, Crafting(db, p, next), "White", effect: null);
        var progression = new ProgressionRepository(db.DataSource, p.Clock);
        await Assert.ThrowsAsync<DomainValidationException>(() => progression.EnhanceEquipmentAsync(p.Player, item, "no-cross-domain", new EnhanceEquipmentRequest(1), Ct));
        Assert.Equal(80, (await p.Seasons.GetWalletAsync(p.Player, p.Season.ContextFor(0), Ct))!.EquipmentFragments);
        Assert.Equal(1000, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", p.Player));
        Assert.Equal(0, (await p.Seasons.GetWalletAsync(p.Player, next.ContextFor(0), Ct))!.EquipmentFragments);
        var version = await db.ScalarAsync<long>("SELECT version FROM class_weapons WHERE player_id=$1 AND hero_class=2", p.Player);
        var weapon = await progression.EnhanceWeaponAsync(p.Player, HeroClass.Mage, "old-source-permanent", version, p.Season.ContextFor(0), Ct);
        Assert.Equal(1, weapon.Equipment.Level);Assert.Equal(72, weapon.EquipmentFragments);
        Assert.Equal(0, (await p.Seasons.GetWalletAsync(p.Player, next.ContextFor(0), Ct))!.EquipmentFragments);
        Assert.Equal(1000, await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", p.Player));
        Assert.Equal(JsonSerializer.Serialize(weapon), JsonSerializer.Serialize(await progression.EnhanceWeaponAsync(p.Player, HeroClass.Mage, "old-source-permanent", version, p.Season.ContextFor(0), Ct)));
    }
}
