using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonSettlementTests
{
    private static async Task<PostgresTestSchema> IdentitySchemaAsync()
    {
        var db = await PostgresTestSchema.CreateAsync(migrate: false);
        try
        {
            var output = Environment.GetEnvironmentVariable("FANTASYCARD_LOOT_ID_SCHEMA_EVIDENCE");
            if (output is not null)
                File.AppendAllText(output, JsonSerializer.Serialize(new { schema = new Npgsql.NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath }) + Environment.NewLine);
            await db.MigrateAsync();
            return db;
        }
        catch { await db.DisposeAsync(); throw; }
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task SameSeedRoomRewardsCommitToTwoOwnersInOneSchemaAndReplayAfterRepositoryRestart()
    {
        await using var db = await IdentitySchemaAsync();
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var first = await SetupAsync(db, clock, definition); var second = await SetupAsync(db, clock, definition);
        var a = IdentityReward(first, bindRoom: true); var b = IdentityReward(second, bindRoom: true);
        Assert.Equal(a.Equipment, b.Equipment); Assert.NotEqual(a.ItemId, b.ItemId);
        SettlementAsset[] assetsA = [new("Equipment", a.ItemId, false, Equipment: a.Equipment), new("Gold", "gold", false, 17)];
        SettlementAsset[] assetsB = [new("Equipment", b.ItemId, false, Equipment: b.Equipment), new("Gold", "gold", false, 17)];
        using var metrics = new ServerMetrics(); var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var receipts = await Task.WhenAll(SettleAsync(repository, first, assetsA), SettleAsync(repository, second, assetsB));
        var committed = await Task.WhenAll(receipts.Select(x => repository.CommitHoldsAsync(x.SettlementId, Ct)));
        Assert.All(committed, x => Assert.Equal(2, x));
        var restarted = new SettlementRepository(db.DataSource, clock, metrics);
        Assert.Equal(receipts[0].SettlementId, (await SettleAsync(restarted, first, assetsA)).SettlementId);
        Assert.Equal(receipts[1].SettlementId, (await SettleAsync(restarted, second, assetsB)).SettlementId);
        foreach (var receipt in receipts) Assert.Equal(0, await restarted.CommitHoldsAsync(receipt.SettlementId, Ct));
        foreach (var (fixture, item) in new[] { (first, a), (second, b) })
        {
            var id = Guid.Parse(item.ItemId);
            Assert.Equal(fixture.Player, await db.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", id));
            Assert.Equal(fixture.Match, await db.ScalarAsync<Guid>("SELECT source_match_id FROM equipments WHERE instance_id=$1", id));
            Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", id));
            Assert.Equal(1L, await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1", id));
            Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1", id));
            Assert.Equal(17L, await Balance(db, fixture.Player, definition.SeasonId, "gold"));
            Assert.Equal(100L, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", fixture.Player));
            Assert.Single(await restarted.GetReadyNotificationsAsync(fixture.Player, Ct));
        }
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM equipments"));
        Assert.Empty(await restarted.GetPendingHoldsAsync(Ct));
        WriteIdentityProof(new { scenario = "same-seed-two-owners-one-schema", first, second, a, b, receipts, committed, restart_replay = true, timed_routes = 0 });
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task PreUpgradeDuplicatePhysicalIdCannotStealAnOwnedItemOrPartiallyCommitTheSecondWallet()
    {
        await using var db = await IdentitySchemaAsync();
        var definition = Define(); var clock = new Clock(definition.StartsAtUtc);
        var first = await SetupAsync(db, clock, definition); var second = await SetupAsync(db, clock, definition);
        var a = IdentityReward(first, bindRoom: false); var b = IdentityReward(second, bindRoom: false);
        Assert.Equal(a.ItemId, b.ItemId); Assert.Equal(a.Equipment, b.Equipment);
        using var metrics = new ServerMetrics(); var repository = new SettlementRepository(db.DataSource, clock, metrics);
        var firstReceipt = await SettleAsync(repository, first, [new("Equipment", a.ItemId, false, Equipment: a.Equipment)]);
        Assert.Equal(1, await repository.CommitHoldsAsync(firstReceipt.SettlementId, Ct));
        var id = Guid.Parse(a.ItemId);
        var before = await db.ScalarAsync<string>("SELECT row_to_json(e)::text FROM equipments e WHERE instance_id=$1", id);
        var collision = await SettleAsync(repository, second, [new("Gold", "gold", false, 37), new("Equipment", b.ItemId, false, Equipment: b.Equipment)]);
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.CommitHoldsAsync(collision.SettlementId, Ct));
        Assert.Equal(before, await db.ScalarAsync<string>("SELECT row_to_json(e)::text FROM equipments e WHERE instance_id=$1", id));
        Assert.Equal(0L, await Balance(db, second.Player, definition.SeasonId, "gold"));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'", collision.SettlementId));
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1", id));
        Assert.Empty(await repository.GetReadyNotificationsAsync(second.Player, Ct));
        WriteIdentityProof(new { scenario = "pre-upgrade-duplicate-rejected", first, second, a, b, firstReceipt, collision,
            existing_owner_unchanged = true, second_wallet_rolled_back = true, auto_repair_claimed = false, timed_routes = 0 });
    }

    private static ExplorationItem IdentityReward(Fixture fixture, bool bindRoom) => RewardChoiceState.Create(ChaosMapLayer.Outer,
        new CombatRandom(73), configuration: GameConfigCatalog.Current, season: new SeasonRewardContext(fixture.Context, SeasonRewardBias.None),
        roomId: bindRoom ? fixture.Room : null).Options.Single(x => x.Kind == RewardChoiceKind.Equipment).Item!;

    private static void WriteIdentityProof<T>(T proof)
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_LOOT_ID_PG_PROOF_OUTPUT");
        if (output is not null) File.AppendAllText(output, JsonSerializer.Serialize(proof) + Environment.NewLine);
    }
}
