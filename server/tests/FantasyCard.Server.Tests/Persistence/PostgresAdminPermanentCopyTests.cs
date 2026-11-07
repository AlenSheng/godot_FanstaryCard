using FantasyCard.Domain.Configuration;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresAdminPermanentCopyTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private const string Required = "Requires isolated PostgreSQL.";
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static AdminRepository Admin(PostgresTestSchema db, CraftingClock clock) =>
        new(db.DataSource, clock, new ConnectionRegistry(), new RealtimeEventStore(clock));

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task UnlockAllRetainsThePermanentCopyChainAndDoesNotGrantExtraCopiesOnFreshOrRepeatedRequests()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);
        var f = await CraftingTestInputs.CreateAsync(db);
        await f.Progression.GetCardsAsync(f.Player, Ct);
        var locked = GameConfigCatalog.Current.Cards.First(card => card.Enabled && card.IsCodex && !card.InitiallyUnlocked).CardId;
        // Declare a valid prior terminal state: one owned copy was consumed,
        // so the latest recorded balance and the current aggregate are zero.
        await CraftingTestInputs.SqlAsync(db, """
            INSERT INTO card_copy_ledger(movement_id,player_id,card_id,delta,balance_after,reason,request_id,created_at)
            VALUES($1,$2,$3,-1,0,'test.declared-prior-consumption','zero-before-admin',$4)
            """, Guid.CreateVersion7(), f.Player, locked, f.Clock.Now);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_cards SET level=3 WHERE player_id=$1 AND card_id='C01'", f.Player);
        var ownedVersion = await db.ScalarAsync<long>("SELECT version FROM player_cards WHERE player_id=$1 AND card_id='C01'", f.Player);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
        var admin = Admin(db, f.Clock);
        var result = (await admin.UnlockAllCardsAsync(f.Player, "unlock", Ct))!;
        Assert.True(result.Cards > 0);
        Assert.Equal(result.Cards, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1 AND reason='admin.unlock_all_cards' AND request_id='unlock'", f.Player));
        Assert.Equal(1, await db.ScalarAsync<int>("SELECT copy_count::integer FROM player_cards WHERE player_id=$1 AND card_id=$2", f.Player, locked));
        Assert.Equal(3, await db.ScalarAsync<int>("SELECT level::integer FROM player_cards WHERE player_id=$1 AND card_id='C01'", f.Player));
        Assert.Equal(ownedVersion, await db.ScalarAsync<long>("SELECT version FROM player_cards WHERE player_id=$1 AND card_id='C01'", f.Player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
        await Assert.ThrowsAsync<AdminConflictException>(() => admin.UnlockAllCardsAsync(f.Player, "unlock", Ct));
        Assert.Equal(0, (await admin.UnlockAllCardsAsync(f.Player, "new-key", Ct))!.Cards);
        Assert.Equal(result.Cards, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1 AND reason='admin.unlock_all_cards'", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task AdminAuditFailureRollsBackUnlocksAndCardLedgerTogetherAndTheOriginalRequestCanRetry()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);
        var f = await CraftingTestInputs.CreateAsync(db);await f.Progression.GetCardsAsync(f.Player, Ct);
        var missing = await db.ScalarAsync<long>("SELECT count(*) FROM player_cards WHERE player_id=$1 AND copy_count=0", f.Player);
        await CraftingTestInputs.SqlAsync(db, """
            CREATE FUNCTION fail_declared_admin_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'declared admin-audit failure'; END; $$;
            CREATE TRIGGER fail_declared_admin_audit BEFORE INSERT ON admin_audit
            FOR EACH ROW EXECUTE FUNCTION fail_declared_admin_audit();
            """);
        var admin = Admin(db, f.Clock);
        await Assert.ThrowsAsync<PostgresException>(() => admin.UnlockAllCardsAsync(f.Player, "rollback", Ct));
        Assert.Equal(missing, await db.ScalarAsync<long>("SELECT count(*) FROM player_cards WHERE player_id=$1 AND copy_count=0", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM admin_audit WHERE request_id='rollback'"));
        await CraftingTestInputs.SqlAsync(db, "DROP TRIGGER fail_declared_admin_audit ON admin_audit");
        Assert.Equal(missing, (await admin.UnlockAllCardsAsync(f.Player, "rollback", Ct))!.Cards);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }
}
