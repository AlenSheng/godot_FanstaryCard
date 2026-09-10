using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Settlement;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresRoomEquipmentTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Extraction_applies_worn_reward_unequipped_armor_and_recycling_in_one_replay_safe_transaction()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var match = await CreateMatchAsync(database, player);
        var oldHead = await AddHeldArmorAsync(database, player, "Head", 3, true);
        var oldChest = await AddHeldArmorAsync(database, player, "Chest", 2, false);
        var feet = await HoldStarterFeetAsync(database, player);
        await ExecuteAsync(database, "UPDATE player_loadouts SET head_id=$1,chest_id=$2 WHERE player_id=$3 AND hero_class=2", oldHead, oldChest, player);
        var reward = Guid.NewGuid();
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, TimeProvider.System, metrics);
        using var details = JsonDocument.Parse("{\"heroClass\":\"Mage\"}");
        SettlementAsset[] assets =
        [
            new("Equipment", oldHead.ToString("D"), true, Destination: "Inventory"),
            new("Equipment", oldChest.ToString("D"), false, Destination: "Recycled"),
            new("Equipment", feet.ToString("D"), false, Destination: "Equipped"),
            new("Equipment", reward.ToString("D"), false,
                Equipment: new("Head", "Blue", "Water", null, "DrawInterval"), Destination: "Equipped")
        ];
        var settlement = await repository.SettleAsync(match, player, "Extracted", details.RootElement, assets, ct);

        Assert.Equal(4, await repository.CommitHoldsAsync(settlement.SettlementId, ct));
        Assert.Equal(0, await repository.CommitHoldsAsync(settlement.SettlementId, ct));

        Assert.Equal("Inventory", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", oldHead));
        Assert.Equal(3, await database.ScalarAsync<int>("SELECT level FROM equipments WHERE instance_id=$1", oldHead));
        Assert.True(await database.ScalarAsync<bool>("SELECT is_bound FROM equipments WHERE instance_id=$1", oldHead));
        Assert.Equal("Recycled", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", oldChest));
        Assert.Equal("Equipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", reward));
        Assert.Equal(reward, await database.ScalarAsync<Guid>("SELECT head_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player));
        Assert.True(await database.ScalarAsync<bool>("SELECT chest_id IS NULL FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player));
        Assert.Equal(feet, await database.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player));
        Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1", player));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'", settlement.SettlementId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Looter_cannot_create_the_victims_pending_reward_and_can_equip_it_after_custody_commits()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var victim = await CreatePlayerAsync(database);
        var looter = await CreatePlayerAsync(database);
        var match = await CreateMatchAsync(database, victim, looter);
        var oldFeet = await HoldStarterFeetAsync(database, looter);
        var equipmentId = Guid.NewGuid();
        var attributes = new EquipmentRewardData("Feet", "Purple", "Wood", "Vitality", "DrawInterval");
        using var metrics = new ServerMetrics();
        var clock = new TestClock(DateTimeOffset.UtcNow);
        var repository = new SettlementRepository(database.DataSource, clock, metrics);
        using var details = JsonDocument.Parse("{\"heroClass\":\"Mage\"}");
        var death = await repository.SettleAsync(match, victim, "Dead", details.RootElement,
            [new("Equipment", equipmentId.ToString("D"), false, Equipment: attributes, Destination: "RelicPile")], ct);
        clock.Now = clock.Now.AddSeconds(1);
        var extraction = await repository.SettleAsync(match, looter, "Extracted", details.RootElement,
            [new("Equipment", equipmentId.ToString("D"), false, Equipment: attributes, Destination: "Equipped"),
             new("Equipment", oldFeet.ToString("D"), false, Destination: "Inventory")], ct);

        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.CommitHoldsAsync(extraction.SettlementId, ct));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1, await repository.CommitHoldsAsync(death.SettlementId, ct));
        Assert.Equal(2, await repository.CommitHoldsAsync(extraction.SettlementId, ct));

        Assert.Equal(looter, await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal("Equipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(equipmentId, await database.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", looter));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(0, await repository.CommitHoldsAsync(extraction.SettlementId, ct));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Invalid_final_loadout_rolls_back_generated_equipment_gold_and_all_holds()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var match = await CreateMatchAsync(database, player);
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, TimeProvider.System, metrics);
        using var details = JsonDocument.Parse("{\"heroClass\":\"Mage\"}");
        var settlement = await repository.SettleAsync(match, player, "Extracted", details.RootElement,
            [new("Gold", "gold", false, 15),
             new("Equipment", first.ToString("D"), false, Equipment: new("Head", "Blue", "Fire", null, "DrawInterval"), Destination: "Equipped"),
             new("Equipment", second.ToString("D"), false, Equipment: new("Head", "Green", "Fire", null, "DrawInterval"), Destination: "Equipped")], ct);

        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.CommitHoldsAsync(settlement.SettlementId, ct));

        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=ANY($1)", new[] { first, second }));
        Assert.Equal(3L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'", settlement.SettlementId));
    }

    private static async Task<Guid> CreatePlayerAsync(PostgresTestSchema database)
    {
        var now = DateTimeOffset.UtcNow;
        return (await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Inventory player", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1),
            TestContext.Current.CancellationToken)).UserId;
    }

    private static async Task<Guid> CreateMatchAsync(PostgresTestSchema database, params Guid[] players)
    {
        var match = Guid.NewGuid();
        await ExecuteAsync(database,
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',11,'test','Running',CURRENT_TIMESTAMP)",
            match, Guid.NewGuid());
        foreach (var player in players)
            await ExecuteAsync(database, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", match, player);
        return match;
    }

    private static async Task<Guid> AddHeldArmorAsync(PostgresTestSchema database, Guid player, string slot, int level, bool bound)
    {
        var id = Guid.NewGuid();
        await ExecuteAsync(database,
            "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait) VALUES($1,$2,$3,'White',$4,$5,'InMatchEquipped',1,CURRENT_TIMESTAMP,'Fire',NULL,'DrawInterval')",
            id, player, slot, level, bound);
        return id;
    }

    private static async Task<Guid> HoldStarterFeetAsync(PostgresTestSchema database, Guid player)
    {
        var feet = await database.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2", player);
        await ExecuteAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", feet);
        return feet;
    }

    private static async Task ExecuteAsync(PostgresTestSchema database, string sql, params object[] values)
    {
        await using var command = database.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
    }

    private sealed class TestClock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
