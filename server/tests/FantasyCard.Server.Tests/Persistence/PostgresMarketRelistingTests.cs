using System.Security.Cryptography;
using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Progression;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresMarketRelistingTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Forward_migration_preserves_sold_history_and_resale_replays_without_double_transfer()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var seller = await PlayerAsync(database, "Original Seller");
        var buyer = await PlayerAsync(database, "Resale Buyer");
        var equipment = await EquipmentAsync(database, seller);
        var economy = new EconomyRepository(database.DataSource, TimeProvider.System);
        var original = await economy.ListAsync(seller, "original-list", new(equipment, 100), ct);
        var purchase = await economy.PurchaseMarketAsync(buyer, "original-purchase", original.ListingId, original.Version, ct);

        // Recreate V028's constraint/state on populated isolated data, then run the real migrator.
        await database.ExecuteAsync("DROP INDEX ux_market_listings_active_equipment");
        await database.ExecuteAsync("ALTER TABLE market_listings ADD CONSTRAINT market_listings_equipment_id_key UNIQUE(equipment_id)");
        await database.ExecuteAsync("DELETE FROM schema_migrations WHERE version=29");
        var originalChecksum = await database.ScalarAsync<string>("SELECT checksum FROM schema_migrations WHERE version=5");
        var migrator = new DatabaseMigrator(database.DataSource, NullLogger<DatabaseMigrator>.Instance);
        await migrator.StartAsync(ct);
        await migrator.StartAsync(ct);
        Assert.Equal(originalChecksum, await database.ScalarAsync<string>("SELECT checksum FROM schema_migrations WHERE version=5"));
        Assert.Equal("Sold", await database.ScalarAsync<string>("SELECT status FROM market_listings WHERE listing_id=$1", original.ListingId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM market_transactions WHERE listing_id=$1", original.ListingId));

        var relisted = await economy.ListAsync(buyer, "resale-list", new(equipment, 200), ct);
        Assert.NotEqual(original.ListingId, relisted.ListingId);
        Assert.Equal(PersistedPrecision(relisted), PersistedPrecision(await economy.ListAsync(buyer, "resale-list", new(equipment, 200), ct)));
        var movementsBeforeReplay = await database.ScalarAsync<long>("SELECT COUNT(*) FROM inventory_movements WHERE item_id=$1", equipment);
        await economy.PurchaseMarketAsync(buyer, "original-purchase", original.ListingId, original.Version, ct);
        Assert.Equal(buyer, await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipment));
        Assert.Equal("MarketListed", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipment));
        Assert.Equal(movementsBeforeReplay, await database.ScalarAsync<long>("SELECT COUNT(*) FROM inventory_movements WHERE item_id=$1", equipment));
        Assert.Equal(purchase.BuyerGoldAfter, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", buyer));
        var boughtBack = await economy.PurchaseMarketAsync(seller, "resale-purchase", relisted.ListingId, relisted.Version, ct);
        await economy.PurchaseMarketAsync(seller, "resale-purchase", relisted.ListingId, relisted.Version, ct);
        Assert.Equal(boughtBack.BuyerGoldAfter, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", seller));
        Assert.Equal(seller, await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipment));
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM market_listings WHERE equipment_id=$1 AND status='Sold'", equipment));
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM market_transactions"));
        Assert.Equal(4L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM economy_ledger WHERE currency='Gold'"));
        Assert.True((await new EconomyReconciliationRepository(database.DataSource).InspectAsync(ct)).IsHealthy);
        await using (var equip = database.DataSource.CreateCommand("UPDATE equipments SET location='Equipped' WHERE instance_id=$1"))
        { equip.Parameters.AddWithValue(equipment); await equip.ExecuteNonQueryAsync(ct); }
        Assert.True((await new EconomyReconciliationRepository(database.DataSource).InspectAsync(ct)).IsHealthy);
        // Historical validation must still detect a transaction diverging from its sale terms.
        await using var corruptReceipt = database.DataSource.CreateCommand("UPDATE market_transactions SET price_gold=price_gold+1,seller_net_gold=seller_net_gold+1 WHERE listing_id=$1");
        corruptReceipt.Parameters.AddWithValue(original.ListingId); await corruptReceipt.ExecuteNonQueryAsync(ct);
        var audit = await new EconomyReconciliationRepository(database.DataSource).InspectAsync(ct);
        Assert.Equal(1, audit.SoldListingMismatchCount);
        Assert.Equal(0, audit.MarketTransactionAmountMismatchCount);
        await using var missingReceipt = database.DataSource.CreateCommand("DELETE FROM market_transactions WHERE listing_id=$1");
        missingReceipt.Parameters.AddWithValue(original.ListingId); await missingReceipt.ExecuteNonQueryAsync(ct);
        Assert.Equal(1, (await new EconomyReconciliationRepository(database.DataSource).InspectAsync(ct)).SoldListingMismatchCount);
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(false)]
    [InlineData(true)]
    [Trait("Category", "PostgresIntegration")]
    public async Task Cancelled_or_expired_history_does_not_block_new_listing(bool expire)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var seller = await PlayerAsync(database, "History Seller");
        var equipment = await EquipmentAsync(database, seller);
        var economy = new EconomyRepository(database.DataSource, TimeProvider.System);
        var old = await economy.ListAsync(seller, "history-original", new(equipment, 100), ct);
        if (expire)
        {
            await using var timestamp = database.DataSource.CreateCommand("UPDATE market_listings SET expires_at=now()-interval '1 second' WHERE listing_id=$1");
            timestamp.Parameters.AddWithValue(old.ListingId); await timestamp.ExecuteNonQueryAsync(ct);
            Assert.Contains(old.ListingId, await economy.ExpireListingsAsync(ct));
        }
        else await economy.CancelListingAsync(seller, old.ListingId, "history-cancel", ct);
        var current = await economy.ListAsync(seller, "history-relist", new(equipment, 101), ct);
        Assert.NotEqual(old.ListingId, current.ListingId);
        var replay = await economy.ListAsync(seller, "history-original", new(equipment, 100), ct);
        Assert.Equal(expire ? "Expired" : "Cancelled", replay.Status);
        if (!expire) await economy.CancelListingAsync(seller, old.ListingId, "history-cancel", ct);
        Assert.Equal("MarketListed", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipment));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM market_listings WHERE equipment_id=$1 AND status='Active'", equipment));
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM market_listings WHERE equipment_id=$1", equipment));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_same_item_listing_has_one_active_owner_and_same_key_replays()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var seller = await PlayerAsync(database, "Concurrent Seller");
        var equipment = await EquipmentAsync(database, seller);
        var economy = new EconomyRepository(database.DataSource, TimeProvider.System);
        var results = await Task.WhenAll(Enumerable.Range(0, 4).Select(async i =>
        {
            try { return await economy.ListAsync(seller, "parallel-" + i, new(equipment, 100), ct); }
            catch (InvalidOperationException) { return null; }
        }));
        var listing = Assert.Single(results.OfType<MarketListingResponse>());
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT COUNT(*) FROM market_listings WHERE equipment_id=$1 AND status='Active'", equipment));
        await economy.CancelListingAsync(seller, listing.ListingId, "parallel-cancel", ct);
        var replays = await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => economy.ListAsync(seller, "parallel-same-key", new(equipment, 101), ct)));
        Assert.All(replays, value => Assert.Equal(PersistedPrecision(replays[0]), PersistedPrecision(value)));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => economy.ListAsync(seller, "parallel-same-key", new(equipment, 102), ct));
        await using var duplicate = database.DataSource.CreateCommand("INSERT INTO market_listings(listing_id,seller_id,equipment_id,price_gold,status,version,created_at,expires_at) SELECT gen_random_uuid(),seller_id,equipment_id,price_gold,'Active',1,created_at,expires_at FROM market_listings WHERE listing_id=$1");
        duplicate.Parameters.AddWithValue(replays[0].ListingId);
        var conflict = await Assert.ThrowsAsync<PostgresException>(async () => await duplicate.ExecuteNonQueryAsync(ct));
        Assert.Equal("23505", conflict.SqlState);
        Assert.Equal("ux_market_listings_active_equipment", conflict.ConstraintName);
    }

    // PostgreSQL timestamptz stores microseconds; DateTimeOffset carries 100-nanosecond ticks.
    private static MarketListingResponse PersistedPrecision(MarketListingResponse value) => value with
    {
        CreatedAt = new DateTimeOffset(value.CreatedAt.Ticks / 10 * 10, value.CreatedAt.Offset),
        ExpiresAt = new DateTimeOffset(value.ExpiresAt.Ticks / 10 * 10, value.ExpiresAt.Offset)
    };

    private static async Task<Guid> PlayerAsync(PostgresTestSchema database, string name)
    {
        var ct = TestContext.Current.CancellationToken;
        var now = DateTimeOffset.UtcNow;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var player = await identity.SignInLocalAsync(Guid.NewGuid().ToString("N"), name, RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await using var fund = database.DataSource.CreateCommand("UPDATE player_wallets SET gold=10000 WHERE player_id=$1");
        fund.Parameters.AddWithValue(player.UserId); await fund.ExecuteNonQueryAsync(ct);
        return player.UserId;
    }
    private static async Task<Guid> EquipmentAsync(PostgresTestSchema database, Guid owner)
    {
        var id = Guid.NewGuid();
        await using var command = database.DataSource.CreateCommand("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Chest','Blue',0,false,'Inventory',1,now())");
        command.Parameters.AddWithValue(id); command.Parameters.AddWithValue(owner);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        return id;
    }
}
