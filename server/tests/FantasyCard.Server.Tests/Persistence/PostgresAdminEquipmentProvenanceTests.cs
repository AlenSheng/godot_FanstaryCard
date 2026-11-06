using FantasyCard.Server.Admin;
using FantasyCard.Server.Realtime;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresAdminEquipmentProvenanceTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private const string Required = "Requires isolated PostgreSQL.";
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static AdminRepository Admin(PostgresTestSchema db, CraftingClock clock) =>
        new(db.DataSource, clock, new ConnectionRegistry(), new RealtimeEventStore(clock));

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task BulkGrantRecordsEachNewGuidWithoutChangingExistingItemsOrInventingSeasonContext()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        var existing = await CraftingTestInputs.ItemAsync(db, f, "Blue", effect: null, level: 3);
        var before = await db.ScalarAsync<string>("SELECT row_to_json(e)::text FROM equipments e WHERE instance_id=$1", existing);
        var admin = Admin(db, f.Clock);var result = (await admin.GrantAllEquipmentAsync(f.Player, "bulk", Ct))!;
        Assert.True(result.Equipment > 0);
        Assert.Equal(result.Equipment, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND request_id='bulk' AND reason='admin.grant_all_equipment'", f.Player));
        Assert.Equal(result.Equipment, await db.ScalarAsync<long>("""
            SELECT count(*) FROM inventory_movements m JOIN equipments e ON e.instance_id=m.item_id
            WHERE m.player_id=$1 AND m.request_id='bulk' AND m.source_kind='AdminGrant' AND m.from_location='Admin'
              AND m.to_location='Inventory' AND e.owner_id=m.player_id AND e.season_id IS NULL AND e.origin_season_id IS NULL
              AND m.season_id IS NULL AND m.difficulty_id IS NULL AND m.ruleset_id IS NULL
              AND m.config_version IS NULL AND m.stats_version IS NULL AND e.created_at=m.created_at
            """, f.Player));
        Assert.Equal(before, await db.ScalarAsync<string>("SELECT row_to_json(e)::text FROM equipments e WHERE instance_id=$1", existing));
        await Assert.ThrowsAsync<AdminConflictException>(() => admin.GrantAllEquipmentAsync(f.Player, "bulk", Ct));
        Assert.Equal(0, (await admin.GrantAllEquipmentAsync(f.Player, "new-bulk-key", Ct))!.Equipment);
        Assert.Equal(result.Equipment, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='admin.grant_all_equipment'", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task APerItemMovementFaultRollsBackEveryMintAndAuditThenTheSameRequestRetries()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        var before = await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", f.Player);
        await CraftingTestInputs.SqlAsync(db, """
            CREATE FUNCTION fail_bulk_grant_movement() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'declared bulk equipment movement failure'; END; $$;
            CREATE TRIGGER fail_bulk_grant_movement BEFORE INSERT ON inventory_movements
            FOR EACH ROW EXECUTE FUNCTION fail_bulk_grant_movement();
            """);
        var admin = Admin(db, f.Clock);
        await Assert.ThrowsAsync<PostgresException>(() => admin.GrantAllEquipmentAsync(f.Player, "rollback-bulk", Ct));
        Assert.Equal(before, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE request_id='rollback-bulk'"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM admin_audit WHERE request_id='rollback-bulk'"));
        await CraftingTestInputs.SqlAsync(db, "DROP TRIGGER fail_bulk_grant_movement ON inventory_movements");
        var result = (await admin.GrantAllEquipmentAsync(f.Player, "rollback-bulk", Ct))!;
        Assert.Equal(before + result.Equipment, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", f.Player));
        Assert.Equal(result.Equipment, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND request_id='rollback-bulk'", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task ParallelDifferentRequestsSerializeAndNeverMintTheSameSpecificationTwice()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        var admin = Admin(db, f.Clock);
        var results = await Task.WhenAll(admin.GrantAllEquipmentAsync(f.Player, "parallel-a", Ct), admin.GrantAllEquipmentAsync(f.Player, "parallel-b", Ct));
        Assert.Equal(1, results.Count(r => r!.Equipment > 0));
        Assert.Equal(results.Sum(r => r!.Equipment), await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='admin.grant_all_equipment'", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("""
            SELECT count(*) FROM (SELECT slot,quality,element FROM equipments WHERE owner_id=$1
                AND location IN ('Inventory','Equipped') GROUP BY slot,quality,element HAVING count(*)>1) duplicated
            """, f.Player));
    }
}
