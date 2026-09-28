using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresBootstrapBatchTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task All_result_sets_map_distinct_values_and_preserve_nullable_equipment_slots()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await PlayerAsync(db, ct);
        await Sql(db, "UPDATE player_wallets SET gold=12345,diamond=67 WHERE player_id=$1", ct, player.UserId);
        await Sql(db, "UPDATE player_materials SET warrior_soul=101,priest_soul=202,mage_soul=303,guardian_soul=404,equipment_fragments=505 WHERE player_id=$1", ct, player.UserId);
        await Sql(db, "UPDATE class_weapons SET level=hero_class,version=hero_class+10 WHERE player_id=$1", ct, player.UserId);
        var feet = await db.InsertWornFeetAsync(player.UserId, HeroClass.Mage, ct);
        var response = await Repository(db.DataSource).GetAsync(player, ct);
        Assert.Equal(new WalletResponse(12345, 67), response.Wallet);
        Assert.Equal(new MaterialsResponse(101, 202, 303, 404, 505), response.Materials);
        Assert.Equal(new[] { HeroClassDto.Priest, HeroClassDto.Mage, HeroClassDto.Guardian }, response.ClassWeapons.Select(value => value.HeroClass));
        Assert.All(response.ClassWeapons, value => { Assert.Equal((int)value.HeroClass, value.Level); Assert.Equal((int)value.HeroClass + 10, value.Version); });
        var mage = Assert.Single(response.EquippedLoadouts, value => value.HeroClass == HeroClassDto.Mage);
        Assert.Equal(new Guid?[] { null, null, null, null, feet }, mage.EquipmentIds);
        Assert.Equal(2, mage.Version);
        Assert.All(response.EquippedLoadouts.Where(value => value.HeroClass != HeroClassDto.Mage), value => Assert.All(value.EquipmentIds, id => Assert.Null(id)));
        Assert.Null(response.UnfinishedMatch);
        Assert.Null(response.UnfinishedSettlement);
        Assert.Equal(player.UserId, response.Player.UserId);
        Assert.NotEmpty(response.Cards);
        Assert.Equal(3, response.Decks.Count);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Optional_tail_result_sets_advance_correctly_and_filter_pending_acknowledged_and_other_players()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await PlayerAsync(db, ct);
        var repository = Repository(db.DataSource);
        var empty = await repository.GetAsync(player, ct);
        Assert.Null(empty.UnfinishedMatch);
        Assert.Null(empty.UnfinishedSettlement);
        var match = Guid.NewGuid(); var room = Guid.NewGuid(); var settlement = Guid.NewGuid(); var hold = Guid.NewGuid();
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',7,'batch-fixture','Running',now())", ct, match, room);
        await Sql(db, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", ct, match, player.UserId);
        await Sql(db, "INSERT INTO match_settlements(settlement_id,match_id,player_id,result,details_json,created_at) VALUES($1,$2,$3,'Extracted','{\"revision\":789}'::jsonb,now())", ct, settlement, match, player.UserId);
        var present = await repository.GetAsync(player, ct);
        Assert.Equal(match, present.UnfinishedMatch!.MatchId);
        Assert.Equal(room, present.UnfinishedMatch.RoomId);
        Assert.Equal("batch-fixture", present.UnfinishedMatch.ConfigVersion);
        Assert.Equal("Running", present.UnfinishedMatch.Status);
        Assert.Null(present.UnfinishedMatch.RoomRevision);
        Assert.Equal(settlement, present.UnfinishedSettlement!.SettlementId);
        Assert.Equal(789, present.UnfinishedSettlement.Details.GetProperty("revision").GetInt32());
        await Sql(db, "INSERT INTO room_snapshots(room_id,revision,snapshot_json,rng_state_json,updated_at) VALUES($1,987,'{}','{}',now())", ct, room);
        await Sql(db, "INSERT INTO settlement_asset_holds(hold_id,settlement_id,player_id,asset_kind,asset_ref,asset_snapshot,state,created_at) VALUES($1,$2,$3,'Gold','batch-gold','{}','Pending',now())", ct, hold, settlement, player.UserId);
        var pending = await repository.GetAsync(player, ct);
        Assert.Equal(987, pending.UnfinishedMatch!.RoomRevision);
        Assert.Null(pending.UnfinishedSettlement);
        await Sql(db, "UPDATE settlement_asset_holds SET state='Committed' WHERE hold_id=$1", ct, hold);
        Assert.Equal(settlement, (await repository.GetAsync(player, ct)).UnfinishedSettlement!.SettlementId);
        await Sql(db, "UPDATE match_settlements SET acknowledged_at=now() WHERE settlement_id=$1", ct, settlement);
        await Sql(db, "UPDATE matches SET status='Completed' WHERE match_id=$1", ct, match);
        var complete = await repository.GetAsync(player, ct);
        Assert.Null(complete.UnfinishedMatch);
        Assert.Null(complete.UnfinishedSettlement);
        var other = await PlayerAsync(db, ct);
        var isolated = await repository.GetAsync(other, ct);
        Assert.Null(isolated.UnfinishedMatch);
        Assert.Null(isolated.UnfinishedSettlement);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Cancelling_a_blocked_batch_releases_reader_and_small_pool_for_next_bootstrap()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await PlayerAsync(db, ct);
        var application = "bootstrap-batch-" + Guid.NewGuid().ToString("N");
        await using var source = NpgsqlDataSource.Create(new NpgsqlConnectionStringBuilder(db.ConnectionString)
        { Pooling = true, MaxPoolSize = 2, MinPoolSize = 0, ApplicationName = application, Timeout = 5 }.ConnectionString);
        await using var locker = await db.DataSource.OpenConnectionAsync(ct);
        await using var transaction = await locker.BeginTransactionAsync(ct);
        await using (var command = new NpgsqlCommand("LOCK TABLE player_wallets IN ACCESS EXCLUSIVE MODE", locker, transaction))
            await command.ExecuteNonQueryAsync(ct);
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(ct);
        var pending = Repository(source).GetAsync(player, cancellation.Token);
        using var observation = CancellationTokenSource.CreateLinkedTokenSource(ct);
        observation.CancelAfter(TimeSpan.FromSeconds(10));
        while (true)
        {
            await using var blocked = db.DataSource.CreateCommand("SELECT count(*) FROM pg_stat_activity WHERE application_name=$1 AND wait_event_type='Lock'");
            blocked.Parameters.AddWithValue(application);
            if ((long)(await blocked.ExecuteScalarAsync(observation.Token))! > 0) break;
            await Task.Delay(20, observation.Token);
        }
        await cancellation.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending.WaitAsync(TimeSpan.FromSeconds(10), ct));
        await transaction.RollbackAsync(ct);
        using var retry = CancellationTokenSource.CreateLinkedTokenSource(ct);
        retry.CancelAfter(TimeSpan.FromSeconds(15));
        var recovered = await Repository(source).GetAsync(player, retry.Token);
        Assert.Equal(player.UserId, recovered.Player.UserId);
        Assert.Equal(3, recovered.ClassWeapons.Count);
        Assert.Null(recovered.UnfinishedMatch);
        await using var sanity = source.CreateCommand("SELECT 42");
        Assert.Equal(42, (int)(await sanity.ExecuteScalarAsync(retry.Token))!);
    }

    private static BootstrapRepository Repository(NpgsqlDataSource source) =>
        new(source, new ProgressionRepository(source), new EconomyRepository(source, TimeProvider.System),
            new MailRepository(source, TimeProvider.System), new PreparationRepository(source, TimeProvider.System), TimeProvider.System);

    private static Task<PlayerProfile> PlayerAsync(PostgresTestSchema db, CancellationToken ct)
    {
        var now = DateTimeOffset.UtcNow;
        return new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString(), "Batch " + Guid.NewGuid().ToString("N")[..12], SessionToken.Hash(SessionToken.Create()), now, now.AddHours(1), ct);
    }

    private static async Task Sql(PostgresTestSchema db, string sql, CancellationToken ct, params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(ct);
    }
}

