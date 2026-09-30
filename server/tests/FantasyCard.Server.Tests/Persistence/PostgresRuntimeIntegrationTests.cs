using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresRuntimeIntegrationTests
{
    public static bool HasTestDatabase => !string.IsNullOrWhiteSpace(
        Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES"));

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Inventory_and_class_loadout_reads_return_complete_lobby_assets()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "inventory-device-" + Guid.NewGuid().ToString("N"),
            "Inventory player",
            TokenHash("inventory-token-" + Guid.NewGuid().ToString("N")),
            now,
            now.AddHours(1),
            cancellationToken);
        var inventoryItemId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            """
            UPDATE player_consumables
            SET health_potion_count=3, advanced_bag_count=2, top_bag_count=1, version=version+1
            WHERE player_id=$1
            """))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            """
            INSERT INTO equipments(
                instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,
                element,effect_affix,secondary_trait)
            VALUES($1,$2,'Head','Purple',2,false,'Inventory',1,$3,'Water','Vitality','DrawInterval')
            """))
        {
            command.Parameters.AddWithValue(inventoryItemId);
            command.Parameters.AddWithValue(player.UserId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var repository = new ProgressionRepository(database.DataSource);

        var inventory = await repository.GetInventoryAsync(player.UserId, cancellationToken);
        var loadout = await repository.GetLoadoutAsync(player.UserId, HeroClass.Priest, cancellationToken);

        Assert.Equal(new(50, 1, 49), inventory.Summary);
        Assert.Equal(new(3, 2, 1), inventory.Consumables);
        var item = Assert.Single(inventory.Equipments);
        Assert.Equal(inventoryItemId, item.InstanceId);
        Assert.Equal("Inventory", item.Location);
        Assert.Equal(("Head", "Purple", 2, "Water", "Vitality", "DrawInterval"),
            (item.Slot, item.Quality, item.Level, item.Element, item.EffectAffix, item.SecondaryTrait));
        Assert.NotNull(loadout);
        Assert.Equal(HeroClassDto.Priest, loadout.HeroClass);
        Assert.Equal(5, loadout.EquipmentIds.Count);
        Assert.All(loadout.EquipmentIds, Assert.Null);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_market_purchase_transfers_equipment_and_gold_exactly_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var identity = CreateIdentityRepository(database.DataSource);
        var seller = await identity.SignInLocalAsync(
            "market-seller-" + Guid.NewGuid().ToString("N"), "Seller",
            TokenHash("market-seller-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var firstBuyer = await identity.SignInLocalAsync(
            "market-buyer-a-" + Guid.NewGuid().ToString("N"), "Buyer A",
            TokenHash("market-buyer-a-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var secondBuyer = await identity.SignInLocalAsync(
            "market-buyer-b-" + Guid.NewGuid().ToString("N"), "Buyer B",
            TokenHash("market-buyer-b-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var equipmentId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_wallets SET gold=2000 WHERE player_id IN ($1,$2)"))
        {
            command.Parameters.AddWithValue(firstBuyer.UserId);
            command.Parameters.AddWithValue(secondBuyer.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            """
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at)
            VALUES($1,$2,'Chest','Blue',0,false,'Inventory',1,$3)
            """))
        {
            command.Parameters.AddWithValue(equipmentId);
            command.Parameters.AddWithValue(seller.UserId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var repository = new EconomyRepository(database.DataSource, TimeProvider.System);
        var listing = await repository.ListAsync(
            seller.UserId, "market-listing-once", new(equipmentId, 1000), cancellationToken);
        var attempts = await Task.WhenAll(
            AttemptPurchaseAsync(firstBuyer.UserId, "market-buy-a"),
            AttemptPurchaseAsync(secondBuyer.UserId, "market-buy-b"));
        var winner = Assert.Single(attempts, attempt => attempt.Response is not null);
        var loser = Assert.Single(attempts, attempt => attempt.Response is null);

        Assert.Equal(1000L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", winner.BuyerId));
        Assert.Equal(2000L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", loser.BuyerId));
        Assert.Equal(900L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", seller.UserId));
        Assert.Equal(winner.BuyerId, await database.ScalarAsync<Guid>(
            "SELECT owner_id FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal("Sold", await database.ScalarAsync<string>(
            "SELECT status FROM market_listings WHERE listing_id=$1", listing.ListingId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM market_transactions WHERE listing_id=$1", listing.ListingId));
        Assert.Equal(2L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE item_id=$1", equipmentId));
        Assert.Equal(2L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE request_id=$1", winner.RequestId));

        async Task<(Guid BuyerId, string RequestId, MarketPurchaseResponse? Response)> AttemptPurchaseAsync(
            Guid buyerId,
            string requestId)
        {
            try
            {
                return (buyerId, requestId, await repository.PurchaseMarketAsync(
                    buyerId, requestId, listing.ListingId, listing.Version, cancellationToken));
            }
            catch (InvalidOperationException)
            {
                return (buyerId, requestId, null);
            }
        }
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Shop_failures_and_replays_do_not_partially_debit_or_grant_assets()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "shop-device-" + Guid.NewGuid().ToString("N"), "Shop player",
            TokenHash("shop-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_wallets SET gold=5000 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var repository = new EconomyRepository(database.DataSource, TimeProvider.System);

        var potionPurchase = await repository.PurchaseAsync(
            player.UserId, "shop-potions", new("health_potion", 2), cancellationToken);
        var potionReplay = await repository.PurchaseAsync(
            player.UserId, "shop-potions", new("health_potion", 2), cancellationToken);

        Assert.Equal(potionPurchase, potionReplay);
        Assert.Equal(4800, potionPurchase.GoldAfter);
        Assert.Equal(2, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM shop_purchases WHERE request_id=$1", "shop-potions"));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE request_id=$1", "shop-potions"));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => repository.PurchaseAsync(
            player.UserId, "shop-potions", new("health_potion", 1), cancellationToken));
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.PurchaseAsync(
            player.UserId, "shop-potion-over-limit", new("health_potion", 3), cancellationToken));
        Assert.Equal(4800L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(2, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.UserId));

        await repository.PurchaseAsync(player.UserId, "shop-bags", new("advanced_bag", 2), cancellationToken);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.PurchaseAsync(
            player.UserId, "shop-bags-over-cap", new("top_bag", 2), cancellationToken));
        Assert.Equal(3200L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(2, await database.ScalarAsync<int>(
            "SELECT advanced_bag_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT top_bag_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM shop_purchases WHERE request_id=$1", "shop-bags-over-cap"));

        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_wallets SET gold=50 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.PurchaseAsync(
            player.UserId, "shop-not-enough-gold", new("warrior_soul", 1), cancellationToken));
        Assert.Equal(50L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT warrior_soul FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM shop_purchases WHERE request_id=$1", "shop-not-enough-gold"));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE request_id=$1", "shop-not-enough-gold"));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Shop_daily_cards_are_deterministic_and_purchase_grants_exact_card_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 9, 0, 0, 0, TimeSpan.Zero));
        var now = time.GetUtcNow();
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "daily-shop-device-" + Guid.NewGuid().ToString("N"), "Daily shop player",
            TokenHash("daily-shop-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_wallets SET gold=10000 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }

        var firstRepository = new EconomyRepository(database.DataSource, time);
        var secondRepository = new EconomyRepository(database.DataSource, time);
        var shops = await Task.WhenAll(
            firstRepository.GetShopAsync(player.UserId, cancellationToken),
            secondRepository.GetShopAsync(player.UserId, cancellationToken));
        Assert.Equal(shops[0].ResetKey, shops[1].ResetKey);
        Assert.Equal(shops[0].Products, shops[1].Products);
        Assert.Equal("2026-09-09", shops[0].ResetKey);
        Assert.Equal(12, shops[0].Products.Count);
        var dailyCards = shops[0].Products
            .Where(product => product.ProductId.StartsWith("daily_card_", StringComparison.Ordinal))
            .OrderBy(product => product.ProductId, StringComparer.Ordinal)
            .ToArray();
        Assert.Equal(3, dailyCards.Length);

        var offeredCardIds = new List<string>();
        foreach (var product in dailyCards)
        {
            Assert.Equal("Cards", product.Kind);
            Assert.Equal(1, product.Limit);
            using var payload = JsonDocument.Parse(product.Payload);
            var cardId = payload.RootElement.GetProperty("cardId").GetString();
            var quality = payload.RootElement.GetProperty("quality").GetString();
            Assert.NotNull(cardId);
            Assert.NotNull(quality);
            offeredCardIds.Add(cardId);
            Assert.Equal(await database.ScalarAsync<int>(
                "SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2", player.UserId, cardId) > 0,
                product.AlreadyOwned);
            var configuredPrice = GameConfigCatalog.Current.ShopCardPrice(quality);
            Assert.Equal(configuredPrice.PriceGold, product.PriceGold);
        }
        Assert.Equal(3, offeredCardIds.Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(12L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM shop_rotations WHERE reset_key=$1", shops[0].ResetKey));

        var selectedProduct = dailyCards[0];
        using var selectedPayload = JsonDocument.Parse(selectedProduct.Payload);
        var selectedCardId = selectedPayload.RootElement.GetProperty("cardId").GetString()!;
        await using (var makeAvailable = database.DataSource.CreateCommand(
            "UPDATE player_cards SET unlocked=false,copy_count=0,level=0 WHERE player_id=$1 AND card_id=$2"))
        {
            makeAvailable.Parameters.AddWithValue(player.UserId);
            makeAvailable.Parameters.AddWithValue(selectedCardId);
            await makeAvailable.ExecuteNonQueryAsync(cancellationToken);
        }
        var copiesBefore = await database.ScalarAsync<int>(
            "SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2", player.UserId, selectedCardId);
        var purchase = await firstRepository.PurchaseAsync(
            player.UserId, "daily-card-purchase", new(selectedProduct.ProductId), cancellationToken);
        var replay = await firstRepository.PurchaseAsync(
            player.UserId, "daily-card-purchase", new(selectedProduct.ProductId), cancellationToken);
        Assert.Equal(purchase, replay);
        Assert.Equal(0, copiesBefore);
        Assert.Equal(1, await database.ScalarAsync<int>(
            "SELECT copy_count FROM player_cards WHERE player_id=$1 AND card_id=$2", player.UserId, selectedCardId));
        Assert.True(await database.ScalarAsync<bool>(
            "SELECT unlocked FROM player_cards WHERE player_id=$1 AND card_id=$2", player.UserId, selectedCardId));
        await Assert.ThrowsAsync<InvalidOperationException>(() => firstRepository.PurchaseAsync(
            player.UserId, "daily-card-over-limit", new(selectedProduct.ProductId), cancellationToken));
        Assert.True((await firstRepository.GetShopAsync(player.UserId, cancellationToken)).Products
            .Single(product => product.ProductId == selectedProduct.ProductId).AlreadyOwned);

        var totalCopiesBeforePack = await database.ScalarAsync<long>(
            "SELECT sum(copy_count) FROM player_cards WHERE player_id=$1", player.UserId);
        await firstRepository.PurchaseAsync(player.UserId, "card-pack-purchase", new("card_pack"), cancellationToken);
        Assert.Equal(totalCopiesBeforePack + 3, await database.ScalarAsync<long>(
            "SELECT sum(copy_count) FROM player_cards WHERE player_id=$1", player.UserId));

        time.Advance(TimeSpan.FromDays(1));
        var nextShop = await firstRepository.GetShopAsync(player.UserId, cancellationToken);
        Assert.Equal("2026-09-10", nextShop.ResetKey);
        Assert.Equal(3, nextShop.Products.Count(product =>
            product.ProductId.StartsWith("daily_card_", StringComparison.Ordinal)));
        Assert.Equal(12L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM shop_rotations WHERE reset_key=$1", nextShop.ResetKey));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Equipment_enhancement_rolls_back_failure_and_consumes_bound_material_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "enhance-device-" + Guid.NewGuid().ToString("N"), "Enhance player",
            TokenHash("enhance-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var targetId = Guid.NewGuid();
        var materialId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET equipment_fragments=255 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            """
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at)
            VALUES($1,$2,'Chest','Purple',3,false,'Inventory',1,$4),
                  ($3,$2,'Feet','Purple',5,true,'Inventory',1,$4)
            """))
        {
            command.Parameters.AddWithValue(targetId);
            command.Parameters.AddWithValue(player.UserId);
            command.Parameters.AddWithValue(materialId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var repository = new ProgressionRepository(database.DataSource);
        var request = new EnhanceEquipmentRequest(1, materialId);

        await Assert.ThrowsAsync<DomainValidationException>(() => repository.EnhanceEquipmentAsync(
            player.UserId, targetId, "enhance-purple-four", request, cancellationToken));
        Assert.Equal(255L, await database.ScalarAsync<long>(
            "SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal(3, await database.ScalarAsync<int>(
            "SELECT level FROM equipments WHERE instance_id=$1", targetId));
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", materialId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM idempotency_records WHERE request_id=$1", "enhance-purple-four"));

        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET equipment_fragments=256 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var enhanced = await repository.EnhanceEquipmentAsync(
            player.UserId, targetId, "enhance-purple-four", request, cancellationToken);
        var replay = await repository.EnhanceEquipmentAsync(
            player.UserId, targetId, "enhance-purple-four", request, cancellationToken);

        Assert.Equal(4, enhanced.Equipment.Level);
        Assert.Equal(0, enhanced.EquipmentFragments);
        Assert.Equal(materialId, enhanced.ConsumedMaterialEquipmentId);
        Assert.Equal(enhanced, replay);
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal("EnhanceMaterialConsumed", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", materialId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1", "enhance-purple-four"));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE request_id=$1", "enhance-purple-four"));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM idempotency_records WHERE request_id=$1", "enhance-purple-four"));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => repository.EnhanceEquipmentAsync(
            player.UserId, targetId, "enhance-purple-four", request with { ExpectedVersion = 2 }, cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Red_equipment_enhancement_rejects_orange_and_consumes_red_material()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "red-enhance-device-" + Guid.NewGuid().ToString("N"), "Red enhance player",
            TokenHash("red-enhance-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var targetId = Guid.NewGuid();
        var orangeMaterialId = Guid.NewGuid();
        var redMaterialId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET equipment_fragments=768 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            """
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at)
            VALUES($1,$2,'Chest','Red',3,false,'Inventory',1,$5),
                  ($3,$2,'Feet','Orange',5,true,'Inventory',1,$5),
                  ($4,$2,'Head','Red',0,true,'Inventory',1,$5)
            """))
        {
            command.Parameters.AddWithValue(targetId);
            command.Parameters.AddWithValue(player.UserId);
            command.Parameters.AddWithValue(orangeMaterialId);
            command.Parameters.AddWithValue(redMaterialId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var repository = new ProgressionRepository(database.DataSource);

        await Assert.ThrowsAsync<DomainValidationException>(() => repository.EnhanceEquipmentAsync(
            player.UserId, targetId, "enhance-red-with-orange",
            new(1, orangeMaterialId), cancellationToken));
        Assert.Equal(768L, await database.ScalarAsync<long>(
            "SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", orangeMaterialId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM idempotency_records WHERE request_id=$1", "enhance-red-with-orange"));

        var enhanced = await repository.EnhanceEquipmentAsync(
            player.UserId, targetId, "enhance-red-with-red",
            new(1, redMaterialId), cancellationToken);

        Assert.Equal(("Red", 4, 0L),
            (enhanced.Equipment.Quality, enhanced.Equipment.Level, enhanced.EquipmentFragments));
        Assert.Equal(redMaterialId, enhanced.ConsumedMaterialEquipmentId);
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", orangeMaterialId));
        Assert.Equal("EnhanceMaterialConsumed", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", redMaterialId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1", "enhance-red-with-red"));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE request_id=$1", "enhance-red-with-red"));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Class_weapon_enhancement_rolls_back_and_replays_without_material_consumption()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "weapon-enhance-device-" + Guid.NewGuid().ToString("N"), "Weapon player",
            TokenHash("weapon-enhance-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET equipment_fragments=7 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var repository = new ProgressionRepository(database.DataSource);

        await Assert.ThrowsAsync<DomainValidationException>(() => repository.EnhanceWeaponAsync(
            player.UserId, HeroClass.Priest, "enhance-priest-weapon", 1, cancellationToken));
        Assert.Equal(7L, await database.ScalarAsync<long>(
            "SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT level FROM class_weapons WHERE player_id=$1 AND hero_class=1", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM idempotency_records WHERE request_id=$1", "enhance-priest-weapon"));

        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET equipment_fragments=8 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var enhanced = await repository.EnhanceWeaponAsync(
            player.UserId, HeroClass.Priest, "enhance-priest-weapon", 1, cancellationToken);
        var replay = await repository.EnhanceWeaponAsync(
            player.UserId, HeroClass.Priest, "enhance-priest-weapon", 1, cancellationToken);

        Assert.Equal(1, enhanced.Equipment.Level);
        Assert.Equal(0, enhanced.EquipmentFragments);
        Assert.Null(enhanced.ConsumedMaterialEquipmentId);
        Assert.Equal(enhanced, replay);
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE request_id=$1", "enhance-priest-weapon"));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1", "enhance-priest-weapon"));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM idempotency_records WHERE request_id=$1", "enhance-priest-weapon"));
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => repository.EnhanceWeaponAsync(
            player.UserId, HeroClass.Priest, "enhance-priest-weapon", 2, cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_first_sign_in_provisions_one_complete_player_aggregate()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var repository = CreateIdentityRepository(database.DataSource);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var subject = "concurrent-device-" + Guid.NewGuid().ToString("N");

        var profiles = await Task.WhenAll(Enumerable.Range(0, 8).Select(index =>
            repository.SignInLocalAsync(
                subject + index,
                "Concurrent player",
                TokenHash($"concurrent-token-{index}-{subject}"),
                now,
                now.AddHours(1),
                cancellationToken)));

        var playerId = Assert.Single(profiles.Select(profile => profile.UserId).Distinct());
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM players WHERE user_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM external_identities WHERE provider='local-name' AND external_subject=$1", "concurrent player"));
        Assert.Equal(8L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_sessions WHERE player_id=$1", playerId));
        await AssertProvisionedAggregateAsync(database, playerId);

        var progression = new ProgressionRepository(database.DataSource);
        var bootstrap = await CreateBootstrapRepository(database.DataSource, progression, TimeProvider.System)
            .GetAsync(profiles[0], cancellationToken);
        Assert.Equal(playerId, bootstrap.Player.UserId);
        Assert.Equal(BootstrapRepository.CurrentConfigVersion, bootstrap.ConfigVersion);
        Assert.Equal(3, bootstrap.ClassWeapons.Count);
        Assert.Equal(3, bootstrap.EquippedLoadouts.Count);
        Assert.Equal(3, bootstrap.Decks.Count);
        Assert.All(bootstrap.Decks, deck => Assert.Equal(20, deck.CardIds.Count));
        Assert.NotEmpty(bootstrap.Cards);
        Assert.Equal(0, bootstrap.InventorySummary.EquipmentCount);
        Assert.NotNull(bootstrap.Inventory);
        Assert.NotNull(bootstrap.Shop);
        Assert.NotNull(bootstrap.Market);
        Assert.NotNull(bootstrap.Mail);
        Assert.Null(bootstrap.ActivePreparation);
        Assert.Null(bootstrap.UnfinishedMatch);
        Assert.Null(bootstrap.UnfinishedSettlement);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Legacy_identity_tables_upgrade_and_existing_player_is_provisioned_idempotently()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        var playerId = Guid.NewGuid();
        var subject = "legacy-device-" + Guid.NewGuid().ToString("N");
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        await database.ExecuteAsync(
            """
            CREATE TABLE players (
                user_id uuid PRIMARY KEY,
                display_name varchar(80) NOT NULL,
                selected_class smallint NULL CHECK (selected_class BETWEEN 1 AND 3),
                version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
                created_at timestamptz NOT NULL,
                updated_at timestamptz NOT NULL);
            CREATE TABLE external_identities (
                provider varchar(32) NOT NULL,
                external_subject varchar(160) NOT NULL,
                player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                created_at timestamptz NOT NULL,
                PRIMARY KEY (provider, external_subject),
                UNIQUE (provider, player_id));
            CREATE TABLE player_sessions (
                session_id uuid PRIMARY KEY,
                player_id uuid NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
                token_hash bytea NOT NULL UNIQUE,
                expires_at timestamptz NOT NULL,
                created_at timestamptz NOT NULL);
            """);
        await using (var command = database.DataSource.CreateCommand(
            """
            INSERT INTO players(user_id,display_name,selected_class,version,created_at,updated_at)
            VALUES($1,$2,NULL,1,$3,$3);
            """))
        {
            command.Parameters.AddWithValue(playerId);
            command.Parameters.AddWithValue("Legacy player");
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            """
            INSERT INTO external_identities(provider,external_subject,player_id,created_at)
            VALUES('local',$1,$2,$3);
            """))
        {
            command.Parameters.AddWithValue(subject);
            command.Parameters.AddWithValue(playerId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }

        await database.ExecuteAsync(
            """
            CREATE TABLE player_wallets (
                player_id uuid PRIMARY KEY REFERENCES players(user_id) ON DELETE CASCADE,
                gold bigint NOT NULL DEFAULT 0 CHECK (gold >= 0),
                diamond bigint NOT NULL DEFAULT 0 CHECK (diamond >= 0),
                version bigint NOT NULL DEFAULT 1 CHECK (version > 0));
            """);
        await using (var wallet = database.DataSource.CreateCommand(
            "INSERT INTO player_wallets(player_id,gold,diamond,version) VALUES($1,777,3,5)"))
        {
            wallet.Parameters.AddWithValue(playerId);
            await wallet.ExecuteNonQueryAsync(cancellationToken);
        }

        await database.MigrateAsync();
        var repository = CreateIdentityRepository(database.DataSource);
        var first = await repository.SignInLocalAsync(
            subject, "Legacy player", TokenHash("legacy-token-1"), now, now.AddHours(1), cancellationToken);
        var second = await repository.SignInLocalAsync(
            "another-device", "Legacy player", TokenHash("legacy-token-2"), now, now.AddHours(1), cancellationToken);

        Assert.Equal(playerId, first.UserId);
        Assert.Equal(playerId, second.UserId);
        Assert.Equal("Legacy player", first.DisplayName);
        await AssertProvisionedAggregateAsync(database, playerId);
        Assert.Equal(777L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
        Assert.Equal(5L, await database.ScalarAsync<long>("SELECT version FROM player_wallets WHERE player_id=$1", playerId));
        var newName = await repository.SignInLocalAsync(
            subject, "New account", TokenHash("legacy-new-name"), now, now.AddHours(1), cancellationToken);
        Assert.NotEqual(playerId, newName.UserId);
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", newName.UserId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task V013_upgrades_legacy_card_ids_and_allows_orange_rarity()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "v013-device-" + Guid.NewGuid().ToString("N"),
            "V013 player",
            TokenHash("v013-token-" + Guid.NewGuid().ToString("N")),
            now,
            now.AddHours(1),
            cancellationToken);

        await database.ExecuteAsync("DELETE FROM player_cards WHERE rarity = 5");
        await database.ExecuteAsync("ALTER TABLE player_cards DROP CONSTRAINT player_cards_rarity_check");
        await database.ExecuteAsync(
            "ALTER TABLE player_cards ADD CONSTRAINT player_cards_rarity_check CHECK (rarity BETWEEN 1 AND 4)");
        await using (var renameOwnedCard = database.DataSource.CreateCommand(
            "UPDATE player_cards SET card_id='common-01' WHERE player_id=$1 AND card_id='C01'"))
        {
            renameOwnedCard.Parameters.AddWithValue(player.UserId);
            await renameOwnedCard.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var renameDeckCards = database.DataSource.CreateCommand(
            """
            UPDATE player_deck_cards cards
            SET card_id='common-01'
            FROM player_decks decks
            WHERE cards.deck_id=decks.deck_id
              AND decks.player_id=$1
              AND cards.card_id='C01'
            """))
        {
            renameDeckCards.Parameters.AddWithValue(player.UserId);
            await renameDeckCards.ExecuteNonQueryAsync(cancellationToken);
        }
        await database.ExecuteAsync("DELETE FROM schema_migrations WHERE version = 13");

        await database.MigrateAsync();

        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_cards WHERE player_id=$1 AND card_id='C01'", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_cards WHERE player_id=$1 AND card_id='common-01'", player.UserId));
        Assert.True(await database.ScalarAsync<long>(
            """
            SELECT count(*) FROM player_deck_cards cards
            JOIN player_decks decks ON decks.deck_id=cards.deck_id
            WHERE decks.player_id=$1 AND cards.card_id='C01'
            """, player.UserId) > 0);
        Assert.Equal(0L, await database.ScalarAsync<long>(
            """
            SELECT count(*) FROM player_deck_cards cards
            JOIN player_decks decks ON decks.deck_id=cards.deck_id
            WHERE decks.player_id=$1 AND cards.card_id='common-01'
            """, player.UserId));

        await using var insertOrange = database.DataSource.CreateCommand(
            """
            INSERT INTO player_cards(
                player_id,card_id,hero_class,rarity,is_monster,unlocked,copy_count,level,version)
            VALUES($1,'V013-ORANGE-TEST',NULL,5,false,false,0,0,1)
            """);
        insertOrange.Parameters.AddWithValue(player.UserId);
        Assert.Equal(1, await insertOrange.ExecuteNonQueryAsync(cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Concurrent_deck_writes_allow_one_version_winner_and_replay_its_response()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "deck-device-" + Guid.NewGuid().ToString("N"),
            "Deck player",
            TokenHash("deck-token-" + Guid.NewGuid().ToString("N")),
            now,
            now.AddHours(1),
            cancellationToken);
        var repository = new ProgressionRepository(database.DataSource);
        var current = Assert.Single(
            await repository.GetDecksAsync(player.UserId, cancellationToken),
            deck => deck.HeroClass == HeroClassDto.Priest);
        var reversed = current.CardIds.Reverse().ToArray();
        var rotated = current.CardIds.Skip(1).Append(current.CardIds[0]).ToArray();

        var writes = await Task.WhenAll(
            repository.SaveDeckAsync(player.UserId, HeroClass.Priest, reversed, "deck-write-a", current.Version, now, cancellationToken),
            repository.SaveDeckAsync(player.UserId, HeroClass.Priest, rotated, "deck-write-b", current.Version, now, cancellationToken));

        var winner = Assert.Single(writes, result => result.Status == SaveDeckStatus.Updated);
        Assert.Single(writes, result => result.Status == SaveDeckStatus.VersionConflict);
        Assert.NotNull(winner.Deck);
        Assert.Equal(current.Version + 1, winner.Deck.Version);
        var winnerRequestId = ReferenceEquals(winner, writes[0]) ? "deck-write-a" : "deck-write-b";
        var replay = await repository.SaveDeckAsync(
            player.UserId,
            HeroClass.Priest,
            winner.Deck.CardIds,
            winnerRequestId,
            current.Version,
            now,
            cancellationToken);
        Assert.Equal(winner.Status, replay.Status);
        Assert.NotNull(replay.Deck);
        Assert.Equal(winner.Deck.DeckId, replay.Deck.DeckId);
        Assert.Equal(winner.Deck.HeroClass, replay.Deck.HeroClass);
        Assert.Equal(winner.Deck.CardIds, replay.Deck.CardIds);
        Assert.Equal(winner.Deck.Version, replay.Deck.Version);
        Assert.Equal(winner.Deck.UpdatedAt, replay.Deck.UpdatedAt);

        var persisted = Assert.Single(
            await repository.GetDecksAsync(player.UserId, cancellationToken),
            deck => deck.HeroClass == HeroClassDto.Priest);
        Assert.Equal(winner.Deck.CardIds, persisted.CardIds);
        Assert.Equal(current.Version + 1, persisted.Version);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Preparation_create_replay_conflict_and_cancel_release_are_atomic()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = DateTimeOffset.UtcNow;
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "preparation-device-" + Guid.NewGuid().ToString("N"),
            "Preparation player",
            TokenHash("preparation-token-" + Guid.NewGuid().ToString("N")),
            now,
            now.AddHours(1),
            cancellationToken);
        await database.InsertWornFeetAsync(player.UserId, HeroClass.Priest, cancellationToken);
        var progression = new ProgressionRepository(database.DataSource);
        var bootstrap = await CreateBootstrapRepository(database.DataSource, progression, TimeProvider.System)
            .GetAsync(player, cancellationToken);
        var deck = Assert.Single(bootstrap.Decks, value => value.HeroClass == HeroClassDto.Priest);
        var loadout = Assert.Single(
            bootstrap.EquippedLoadouts,
            value => value.HeroClass == HeroClassDto.Priest);
        var request = new CreatePreparationRequest(
            HeroClassDto.Priest,
            deck.Version,
            loadout.EquipmentIds,
            BackpackTierDto.Free,
            [],
            0,
            "Standard");
        var repository = new PreparationRepository(database.DataSource, TimeProvider.System);

        var creates = await Task.WhenAll(
            repository.CreateAsync(player.UserId, "preparation-create", request, cancellationToken),
            repository.CreateAsync(player.UserId, "preparation-create", request, cancellationToken));
        Assert.Contains(creates, result => result.Status == CreatePreparationStatus.Created);
        Assert.Contains(creates, result => result.Status == CreatePreparationStatus.Replayed);
        var preparationId = Assert.Single(creates.Select(result => result.Preparation!.PreparationId).Distinct());
        var equipmentId = Assert.Single(request.EquipmentIds!, value => value.HasValue)!.Value;
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM preparations WHERE player_id=$1 AND status='Active'", player.UserId));
        Assert.Equal("PreparationLocked", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='preparation.lock'", "preparation-create"));

        var changedRequest = request with { HeroClass = HeroClassDto.Mage };
        var conflict = await repository.CreateAsync(
            player.UserId, "preparation-create", changedRequest, cancellationToken);
        Assert.Equal(CreatePreparationStatus.RequestConflict, conflict.Status);

        Assert.Equal(CancelPreparationStatus.Cancelled, await repository.CancelAsync(
            player.UserId, preparationId, "preparation-cancel", cancellationToken));
        Assert.Equal(CancelPreparationStatus.Cancelled, await repository.CancelAsync(
            player.UserId, preparationId, "preparation-cancel", cancellationToken));
        Assert.Equal("Equipped", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='preparation.release'", "preparation-cancel"));
        var replacement = await repository.CreateAsync(
            player.UserId, "preparation-create-2", request, cancellationToken);
        Assert.Equal(CreatePreparationStatus.Created, replacement.Status);
        Assert.NotEqual(preparationId, replacement.Preparation!.PreparationId);
        Assert.Equal("PreparationLocked", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM preparations WHERE player_id=$1 AND status='Active'", player.UserId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Extraction_settlement_commits_all_assets_once_and_releases_notification()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = new DateTimeOffset(2026, 9, 7, 3, 0, 0, TimeSpan.Zero);
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "settlement-device-" + Guid.NewGuid().ToString("N"), "Settlement player",
            TokenHash("settlement-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        await database.ExecuteAsync(
            "UPDATE player_wallets SET gold=0; UPDATE player_materials SET warrior_soul=0,mage_soul=0,equipment_fragments=0; UPDATE player_consumables SET health_potion_count=0;");
        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        var heldEquipmentId = Guid.NewGuid();
        var wornEquipmentId = Guid.NewGuid();
        var generatedEquipmentId = Guid.NewGuid();
        var reclaimedGeneratedId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',17,'test','Running',$3)"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(roomId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Head','Blue',0,false,'InMatchBackpack',1,$3)"))
        {
            command.Parameters.AddWithValue(heldEquipmentId);
            command.Parameters.AddWithValue(player.UserId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Chest','Purple',1,false,'InMatchEquipped',1,$3)"))
        {
            command.Parameters.AddWithValue(wornEquipmentId);
            command.Parameters.AddWithValue(player.UserId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait) VALUES($1,$2,'Hands','Green',0,false,'RelicPile',1,$3,'Wood',NULL,'DrawInterval')"))
        {
            command.Parameters.AddWithValue(reclaimedGeneratedId);
            command.Parameters.AddWithValue(player.UserId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, new MutableTimeProvider(now), metrics);
        using var details = JsonDocument.Parse("{\"roomRevision\":42}");
        SettlementAsset[] assets =
        [
            new("Equipment", heldEquipmentId.ToString("D"), false),
            new("Equipment", wornEquipmentId.ToString("D"), false, Destination: "Equipped"),
            new("Equipment", generatedEquipmentId.ToString("D"), false, Equipment: new(
                "Feet", "Orange", "Fire", "Piercing", "ForcedEscape")),
            new("Equipment", reclaimedGeneratedId.ToString("D"), false, Equipment: new(
                "Hands", "Green", "Wood", null, "DrawInterval")),
            new("Gold", "gold", false, 17),
            new("WarriorSoul", "warrior_soul", false, 3),
            new("ClassSoul", "class_soul:Mage", false, 4),
            new("EquipmentFragments", "equipment_fragments", false, 5),
            new("HealthPotion", "health_potion", false, 2)
        ];

        var created = await repository.SettleAsync(
            matchId, player.UserId, "Extracted", details.RootElement, assets, cancellationToken);
        var replay = await repository.SettleAsync(
            matchId, player.UserId, "Extracted", details.RootElement, assets, cancellationToken);

        Assert.True(created.Created);
        Assert.False(replay.Created);
        Assert.Equal(created.SettlementId, replay.SettlementId);
        Assert.Equal(assets.Length, await repository.CommitHoldsAsync(created.SettlementId, cancellationToken));
        Assert.Equal(0, await repository.CommitHoldsAsync(created.SettlementId, cancellationToken));
        Assert.Equal(17L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(3L, await database.ScalarAsync<long>(
            "SELECT warrior_soul FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT mage_soul FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal(5L, await database.ScalarAsync<long>(
            "SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId));
        Assert.Equal(2, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT advanced_bag_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", heldEquipmentId));
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", generatedEquipmentId));
        Assert.Equal("Equipped", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", wornEquipmentId));
        Assert.Equal("Inventory", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", reclaimedGeneratedId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='settlement.extract'", player.UserId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", player.UserId));
        Assert.Equal("Completed", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", matchId));
        Assert.Equal("Settled", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE match_id=$1", matchId));

        var notification = Assert.Single(await repository.GetReadyNotificationsAsync(player.UserId, cancellationToken));
        Assert.Equal(created.SettlementId, notification.SettlementId);
        await repository.MarkNotificationPublishedAsync(created.SettlementId, cancellationToken);
        Assert.Empty(await repository.GetReadyNotificationsAsync(player.UserId, cancellationToken));
        Assert.Equal(created.SettlementId,
            (await repository.GetForMatchAsync(player.UserId, matchId, cancellationToken)).SettlementId);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Settlement_asset_commit_rolls_back_the_whole_batch_and_withholds_notification()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = new DateTimeOffset(2026, 9, 7, 4, 0, 0, TimeSpan.Zero);
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "settlement-rollback-device-" + Guid.NewGuid().ToString("N"), "Rollback player",
            TokenHash("settlement-rollback-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var owner = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "settlement-owner-device-" + Guid.NewGuid().ToString("N"), "Asset owner",
            TokenHash("settlement-owner-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var matchId = Guid.NewGuid();
        var foreignEquipmentId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_wallets SET gold=0 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',29,'test','Running',$3)"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(Guid.NewGuid());
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Head','Blue',0,false,'InMatchBackpack',1,$3)"))
        {
            command.Parameters.AddWithValue(foreignEquipmentId);
            command.Parameters.AddWithValue(owner.UserId);
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, new MutableTimeProvider(now), metrics);
        using var details = JsonDocument.Parse("{}");
        var settlement = await repository.SettleAsync(matchId, player.UserId, "Extracted", details.RootElement,
            [new("Gold", "gold", false, 50),
                new("Equipment", foreignEquipmentId.ToString("D"), false)], cancellationToken);

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            repository.CommitHoldsAsync(settlement.SettlementId, cancellationToken));

        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", player.UserId));
        Assert.Equal(2L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'", settlement.SettlementId));
        Assert.Equal(owner.UserId, await database.ScalarAsync<Guid>(
            "SELECT owner_id FROM equipments WHERE instance_id=$1", foreignEquipmentId));
        Assert.Equal("InMatchBackpack", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", foreignEquipmentId));
        Assert.Empty(await repository.GetReadyNotificationsAsync(player.UserId, cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Death_settlement_moves_worn_equipment_to_relic_and_clears_loadout()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var now = new DateTimeOffset(2026, 9, 7, 5, 0, 0, TimeSpan.Zero);
        var cancellationToken = TestContext.Current.CancellationToken;
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "settlement-death-device-" + Guid.NewGuid().ToString("N"), "Death player",
            TokenHash("settlement-death-token-" + Guid.NewGuid().ToString("N")), now, now.AddHours(1), cancellationToken);
        var equipmentId = await database.InsertWornFeetAsync(player.UserId, HeroClass.Priest, cancellationToken);
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE player_consumables SET advanced_bag_count=1 WHERE player_id=$1"))
        {
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1"))
        {
            command.Parameters.AddWithValue(equipmentId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        var matchId = Guid.NewGuid();
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',31,'test','Running',$3)"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(Guid.NewGuid());
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(player.UserId);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, new MutableTimeProvider(now), metrics);
        using var details = JsonDocument.Parse("{}");
        var settlement = await repository.SettleAsync(matchId, player.UserId, "Dead", details.RootElement,
            [new("Equipment", equipmentId.ToString("D"), false, Destination: "RelicPile"),
                new("Backpack", "Advanced", false)], cancellationToken);

        Assert.Equal(2, await repository.CommitHoldsAsync(settlement.SettlementId, cancellationToken));
        Assert.Equal("RelicPile", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_loadouts WHERE feet_id=$1", equipmentId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_loadouts WHERE player_id=$1 AND hero_class=1 AND feet_id IS NOT NULL", player.UserId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason='settlement.death'", equipmentId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT advanced_bag_count FROM player_consumables WHERE player_id=$1", player.UserId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Running_room_restart_restores_actor_and_compensates_snapshot_downtime()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 7, 6, 0, 0, TimeSpan.Zero));
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        var playerId = Guid.NewGuid();
        const int seed = 73;

        await using (var command = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',$3,'test','Running',$4)"))
        {
            command.Parameters.AddWithValue(matchId);
            command.Parameters.AddWithValue(roomId);
            command.Parameters.AddWithValue(seed);
            command.Parameters.AddWithValue(time.GetUtcNow());
            await command.ExecuteNonQueryAsync(cancellationToken);
        }

        var room = new BattleRoom(roomId, "test", CombatCardCatalog.CreatePrototype(), seed);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null));
        room.MarkPlayerDisconnected(playerId);
        var beforeRestart = room.Capture();
        await snapshots.SaveIfDueAsync(beforeRestart, cancellationToken);

        time.Advance(TimeSpan.FromSeconds(16));
        var recoveryState = new RoomRecoveryState();
        await using var recoveredRooms = new RoomRegistry(
            time,
            snapshotRepository: snapshots,
            persistenceState: new RoomPersistenceState(),
            metrics: metrics,
            logger: NullLogger<RoomRegistry>.Instance);
        var worker = new RoomRecoveryWorker(
            snapshots,
            recoveredRooms,
            recoveryState,
            time,
            NullLogger<RoomRecoveryWorker>.Instance);

        await worker.StartAsync(cancellationToken);

        Assert.True(recoveryState.Capture().IsHealthy);
        Assert.True(recoveredRooms.TryGetForPlayer(playerId, out var actor, out var recoveredMatchId));
        Assert.Equal(matchId, recoveredMatchId);
        var recovered = await actor!.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
        Assert.Equal(RoomPlayerPhase.Dead, Assert.Single(recovered.Players).Phase);
        Assert.True(recovered.Elapsed >= beforeRestart.Elapsed + TimeSpan.FromSeconds(16));
        Assert.Equal(beforeRestart.RandomStreams, recovered.RandomStreams);

        var persisted = Assert.IsType<BattleRoomSnapshot>(await snapshots.GetAsync(roomId, cancellationToken));
        Assert.Equal(RoomPlayerPhase.Dead, Assert.Single(persisted.Players).Phase);
        Assert.True(persisted.Elapsed >= beforeRestart.Elapsed + TimeSpan.FromSeconds(16));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task RoomActor_extraction_commits_settlement_and_removes_terminal_room()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 7, 7, 0, 0, TimeSpan.Zero));
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "room-settlement-device-" + Guid.NewGuid().ToString("N"),
            "Room settlement",
            TokenHash("room-settlement-token-" + Guid.NewGuid().ToString("N")),
            time.GetUtcNow(),
            time.GetUtcNow().AddHours(1),
            cancellationToken);
        await database.ExecuteAsync(
            "UPDATE player_wallets SET gold=0; UPDATE player_consumables SET health_potion_count=0;");
        var equipmentId = await database.InsertWornFeetAsync(player.UserId, HeroClass.Mage, cancellationToken);
        await using (var equipment = database.DataSource.CreateCommand(
            "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1"))
        {
            equipment.Parameters.AddWithValue(equipmentId);
            await equipment.ExecuteNonQueryAsync(cancellationToken);
        }

        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        const int seed = 97;
        await using (var match = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',$3,'test','Running',$4)"))
        {
            match.Parameters.AddWithValue(matchId);
            match.Parameters.AddWithValue(roomId);
            match.Parameters.AddWithValue(seed);
            match.Parameters.AddWithValue(time.GetUtcNow());
            await match.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var assignment = database.DataSource.CreateCommand(
            "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            assignment.Parameters.AddWithValue(matchId);
            assignment.Parameters.AddWithValue(player.UserId);
            await assignment.ExecuteNonQueryAsync(cancellationToken);
        }

        var draft = new BattleRoom(roomId, "test", CombatCardCatalog.CreatePrototype(), seed);
        var roomPlayer = draft.AddPlayer(new BattleRoomPlayerSetup(
            player.UserId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null,
            WornArmor: [new(equipmentId.ToString("D"), ExplorationItemKind.Equipment)]));
        Assert.True(roomPlayer.Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 23)));
        Assert.True(roomPlayer.Inventory.TryAdd(new("health_potion:1", ExplorationItemKind.HealthPotion)));
        draft.InitializeMap(ChaosMapGenerator.Generate(seed, 1));
        var preparedSnapshot = draft.Capture();
        var evacuation = preparedSnapshot.Map!.Cells.First(cell => cell.HasEvacuation).Position;
        preparedSnapshot = preparedSnapshot with
        {
            Players = preparedSnapshot.Players.Select(value => value with
            {
                Position = evacuation,
                Phase = RoomPlayerPhase.ActionBar,
                Pve = null
            }).ToArray()
        };
        var room = BattleRoom.Restore(preparedSnapshot, CombatCardCatalog.CreatePrototype(), seed);

        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, time, metrics);
        var coordinator = new SettlementCoordinator(repository);
        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        var eventStore = new RealtimeEventStore(time);
        var connections = new ConnectionRegistry();
        await using var rooms = new RoomRegistry(
            time,
            coordinator,
            snapshots,
            new RoomPersistenceState(),
            metrics,
            NullLogger<RoomRegistry>.Instance,
            eventStore,
            connections);
        var actor = rooms.Register(room, matchId, startTicker: false);

        var extraction = await actor.ExecuteAsync(
            new RequestRoomExtractionCommand(player.UserId), cancellationToken);
        Assert.Equal(TimeSpan.FromSeconds(3), extraction.Remaining);
        await actor.ExecuteAsync(
            new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(3), time.GetUtcNow().AddSeconds(3)),
            cancellationToken);
        var terminal = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
        Assert.Equal(RoomPlayerPhase.Extracted, Assert.Single(terminal.Players).Phase);
        // Actor command completion precedes the asynchronous persistence observer.
        await database.WaitForScalarAsync(1L,
            "SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId);
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
        Assert.Equal(3L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM settlement_asset_holds h JOIN match_settlements s ON s.settlement_id=h.settlement_id WHERE s.match_id=$1 AND h.state='Pending'", matchId));

        using var worker = new SettlementWorker(
            repository,
            new SettlementEventPublisher(repository, eventStore, connections),
            rooms,
            new SettlementRecoveryState(),
            metrics,
            NullLogger<SettlementWorker>.Instance);
        Assert.Equal(1, await worker.ProcessNextAsync(cancellationToken));

        Assert.False(rooms.ContainsRoom(roomId));
        Assert.False(rooms.TryGetForPlayer(player.UserId, out _));
        Assert.Equal("Completed", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", matchId));
        Assert.Equal("Settled", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE match_id=$1", matchId));
        Assert.Equal(23L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(1, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal("Equipped", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM settlement_asset_holds h JOIN match_settlements s ON s.settlement_id=h.settlement_id WHERE s.match_id=$1 AND h.state='Pending'", matchId));
        Assert.Single(await repository.GetReadyNotificationsAsync(player.UserId, cancellationToken));
        Assert.Equal(0, await worker.ProcessNextAsync(cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task RoomActor_death_preserves_safe_assets_and_moves_losses_to_relic()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 7, 8, 0, 0, TimeSpan.Zero));
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "room-death-device-" + Guid.NewGuid().ToString("N"),
            "Room death",
            TokenHash("room-death-token-" + Guid.NewGuid().ToString("N")),
            time.GetUtcNow(),
            time.GetUtcNow().AddHours(1),
            cancellationToken);
        await database.ExecuteAsync(
            "UPDATE player_wallets SET gold=0; UPDATE player_consumables SET health_potion_count=0,advanced_bag_count=1;");
        var wornEquipmentId = await database.InsertWornFeetAsync(player.UserId, HeroClass.Mage, cancellationToken);
        await using (var equipment = database.DataSource.CreateCommand(
            "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1"))
        {
            equipment.Parameters.AddWithValue(wornEquipmentId);
            await equipment.ExecuteNonQueryAsync(cancellationToken);
        }
        var backpackEquipmentId = Guid.NewGuid();
        await using (var equipment = database.DataSource.CreateCommand(
            "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES($1,$2,'Head','Blue',1,false,'InMatchBackpack',1,$3)"))
        {
            equipment.Parameters.AddWithValue(backpackEquipmentId);
            equipment.Parameters.AddWithValue(player.UserId);
            equipment.Parameters.AddWithValue(time.GetUtcNow());
            await equipment.ExecuteNonQueryAsync(cancellationToken);
        }

        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        const int seed = 101;
        await using (var match = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',$3,'test','Running',$4)"))
        {
            match.Parameters.AddWithValue(matchId);
            match.Parameters.AddWithValue(roomId);
            match.Parameters.AddWithValue(seed);
            match.Parameters.AddWithValue(time.GetUtcNow());
            await match.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var assignment = database.DataSource.CreateCommand(
            "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            assignment.Parameters.AddWithValue(matchId);
            assignment.Parameters.AddWithValue(player.UserId);
            await assignment.ExecuteNonQueryAsync(cancellationToken);
        }

        var room = new BattleRoom(roomId, "test", CombatCardCatalog.CreatePrototype(), seed);
        var roomPlayer = room.AddPlayer(new BattleRoomPlayerSetup(
            player.UserId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null,
            InventoryCapacity: 28,
            SafeSlots: 1,
            WornArmor: [new(wornEquipmentId.ToString("D"), ExplorationItemKind.Equipment)]));
        Assert.True(roomPlayer.Inventory.TryAdd(new("safe-gold", ExplorationItemKind.Gold, 11, IsSafe: true)));
        Assert.True(roomPlayer.Inventory.TryAdd(new("unsafe-gold", ExplorationItemKind.Gold, 29)));
        Assert.True(roomPlayer.Inventory.TryAdd(new("health_potion:1", ExplorationItemKind.HealthPotion)));
        Assert.True(roomPlayer.Inventory.TryAdd(new(
            backpackEquipmentId.ToString("D"), ExplorationItemKind.Equipment)));
        room.InitializeMap(ChaosMapGenerator.Generate(seed, 1));

        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, time, metrics);
        var coordinator = new SettlementCoordinator(repository);
        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        var eventStore = new RealtimeEventStore(time);
        var connections = new ConnectionRegistry();
        await using var rooms = new RoomRegistry(
            time,
            coordinator,
            snapshots,
            new RoomPersistenceState(),
            metrics,
            NullLogger<RoomRegistry>.Instance,
            eventStore,
            connections);
        var actor = rooms.Register(room, matchId, startTicker: false);

        await actor.ExecuteAsync(new SetPlayerConnectionCommand(player.UserId, Connected: false), cancellationToken);
        await actor.ExecuteAsync(
            new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(15), time.GetUtcNow().AddSeconds(15)),
            cancellationToken);
        var terminal = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
        var dead = Assert.Single(terminal.Players);
        Assert.Equal(RoomPlayerPhase.Dead, dead.Phase);
        Assert.Equal("safe-gold", Assert.Single(dead.Inventory!.Items).ItemId);
        var relic = Assert.Single(terminal.RelicPiles!);
        Assert.Equal(4, relic.Items.Count);
        Assert.Contains(relic.Items, item => item.ItemId == "unsafe-gold");
        Assert.Contains(relic.Items, item => item.ItemId == "health_potion:1");
        Assert.Contains(relic.Items, item => item.ItemId == backpackEquipmentId.ToString("D"));
        Assert.Contains(relic.Items, item => item.ItemId == wornEquipmentId.ToString("D"));

        // Actor command completion precedes the asynchronous persistence observer.
        await database.WaitForScalarAsync(1L,
            "SELECT count(*) FROM match_settlements WHERE match_id=$1 AND result='Dead'", matchId);
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_settlements WHERE match_id=$1 AND result='Dead'", matchId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM settlement_asset_holds h JOIN match_settlements s ON s.settlement_id=h.settlement_id WHERE s.match_id=$1 AND h.state='Pending'", matchId));
        using var worker = new SettlementWorker(
            repository,
            new SettlementEventPublisher(repository, eventStore, connections),
            rooms,
            new SettlementRecoveryState(),
            metrics,
            NullLogger<SettlementWorker>.Instance);

        Assert.Equal(1, await worker.ProcessNextAsync(cancellationToken));

        Assert.Equal(11L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT advanced_bag_count FROM player_consumables WHERE player_id=$1", player.UserId));
        Assert.Equal("RelicPile", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", wornEquipmentId));
        Assert.Equal("RelicPile", await database.ScalarAsync<string>(
            "SELECT location FROM equipments WHERE instance_id=$1", backpackEquipmentId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_loadouts WHERE feet_id=$1", wornEquipmentId));
        Assert.Equal(2L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='settlement.death'", player.UserId));
        Assert.False(rooms.ContainsRoom(roomId));
        Assert.Single(await repository.GetReadyNotificationsAsync(player.UserId, cancellationToken));
        Assert.Equal(0, await worker.ProcessNextAsync(cancellationToken));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Settlement_worker_restart_recovers_pending_holds_exactly_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 7, 9, 0, 0, TimeSpan.Zero));
        var player = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
            "settlement-restart-device-" + Guid.NewGuid().ToString("N"),
            "Restart settle",
            TokenHash("settlement-restart-token-" + Guid.NewGuid().ToString("N")),
            time.GetUtcNow(),
            time.GetUtcNow().AddHours(1),
            cancellationToken);
        await database.ExecuteAsync("UPDATE player_wallets SET gold=0;");
        var matchId = Guid.NewGuid();
        await using (var match = database.DataSource.CreateCommand(
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',109,'test','Running',$3)"))
        {
            match.Parameters.AddWithValue(matchId);
            match.Parameters.AddWithValue(Guid.NewGuid());
            match.Parameters.AddWithValue(time.GetUtcNow());
            await match.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var assignment = database.DataSource.CreateCommand(
            "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {
            assignment.Parameters.AddWithValue(matchId);
            assignment.Parameters.AddWithValue(player.UserId);
            await assignment.ExecuteNonQueryAsync(cancellationToken);
        }

        using var firstMetrics = new ServerMetrics();
        var firstRepository = new SettlementRepository(database.DataSource, time, firstMetrics);
        using var details = JsonDocument.Parse("{\"source\":\"restart-test\"}");
        var settlement = await firstRepository.SettleAsync(
            matchId,
            player.UserId,
            "Extracted",
            details.RootElement,
            [new("Gold", "gold", false, 37)],
            cancellationToken);
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'", settlement.SettlementId));
        var progression = new ProgressionRepository(database.DataSource);
        var bootstrapRepository = CreateBootstrapRepository(database.DataSource, progression, time);
        Assert.Null((await bootstrapRepository.GetAsync(player, cancellationToken)).UnfinishedSettlement);
        await Assert.ThrowsAsync<SettlementNotReadyException>(() => firstRepository.AcknowledgeAsync(
            player.UserId, settlement.SettlementId, "settlement-pending", cancellationToken));

        using var recoveredMetrics = new ServerMetrics();
        var recoveredRepository = new SettlementRepository(database.DataSource, time, recoveredMetrics);
        await using var recoveredRooms = new RoomRegistry(time);
        var recoveredState = new SettlementRecoveryState();
        using var recoveredWorker = new SettlementWorker(
            recoveredRepository,
            new SettlementEventPublisher(recoveredRepository, new RealtimeEventStore(time), new ConnectionRegistry()),
            recoveredRooms,
            recoveredState,
            recoveredMetrics,
            NullLogger<SettlementWorker>.Instance);

        Assert.Equal(1, await recoveredWorker.ProcessNextAsync(cancellationToken));
        Assert.True(recoveredState.Capture().IsHealthy);
        Assert.Equal(37L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal("Committed", await database.ScalarAsync<string>(
            "SELECT state FROM settlement_asset_holds WHERE settlement_id=$1", settlement.SettlementId));
        Assert.Single(await recoveredRepository.GetReadyNotificationsAsync(player.UserId, cancellationToken));
        var unfinishedSettlement = Assert.IsType<SettlementResponse>(
            (await bootstrapRepository.GetAsync(player, cancellationToken)).UnfinishedSettlement);
        Assert.Equal(settlement.SettlementId, unfinishedSettlement.SettlementId);
        Assert.Equal(matchId, unfinishedSettlement.MatchId);
        Assert.Equal("Extracted", unfinishedSettlement.Result);

        var acknowledgement = await recoveredRepository.AcknowledgeAsync(
            player.UserId, settlement.SettlementId, "settlement-acknowledge", cancellationToken);
        time.Advance(TimeSpan.FromMinutes(1));
        var acknowledgementReplay = await recoveredRepository.AcknowledgeAsync(
            player.UserId, settlement.SettlementId, "settlement-acknowledge", cancellationToken);
        Assert.Equal(acknowledgement, acknowledgementReplay);
        Assert.Null((await bootstrapRepository.GetAsync(player, cancellationToken)).UnfinishedSettlement);
        await Assert.ThrowsAsync<SettlementNotFoundException>(() => recoveredRepository.AcknowledgeAsync(
            Guid.NewGuid(), settlement.SettlementId, "settlement-other-player", cancellationToken));

        using var secondRestartMetrics = new ServerMetrics();
        var secondRestartRepository = new SettlementRepository(database.DataSource, time, secondRestartMetrics);
        await using var secondRestartRooms = new RoomRegistry(time);
        var secondRestartState = new SettlementRecoveryState();
        using var secondRestartWorker = new SettlementWorker(
            secondRestartRepository,
            new SettlementEventPublisher(secondRestartRepository, new RealtimeEventStore(time), new ConnectionRegistry()),
            secondRestartRooms,
            secondRestartState,
            secondRestartMetrics,
            NullLogger<SettlementWorker>.Instance);

        Assert.Equal(0, await secondRestartWorker.ProcessNextAsync(cancellationToken));
        Assert.True(secondRestartState.Capture().IsHealthy);
        Assert.Equal(37L, await database.ScalarAsync<long>(
            "SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", player.UserId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Four_humans_enqueue_ready_and_launch_one_persisted_room()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 7, 1, 0, 0, TimeSpan.Zero));
        using var metrics = new ServerMetrics();
        var matchmaking = new MatchmakingRepository(database.DataSource, time, metrics);
        var players = new List<(Guid PlayerId, Guid PreparationId, MatchTicketResponse Ticket)>();

        for (var index = 0; index < 4; index++)
        {
            var prepared = await CreatePreparedPlayerAsync(index);
            var ticket = await matchmaking.EnqueueAsync(
                prepared.PlayerId,
                $"match-enqueue-{index}",
                new(prepared.PreparationId),
                cancellationToken);
            players.Add((prepared.PlayerId, prepared.PreparationId, ticket));

            if (index == 0)
            {
                // A former match for this player must not leak into a queued ticket replay.
                var historicalMatchId = Guid.NewGuid();
                await using (var historicalMatch = database.DataSource.CreateCommand(
                    "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',0,$3,'Completed',$4)"))
                {
                    historicalMatch.Parameters.AddWithValue(historicalMatchId);
                    historicalMatch.Parameters.AddWithValue(Guid.NewGuid());
                    historicalMatch.Parameters.AddWithValue(BootstrapRepository.CurrentConfigVersion);
                    historicalMatch.Parameters.AddWithValue(time.GetUtcNow());
                    await historicalMatch.ExecuteNonQueryAsync(cancellationToken);
                }
                await using (var historicalPlayer = database.DataSource.CreateCommand(
                    "INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Settled')"))
                {
                    historicalPlayer.Parameters.AddWithValue(historicalMatchId);
                    historicalPlayer.Parameters.AddWithValue(prepared.PlayerId);
                    historicalPlayer.Parameters.AddWithValue(Guid.NewGuid());
                    await historicalPlayer.ExecuteNonQueryAsync(cancellationToken);
                }
                Assert.Null(await matchmaking.TryCreateMatchAsync(cancellationToken));
                Assert.Equal(ticket, await matchmaking.EnqueueAsync(
                    prepared.PlayerId, "match-enqueue-0", new(prepared.PreparationId), cancellationToken));
                await Assert.ThrowsAsync<IdempotencyConflictException>(() => matchmaking.EnqueueAsync(
                    prepared.PlayerId, "match-enqueue-0", new(Guid.NewGuid()), cancellationToken));
            }
        }

        var pending = Assert.IsType<PendingMatch>(await matchmaking.TryCreateMatchAsync(cancellationToken));
        Assert.Equal(pending.MatchId, (await matchmaking.EnqueueAsync(
            players[0].PlayerId, "match-enqueue-0", new(players[0].PreparationId), cancellationToken)).MatchId);
        Assert.Equal(4, pending.PlayerIds.Count);
        foreach (var player in players)
        {
            var ready = await matchmaking.MarkReadyAsync(player.PlayerId, time.GetUtcNow(), cancellationToken);
            Assert.True(ready.IsReady);
        }

        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        await using var rooms = new RoomRegistry(time);
        using var coordinator = new RoomReadyCoordinator(
            matchmaking,
            rooms,
            snapshots,
            new RealtimeEventStore(time),
            new ConnectionRegistry(),
            time,
            NullLogger<RoomReadyCoordinator>.Instance);

        Assert.True(await coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
        Assert.True(rooms.ContainsRoom(pending.RoomId));
        var snapshot = await snapshots.GetAsync(pending.RoomId, cancellationToken);
        Assert.NotNull(snapshot);
        Assert.Equal(4, snapshot.Players.Count);
        Assert.Equal("Running", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_players WHERE match_id=$1 AND is_bot=false AND state='Active'", pending.MatchId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_tickets WHERE status='Matched' AND ticket_id IN (SELECT ticket_id FROM match_tickets t JOIN match_players p ON p.player_id=t.player_id AND p.preparation_id=t.preparation_id WHERE p.match_id=$1)", pending.MatchId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM preparations p JOIN match_players mp ON mp.preparation_id=p.preparation_id WHERE mp.match_id=$1 AND p.status='Matched'", pending.MatchId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM equipments e JOIN preparation_assets pa ON pa.asset_id=e.instance_id::text JOIN match_players mp ON mp.preparation_id=pa.preparation_id WHERE mp.match_id=$1 AND pa.asset_type='Equipment' AND e.location='InMatchEquipped'", pending.MatchId));
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM inventory_movements WHERE request_id=$1 AND reason='match.start'", pending.MatchId.ToString("D")));
        Assert.Equal(0, await database.ScalarAsync<int>(
            "SELECT health_potion_count FROM player_consumables WHERE player_id=$1", players[0].PlayerId));
        Assert.Equal(1, await database.ScalarAsync<int>(
            "SELECT advanced_bag_count FROM player_consumables WHERE player_id=$1", players[0].PlayerId));
        Assert.Equal(28, snapshot.Players.Single(value => value.PlayerId == players[0].PlayerId).Inventory!.Capacity);
        Assert.Equal(2, snapshot.Players.Single(value => value.PlayerId == players[0].PlayerId).Inventory!.Items.Count(
            item => item.Kind == ExplorationItemKind.HealthPotion));

        async Task<(Guid PlayerId, Guid PreparationId)> CreatePreparedPlayerAsync(int index)
        {
            var profile = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
                $"match-device-{index}-{Guid.NewGuid():N}",
                $"Match player {index}",
                TokenHash($"match-token-{index}-{Guid.NewGuid():N}"),
                time.GetUtcNow(),
                time.GetUtcNow().AddHours(1),
                cancellationToken);
            var progression = new ProgressionRepository(database.DataSource);
            var deck = Assert.Single(
                await progression.GetDecksAsync(profile.UserId, cancellationToken),
                value => value.HeroClass == HeroClassDto.Priest);
            await database.InsertWornFeetAsync(profile.UserId, HeroClass.Priest, cancellationToken);
            var loadout = Assert.IsType<LoadoutResponse>(
                await progression.GetLoadoutAsync(profile.UserId, HeroClass.Priest, cancellationToken));
            if (index == 0)
            {
                await using var consumables = database.DataSource.CreateCommand(
                    "UPDATE player_consumables SET health_potion_count=2,advanced_bag_count=1 WHERE player_id=$1");
                consumables.Parameters.AddWithValue(profile.UserId);
                await consumables.ExecuteNonQueryAsync(cancellationToken);
            }
            var preparation = await new PreparationRepository(database.DataSource, time).CreateAsync(
                profile.UserId,
                $"match-preparation-{index}",
                new(HeroClassDto.Priest, deck.Version, loadout.EquipmentIds,
                    index == 0 ? BackpackTierDto.Advanced : BackpackTierDto.Free,
                    index == 0 ? [0] : [], index == 0 ? 2 : 0, "Standard"),
                cancellationToken);
            Assert.Equal(CreatePreparationStatus.Created, preparation.Status);
            return (profile.UserId, preparation.Preparation!.PreparationId);
        }
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Match_timeout_removes_unready_human_and_fills_room_with_bots()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var cancellationToken = TestContext.Current.CancellationToken;
        var time = new MutableTimeProvider(new DateTimeOffset(2026, 9, 7, 2, 0, 0, TimeSpan.Zero));
        using var metrics = new ServerMetrics();
        var matchmaking = new MatchmakingRepository(database.DataSource, time, metrics);
        var preparedPlayers = new List<(Guid PlayerId, Guid PreparationId)>();
        var profiles = new List<PlayerProfile>();

        for (var index = 0; index < 2; index++)
        {
            var profile = await CreateIdentityRepository(database.DataSource).SignInLocalAsync(
                $"fallback-device-{index}-{Guid.NewGuid():N}",
                $"Fallback player {index}",
                TokenHash($"fallback-token-{index}-{Guid.NewGuid():N}"),
                time.GetUtcNow(),
                time.GetUtcNow().AddHours(1),
                cancellationToken);
            profiles.Add(profile);
            var progression = new ProgressionRepository(database.DataSource);
            var deck = Assert.Single(
                await progression.GetDecksAsync(profile.UserId, cancellationToken),
                value => value.HeroClass == HeroClassDto.Mage);
            await database.InsertWornFeetAsync(profile.UserId, HeroClass.Mage, cancellationToken);
            var loadout = Assert.IsType<LoadoutResponse>(
                await progression.GetLoadoutAsync(profile.UserId, HeroClass.Mage, cancellationToken));
            var preparation = await new PreparationRepository(database.DataSource, time).CreateAsync(
                profile.UserId,
                $"fallback-preparation-{index}",
                new(HeroClassDto.Mage, deck.Version, loadout.EquipmentIds,
                    BackpackTierDto.Free, [], 0, "Standard"),
                cancellationToken);
            Assert.Equal(CreatePreparationStatus.Created, preparation.Status);
            preparedPlayers.Add((profile.UserId, preparation.Preparation!.PreparationId));
            await matchmaking.EnqueueAsync(profile.UserId, $"fallback-enqueue-{index}",
                new(preparation.Preparation.PreparationId), cancellationToken);
        }

        Assert.Null(await matchmaking.TryCreateMatchAsync(cancellationToken));
        time.Advance(TimeSpan.FromSeconds(30));
        var pending = Assert.IsType<PendingMatch>(await matchmaking.TryCreateMatchAsync(cancellationToken));
        var readyPlayer = preparedPlayers[0];
        var removedPlayer = preparedPlayers[1];
        var bootstrapRepository = CreateBootstrapRepository(
            database.DataSource, new ProgressionRepository(database.DataSource), time);
        // Merely being assigned a seat must not force combat reconnection at login.
        Assert.Null((await bootstrapRepository.GetAsync(profiles[0], cancellationToken)).UnfinishedMatch);
        Assert.Null((await bootstrapRepository.GetAsync(profiles[1], cancellationToken)).UnfinishedMatch);
        await matchmaking.MarkReadyAsync(readyPlayer.PlayerId, time.GetUtcNow(), cancellationToken);
        Assert.Equal(pending.MatchId,
            (await bootstrapRepository.GetAsync(profiles[0], cancellationToken)).UnfinishedMatch?.MatchId);
        Assert.Null((await bootstrapRepository.GetAsync(profiles[1], cancellationToken)).UnfinishedMatch);
        time.Advance(TimeSpan.FromSeconds(15));

        var snapshots = new RoomSnapshotRepository(database.DataSource, time, metrics);
        await using var rooms = new RoomRegistry(time);
        using var coordinator = new RoomReadyCoordinator(
            matchmaking,
            rooms,
            snapshots,
            new RealtimeEventStore(time),
            new ConnectionRegistry(),
            time,
            NullLogger<RoomReadyCoordinator>.Instance);

        Assert.True(await coordinator.ProcessNextAsync(time.GetUtcNow(), cancellationToken));
        var snapshot = await snapshots.GetAsync(pending.RoomId, cancellationToken);
        Assert.NotNull(snapshot);
        Assert.Equal(4, snapshot.Players.Count);
        Assert.Contains(snapshot.Players, player => player.PlayerId == readyPlayer.PlayerId && !player.IsBot);
        Assert.DoesNotContain(snapshot.Players, player => player.PlayerId == removedPlayer.PlayerId);
        Assert.Equal(3, snapshot.Players.Count(player => player.IsBot));
        Assert.Equal("Running", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.Equal("Active", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE player_id=$1 AND is_bot=false", readyPlayer.PlayerId));
        Assert.Equal("Removed", await database.ScalarAsync<string>(
            "SELECT state FROM match_players WHERE player_id=$1 AND is_bot=false", removedPlayer.PlayerId));
        Assert.Equal("Matched", await database.ScalarAsync<string>(
            "SELECT status FROM preparations WHERE preparation_id=$1", readyPlayer.PreparationId));
        Assert.Equal("Cancelled", await database.ScalarAsync<string>(
            "SELECT status FROM preparations WHERE preparation_id=$1", removedPlayer.PreparationId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM equipments e JOIN preparation_assets pa ON pa.asset_id=e.instance_id::text WHERE pa.preparation_id=$1 AND e.location='InMatchEquipped'", readyPlayer.PreparationId));
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM equipments e JOIN preparation_assets pa ON pa.asset_id=e.instance_id::text WHERE pa.preparation_id=$1 AND e.location='Equipped'", removedPlayer.PreparationId));
        Assert.Equal(3L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_players WHERE match_id=$1 AND is_bot=true AND state='Active'", pending.MatchId));
        Assert.Equal(pending.MatchId,
            (await bootstrapRepository.GetAsync(profiles[0], cancellationToken)).UnfinishedMatch?.MatchId);
        var removedBootstrap = await bootstrapRepository.GetAsync(profiles[1], cancellationToken);
        Assert.Null(removedBootstrap.UnfinishedMatch);
        Assert.Null(removedBootstrap.ActivePreparation);
        Assert.Null(removedBootstrap.UnfinishedSettlement);
    }

    private static BootstrapRepository CreateBootstrapRepository(
        NpgsqlDataSource dataSource,
        ProgressionRepository progression,
        TimeProvider timeProvider) =>
        new(dataSource, progression, new EconomyRepository(dataSource, timeProvider),
            new MailRepository(dataSource, timeProvider),
            new PreparationRepository(dataSource, timeProvider), timeProvider);

    private static IdentityRepository CreateIdentityRepository(NpgsqlDataSource dataSource) =>
        new(dataSource, new PlayerProvisioningService());

    private static byte[] TokenHash(string value) => SHA256.HashData(Encoding.UTF8.GetBytes(value));

    private sealed class MutableTimeProvider(DateTimeOffset utcNow) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => utcNow;

        public void Advance(TimeSpan duration) => utcNow += duration;
    }

    private static async Task AssertProvisionedAggregateAsync(PostgresTestSchema database, Guid playerId)
    {
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM player_wallets WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM player_materials WHERE player_id=$1", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM player_consumables WHERE player_id=$1", playerId));
        Assert.Equal(220L, await database.ScalarAsync<long>("SELECT count(*) FROM player_cards WHERE player_id=$1", playerId));
        Assert.Equal(51L, await database.ScalarAsync<long>("SELECT count(*) FROM player_cards WHERE player_id=$1 AND unlocked", playerId));
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM player_decks WHERE player_id=$1", playerId));
        Assert.Equal(60L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_deck_cards dc JOIN player_decks d ON d.deck_id=dc.deck_id WHERE d.player_id=$1", playerId));
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM class_weapons WHERE player_id=$1", playerId));
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM player_loadouts WHERE player_id=$1", playerId));
        Assert.Equal(3L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_loadouts WHERE player_id=$1 AND feet_id IS NULL AND head_id IS NULL AND chest_id IS NULL AND hands_id IS NULL AND legs_id IS NULL", playerId));
        Assert.Equal(0L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM equipments WHERE owner_id=$1", playerId));
    }
}

internal sealed class PostgresTestSchema : IAsyncDisposable
{
    private readonly NpgsqlDataSource _admin;
    private readonly string _schema;

    private PostgresTestSchema(
        NpgsqlDataSource admin,
        NpgsqlDataSource dataSource,
        string schema,
        string connectionString)
    {
        _admin = admin;
        DataSource = dataSource;
        _schema = schema;
        ConnectionString = connectionString;
    }

    public NpgsqlDataSource DataSource { get; }
    public string ConnectionString { get; }

    public static async Task<PostgresTestSchema> CreateAsync(bool migrate)
    {
        var connectionString = Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")
            ?? throw new InvalidOperationException("FANTASYCARD_TEST_POSTGRES is not configured.");
        var schema = "fc_runtime_test_" + Guid.NewGuid().ToString("N");
        var admin = NpgsqlDataSource.Create(connectionString);
        await using (var command = admin.CreateCommand($"CREATE SCHEMA {schema}"))
            await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        var settings = new NpgsqlConnectionStringBuilder(connectionString) { SearchPath = schema };
        var database = new PostgresTestSchema(
            admin,
            NpgsqlDataSource.Create(settings.ConnectionString),
            schema,
            settings.ConnectionString);
        if (migrate) await database.MigrateAsync();
        return database;
    }

    public async Task MigrateAsync() => await new DatabaseMigrator(
        DataSource,
        NullLogger<DatabaseMigrator>.Instance).StartAsync(TestContext.Current.CancellationToken);

    public async Task ExecuteAsync(string sql)
    {
        await using var command = DataSource.CreateCommand(sql);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
    }

    public async Task<Guid> InsertWornFeetAsync(Guid playerId, HeroClass heroClass, CancellationToken cancellationToken)
    {
        var feetId = Guid.CreateVersion7();
        await using (var insert = DataSource.CreateCommand(
            """
            INSERT INTO equipments(
                instance_id, owner_id, slot, quality, level, is_bound, location, version, created_at,
                element, effect_affix, secondary_trait)
            VALUES ($1, $2, 'Feet', 'White', 0, false, 'Equipped', 1, CURRENT_TIMESTAMP, 'Fire', NULL, 'DrawInterval')
            """))
        {
            insert.Parameters.AddWithValue(feetId);
            insert.Parameters.AddWithValue(playerId);
            await insert.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var loadout = DataSource.CreateCommand(
            "UPDATE player_loadouts SET feet_id=$1, version=version+1 WHERE player_id=$2 AND hero_class=$3"))
        {
            loadout.Parameters.AddWithValue(feetId);
            loadout.Parameters.AddWithValue(playerId);
            loadout.Parameters.AddWithValue((short)heroClass);
            if (await loadout.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("The test loadout is missing.");
        }
        return feetId;
    }

    public async Task WaitForScalarAsync(long expected, string sql, params object[] parameters)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(10));
        long? actual = null;
        try
        {
            while (true)
            {
                await using var command = DataSource.CreateCommand(sql);
                foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter);
                actual = (long?)await command.ExecuteScalarAsync(timeout.Token);
                if (actual == expected) return;
                await Task.Delay(TimeSpan.FromMilliseconds(20), timeout.Token);
            }
        }
        catch (OperationCanceledException) when (!TestContext.Current.CancellationToken.IsCancellationRequested)
        {
            Assert.Fail($"Persistence did not reach expected scalar {expected} within 10 seconds; last value {actual}. Query: {sql}");
        }
    }

    public async Task<T> ScalarAsync<T>(string sql, params object[] parameters)
    {
        await using var command = DataSource.CreateCommand(sql);
        foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter);
        return (T)(await command.ExecuteScalarAsync(TestContext.Current.CancellationToken)
            ?? throw new InvalidOperationException("The scalar query returned null."));
    }

    public async ValueTask DisposeAsync()
    {
        await DataSource.DisposeAsync();
        await using var command = _admin.CreateCommand($"DROP SCHEMA {_schema} CASCADE");
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await command.ExecuteNonQueryAsync(timeout.Token);
        await _admin.DisposeAsync();
    }
}
