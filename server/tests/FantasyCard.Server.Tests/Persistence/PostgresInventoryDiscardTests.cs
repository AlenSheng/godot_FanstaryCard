using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresInventoryDiscardTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private const string Required = "Requires isolated PostgreSQL.";
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static DiscardEquipmentRequest Request(CraftingPlayer f, params Guid[] ids) =>
        new(ids.Select(id => new DiscardEquipmentItemRequest(id, 1)).ToArray(), f.Season.SeasonId);

    private static async Task<PostgresTestSchema> OpenAsync()
    {
        var db = await PostgresTestSchema.CreateAsync(false);
        try
        {
            var output = Environment.GetEnvironmentVariable("FANTASYCARD_DISCARD_SCHEMA_EVIDENCE");
            if (output is not null)
                File.AppendAllText(output, JsonSerializer.Serialize(new
                {
                    kind = "inventory-discard-schema", schema = new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath,
                    created_at_utc = DateTimeOffset.UtcNow
                }) + Environment.NewLine);
            await db.MigrateAsync();
            return db;
        }
        catch { await db.DisposeAsync(); throw; }
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task BatchRetainsPhysicalHistoryAndRecipesWithoutAnyResourceRefundAndReplaysAfterSeasonEnd()
    {
        await using var db = await OpenAsync(); var f = await CraftingTestInputs.CreateAsync(db);
        var a = await CraftingTestInputs.ItemAsync(db, f, bound: true, level: 3);
        var b = await CraftingTestInputs.ItemAsync(db, f, "Orange", "Head");
        await f.Progression.LearnSeasonRecipeAsync(f.Player, "learn-before-discard", new(f.Season.SeasonId, a, 1), Ct);
        var request = new DiscardEquipmentRequest([new(a, 2), new(b, 1)], f.Season.SeasonId);
        var wallet = await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_season_wallets w WHERE player_id=$1", f.Player);
        var original = await db.ScalarAsync<string>("SELECT jsonb_agg(to_jsonb(e)-'location'-'version' ORDER BY instance_id)::text FROM equipments e WHERE owner_id=$1", f.Player);
        var result = await f.Progression.DiscardEquipmentAsync(f.Player, "discard-batch", request, Ct);
        Assert.Equal(2, result.Items.Count); Assert.All(result.Items, x => Assert.Equal("Recycled", x.Location));
        Assert.Equal(3, result.Items.Single(x => x.InstanceId == a).Version); Assert.Equal(2, result.Items.Single(x => x.InstanceId == b).Version);
        Assert.Equal(original, await db.ScalarAsync<string>("SELECT jsonb_agg(to_jsonb(e)-'location'-'version' ORDER BY instance_id)::text FROM equipments e WHERE owner_id=$1", f.Player));
        Assert.Equal(wallet, await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_season_wallets w WHERE player_id=$1", f.Player));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM learned_season_recipes WHERE source_item_id=$1", a));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='equipment.discard' AND from_location='Inventory' AND to_location='Recycled' AND season_id=$2 AND config_version=$3", f.Player, f.Season.SeasonId, f.Season.ConfigVersion));
        Assert.Empty((await f.Progression.GetInventoryAsync(f.Player, Ct)).Equipments);
        f.Clock.Now = f.Season.EndsAtUtc;
        var restarted = new ProgressionRepository(db.DataSource, f.Clock);
        var replay = await restarted.DiscardEquipmentAsync(f.Player, "discard-batch", request with { Items = request.Items!.Reverse().ToArray() }, Ct);
        Assert.Equivalent(result, replay, strict: true);
        await Assert.ThrowsAsync<DomainValidationException>(() => restarted.DiscardEquipmentAsync(f.Player, "after-end", request, Ct));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => restarted.DiscardEquipmentAsync(f.Player, "discard-batch", Request(f, b), Ct));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='equipment.discard'"));
    }

    [Theory(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    [InlineData("Equipped")][InlineData("PreparationLocked")][InlineData("MarketListed")][InlineData("InMatchBackpack")][InlineData("Recycled")]
    public async Task OneUnavailableItemRejectsTheEntireBatch(string location)
    {
        await using var db = await OpenAsync(); var f = await CraftingTestInputs.CreateAsync(db);
        var a = await CraftingTestInputs.ItemAsync(db, f); var b = await CraftingTestInputs.ItemAsync(db, f);
        await CraftingTestInputs.SqlAsync(db, "UPDATE equipments SET location=$2 WHERE instance_id=$1", b, location);
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "reject", Request(f, a, b), Ct));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", a));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1", a));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.discard'"));
    }

    [Theory(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    [InlineData("stale")][InlineData("owner")][InlineData("legacy")][InlineData("Borrowed")][InlineData("BotReward")]
    public async Task ChangedVersionForeignOwnerOrDifferentAssetDomainNeverDiscardsOtherItems(string change)
    {
        await using var db = await OpenAsync(); var f = await CraftingTestInputs.CreateAsync(db);
        var a = await CraftingTestInputs.ItemAsync(db, f); var b = await CraftingTestInputs.ItemAsync(db, f);
        if (change == "stale") await CraftingTestInputs.SqlAsync(db, "UPDATE equipments SET version=2 WHERE instance_id=$1", b);
        else if (change == "owner")
        {
            var other = await CraftingTestInputs.PlayerAsync(db, f.Clock); await f.Seasons.EnsurePlayerAsync(other, f.Season.ContextFor(0), Ct);
            await CraftingTestInputs.SqlAsync(db, "UPDATE equipments SET owner_id=$2 WHERE instance_id=$1", b, other);
        }
        else if (change == "legacy") await CraftingTestInputs.SqlAsync(db, "UPDATE equipments SET origin_season_id=NULL,season_id=NULL,asset_scope=NULL,stats_version=NULL WHERE instance_id=$1", b);
        else await CraftingTestInputs.SqlAsync(db, "UPDATE equipments SET source_kind=$2 WHERE instance_id=$1", b, change);
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "reject-domain", Request(f, a, b), Ct));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=ANY($1) AND location='Inventory'", new[] { a, b }));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task SavedLoadoutInAnotherClassIsProtectedAndExplicitSeasonIdentityIsRequired()
    {
        await using var db = await OpenAsync(); var f = await CraftingTestInputs.CreateAsync(db);
        var item = await CraftingTestInputs.ItemAsync(db, f);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_loadouts SET chest_id=$2 WHERE player_id=$1 AND hero_class=1", f.Player, item);
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "loadout", Request(f, item), Ct));
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_loadouts SET chest_id=NULL WHERE player_id=$1", f.Player);
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "missing-season", Request(f, item) with { SeasonId = null }, Ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "wrong-season", Request(f, item) with { SeasonId = "another-season" }, Ct));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", item));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task SecondMovementFailureRollsBackEveryItemAndReceiptThenSameRequestRetries()
    {
        await using var db = await OpenAsync(); var f = await CraftingTestInputs.CreateAsync(db);
        var a = await CraftingTestInputs.ItemAsync(db, f); var b = await CraftingTestInputs.ItemAsync(db, f);
        await CraftingTestInputs.SqlAsync(db, """
            CREATE FUNCTION fail_second_discard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
              IF NEW.reason='equipment.discard' AND EXISTS(SELECT 1 FROM inventory_movements WHERE reason='equipment.discard')
              THEN RAISE EXCEPTION 'declared second discard movement failure'; END IF; RETURN NEW; END; $$;
            CREATE TRIGGER fail_second_discard BEFORE INSERT ON inventory_movements FOR EACH ROW EXECUTE FUNCTION fail_second_discard();
            """);
        await Assert.ThrowsAsync<PostgresException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "rollback", Request(f, a, b), Ct));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location='Inventory' AND version=1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.discard'"));
        await CraftingTestInputs.SqlAsync(db, "DROP TRIGGER fail_second_discard ON inventory_movements");
        Assert.Equal(2, (await f.Progression.DiscardEquipmentAsync(f.Player, "rollback", Request(f, a, b), Ct)).Items.Count);
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task ConcurrentSameRequestReplaysAndCompetingRequestCannotDestroyTheBodyAgain()
    {
        await using var db = await OpenAsync(); var f = await CraftingTestInputs.CreateAsync(db);
        var item = await CraftingTestInputs.ItemAsync(db, f); var request = Request(f, item);
        var results = await Task.WhenAll(f.Progression.DiscardEquipmentAsync(f.Player, "concurrent", request, Ct),
            new ProgressionRepository(db.DataSource, f.Clock).DiscardEquipmentAsync(f.Player, "concurrent", request, Ct));
        Assert.Equivalent(results[0], results[1], strict: true);
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Progression.DiscardEquipmentAsync(f.Player, "competing", request, Ct));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1", item));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_discard_batches"));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='equipment.discard'"));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task LegacyInventoryCanDiscardWithoutInventingSeasonOrChangingPermanentBalances()
    {
        await using var db = await OpenAsync(); var clock = new CraftingClock(DateTimeOffset.UtcNow);
        var player = await CraftingTestInputs.PlayerAsync(db, clock); var item = Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db, "INSERT INTO equipments(instance_id,owner_id,slot,quality,location,created_at) VALUES($1,$2,'Head','White','Inventory',now())", item, player);
        var balances = await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_wallets w WHERE player_id=$1", player);
        var response = await new ProgressionRepository(db.DataSource, clock).DiscardEquipmentAsync(player, "legacy", new([new(item, 1)]), Ct);
        Assert.Null(response.SeasonId); Assert.Null(Assert.Single(response.Items).AssetScope);
        Assert.Equal(balances, await db.ScalarAsync<string>("SELECT row_to_json(w)::text FROM player_wallets w WHERE player_id=$1", player));
        Assert.True(await db.ScalarAsync<bool>("SELECT season_id IS NULL AND config_version IS NULL AND stats_version IS NULL FROM inventory_movements WHERE item_id=$1 AND reason='equipment.discard'", item));
    }
}
