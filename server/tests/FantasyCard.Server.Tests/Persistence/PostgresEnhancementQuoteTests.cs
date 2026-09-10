using System.Security.Cryptography;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresEnhancementQuoteTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Armor_quote_matches_actual_cost_and_counts_only_available_same_quality_materials()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var item = await CreateEquipmentAsync(database, player, "Purple", 3);
        var material = await CreateEquipmentAsync(database, player, "Purple", 0);
        await CreateEquipmentAsync(database, player, "Blue", 0);
        var repository = new ProgressionRepository(database.DataSource);
        var quote = (await repository.GetEquipmentEnhancementQuoteAsync(player, item, ct))!;
        Assert.Equal(256, quote.FragmentCost);
        Assert.Equal(4, quote.NextLevel);
        Assert.Equal(1, quote.MaterialCount);
        Assert.Equal("Purple", quote.MaterialQuality);
        Assert.Equal(1, quote.AvailableMaterialCount);
        Assert.False(quote.CanEnhance);
        await FundAsync(database, player, quote.FragmentCost);
        quote = (await repository.GetEquipmentEnhancementQuoteAsync(player, item, ct))!;
        Assert.True(quote.CanEnhance);
        var result = await repository.EnhanceEquipmentAsync(player, item, "quoted-fourth",
            new(quote.ExpectedVersion, material), ct);
        Assert.Equal(quote.NextLevel, result.Equipment.Level);
        Assert.Equal(0, result.EquipmentFragments);
        Assert.Equal(material, result.ConsumedMaterialEquipmentId);
        Assert.Null(await repository.GetEquipmentEnhancementQuoteAsync(Guid.NewGuid(), item, ct));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Class_weapon_quotes_never_require_a_material_and_cap_at_five()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        await FundAsync(database, player, 248);
        foreach (var cost in new[] { 8, 16, 32, 64, 128 })
        {
            var quote = (await repository.GetWeaponEnhancementQuoteAsync(player, HeroClass.Mage, ct))!;
            Assert.Equal(cost, quote.FragmentCost);
            Assert.True(quote.CanEnhance);
            Assert.Equal(0, quote.MaterialCount);
            Assert.Null(quote.MaterialQuality);
            var result = await repository.EnhanceWeaponAsync(player, HeroClass.Mage,
                "weapon-" + quote.NextLevel, quote.ExpectedVersion, ct);
            Assert.Equal(quote.NextLevel, result.Equipment.Level);
            Assert.Equal(quote.AvailableFragments - cost, result.EquipmentFragments);
        }
        var maximum = (await repository.GetWeaponEnhancementQuoteAsync(player, HeroClass.Mage, ct))!;
        Assert.False(maximum.CanEnhance);
        Assert.Null(maximum.NextLevel);
        Assert.Equal(0, maximum.FragmentCost);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Low_level_or_locked_equipment_cannot_consume_an_unrequested_material()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var otherPlayer = await CreatePlayerAsync(database);
        var item = await CreateEquipmentAsync(database, player, "White", 0);
        var otherItem = await CreateEquipmentAsync(database, otherPlayer, "Orange", 0);
        await FundAsync(database, player, 1000);
        var repository = new ProgressionRepository(database.DataSource);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.EnhanceEquipmentAsync(
            player, item, "invalid-extra-material", new(1, otherItem), ct));
        Assert.Equal("Inventory", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", otherItem));
        Assert.Equal(1000L, await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player));
        await using (var lockItem = database.DataSource.CreateCommand("UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1"))
        {
            lockItem.Parameters.AddWithValue(item);
            await lockItem.ExecuteNonQueryAsync(ct);
        }
        var quote = (await repository.GetEquipmentEnhancementQuoteAsync(player, item, ct))!;
        Assert.False(quote.CanEnhance);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.EnhanceEquipmentAsync(
            player, item, "locked-equipment", new(1), ct));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Market_list_projects_the_actual_equipment_attributes()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var item = await CreateEquipmentAsync(database, player, "Purple", 3);
        var market = new EconomyRepository(database.DataSource, TimeProvider.System);
        var listed = await market.ListAsync(player, "detailed-listing", new(item, 100), ct);
        var projected = Assert.Single(await market.GetMarketAsync(ct), listing => listing.ListingId == listed.ListingId);
        Assert.NotNull(projected.Equipment);
        Assert.Equal(item, projected.Equipment.InstanceId);
        Assert.Equal("Chest", projected.Equipment.Slot);
        Assert.Equal("Purple", projected.Equipment.Quality);
        Assert.Equal(3, projected.Equipment.Level);
        Assert.Equal("Fire", projected.Equipment.Element);
        Assert.Equal("DrawInterval", projected.Equipment.SecondaryTrait);
        Assert.Equal("MarketListed", projected.Equipment.Location);
        Assert.False(projected.Equipment.IsBound);
    }

    private static async Task<Guid> CreatePlayerAsync(PostgresTestSchema database)
    {
        var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Quote player", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1),
            TestContext.Current.CancellationToken);
        return player.UserId;
    }

    private static async Task<Guid> CreateEquipmentAsync(PostgresTestSchema database, Guid owner, string quality, int level)
    {
        var id = Guid.NewGuid();
        await using var command = database.DataSource.CreateCommand(
            """
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,secondary_trait)
            VALUES($1,$2,'Chest',$3,$4,false,'Inventory',1,CURRENT_TIMESTAMP,'Fire','DrawInterval')
            """);
        command.Parameters.AddWithValue(id);
        command.Parameters.AddWithValue(owner);
        command.Parameters.AddWithValue(quality);
        command.Parameters.AddWithValue(level);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        return id;
    }

    private static async Task FundAsync(PostgresTestSchema database, Guid player, long amount)
    {
        await using var command = database.DataSource.CreateCommand("UPDATE player_materials SET equipment_fragments=$1 WHERE player_id=$2");
        command.Parameters.AddWithValue(amount);
        command.Parameters.AddWithValue(player);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
    }
}
