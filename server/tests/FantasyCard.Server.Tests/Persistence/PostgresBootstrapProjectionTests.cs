using FantasyCard.Domain.Players;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresBootstrapProjectionTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Projection_is_scoped_to_caller_match_unacknowledged_and_completed_holds_without_writes()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await PlayerAsync(db, ct);
        var other = await PlayerAsync(db, ct);
        var repository = Repository(db.DataSource);
        var match = Guid.NewGuid(); var receipt = Guid.NewGuid();
        var newerMatch = Guid.NewGuid(); var newerReceipt = Guid.NewGuid();
        await SeedAsync(db, player.UserId, match, receipt, 0, ct);
        await SeedAsync(db, player.UserId, newerMatch, newerReceipt, 1, ct);
        var full = await repository.GetAsync(player, ct);
        Assert.Equal(newerReceipt, full.UnfinishedSettlement!.SettlementId);
        Assert.NotEmpty(full.Cards);
        var before = await DigestAsync(db, ct);
        var selected = await repository.GetSettlementAsync(player.UserId, match, ct);
        Assert.Equal(receipt, selected.UnfinishedSettlement!.SettlementId);
        Assert.Equal(match, selected.UnfinishedSettlement.MatchId);
        Assert.Equal(player.UserId, selected.UnfinishedSettlement.PlayerId);
        Assert.Equal(BootstrapRepository.CurrentConfigVersion, selected.ConfigVersion);
        Assert.Null((await repository.GetSettlementAsync(other.UserId, match, ct)).UnfinishedSettlement);
        Assert.Null((await repository.GetSettlementAsync(player.UserId, Guid.NewGuid(), ct)).UnfinishedSettlement);
        Assert.Equal(before, await DigestAsync(db, ct));

        var hold = Guid.NewGuid();
        await Sql(db, "INSERT INTO settlement_asset_holds(hold_id,settlement_id,player_id,asset_kind,asset_ref,asset_snapshot,state,created_at) VALUES($1,$2,$3,'Gold','projection-gold','{}','Pending',now())", ct, hold, receipt, player.UserId);
        before = await DigestAsync(db, ct);
        Assert.Null((await repository.GetSettlementAsync(player.UserId, match, ct)).UnfinishedSettlement);
        Assert.Equal(newerReceipt, (await repository.GetSettlementAsync(player.UserId, newerMatch, ct)).UnfinishedSettlement!.SettlementId);
        Assert.Equal(before, await DigestAsync(db, ct));
        await Sql(db, "UPDATE settlement_asset_holds SET state='Committed' WHERE hold_id=$1", ct, hold);
        Assert.Equal(receipt, (await repository.GetSettlementAsync(player.UserId, match, ct)).UnfinishedSettlement!.SettlementId);
        await Sql(db, "UPDATE match_settlements SET acknowledged_at=now() WHERE settlement_id=$1", ct, receipt);
        before = await DigestAsync(db, ct);
        Assert.Null((await repository.GetSettlementAsync(player.UserId, match, ct)).UnfinishedSettlement);
        Assert.Equal(before, await DigestAsync(db, ct));
        Assert.NotEmpty((await repository.GetAsync(player, ct)).Cards);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Projection_does_not_wait_on_locked_wallet_or_card_catalog_tables()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await PlayerAsync(db, ct);
        var match = Guid.NewGuid(); var receipt = Guid.NewGuid();
        await SeedAsync(db, player.UserId, match, receipt, 0, ct);
        await using var locker = await db.DataSource.OpenConnectionAsync(ct);
        await using var transaction = await locker.BeginTransactionAsync(ct);
        await using (var command = new NpgsqlCommand("LOCK TABLE player_wallets,player_cards IN ACCESS EXCLUSIVE MODE", locker, transaction))
            await command.ExecuteNonQueryAsync(ct);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        var projection = await Repository(db.DataSource).GetSettlementAsync(player.UserId, match, deadline.Token);
        Assert.Equal(receipt, projection.UnfinishedSettlement!.SettlementId);
        await transaction.RollbackAsync(ct);
        Assert.NotEmpty((await Repository(db.DataSource).GetAsync(player, ct)).Cards);
    }

    private static BootstrapRepository Repository(NpgsqlDataSource source) =>
        new(source, new ProgressionRepository(source), new EconomyRepository(source, TimeProvider.System),
            new MailRepository(source, TimeProvider.System), new PreparationRepository(source, TimeProvider.System), TimeProvider.System);

    private static Task<PlayerProfile> PlayerAsync(PostgresTestSchema db, CancellationToken ct)
    {
        var now = DateTimeOffset.UtcNow;
        return new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString(), "Proj " + Guid.NewGuid().ToString("N")[..12],
            SessionToken.Hash(SessionToken.Create()), now, now.AddHours(1), ct);
    }

    private static async Task SeedAsync(PostgresTestSchema db, Guid player, Guid match, Guid receipt, int seconds, CancellationToken ct)
    {
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',7,'projection-fixture','Completed',now())", ct, match, Guid.NewGuid());
        await Sql(db, "INSERT INTO match_settlements(settlement_id,match_id,player_id,result,details_json,created_at) VALUES($1,$2,$3,'Dead','{\"revision\":789}'::jsonb,now()+make_interval(secs=>$4))", ct, receipt, match, player, seconds);
    }

    private static async Task<string> DigestAsync(PostgresTestSchema db, CancellationToken ct)
    {
        await using var command = db.DataSource.CreateCommand("""
            SELECT md5(jsonb_build_object(
                'settlements',(SELECT jsonb_agg(to_jsonb(t) ORDER BY settlement_id) FROM match_settlements t),
                'holds',(SELECT jsonb_agg(to_jsonb(t) ORDER BY hold_id) FROM settlement_asset_holds t),
                'wallets',(SELECT jsonb_agg(to_jsonb(t) ORDER BY player_id) FROM player_wallets t),
                'movements',(SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM inventory_movements t),
                'ACKs',(SELECT jsonb_agg(to_jsonb(t) ORDER BY request_id) FROM idempotency_records t WHERE scope='settlement.acknowledge')
            )::text)
            """);
        return (string)(await command.ExecuteScalarAsync(ct))!;
    }

    private static async Task Sql(PostgresTestSchema db, string sql, CancellationToken ct, params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(ct);
    }
}
