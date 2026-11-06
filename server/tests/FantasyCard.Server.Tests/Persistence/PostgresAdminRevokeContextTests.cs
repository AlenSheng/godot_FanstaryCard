using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresAdminRevokeContextTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private const string Required = "Requires isolated PostgreSQL.";
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static AdminRepository Admin(PostgresTestSchema db, CraftingClock clock) =>
        new(db.DataSource, clock, new ConnectionRegistry(), new RealtimeEventStore(clock));
    private static Task Sql(PostgresTestSchema db, string sql, params object[] values) => CraftingTestInputs.SqlAsync(db, sql, values);

    private static async Task<Guid> GrantMail(PostgresTestSchema db, CraftingPlayer f, string kind, long amount, string? item = null)
    {
        var id = (await Admin(db, f.Clock).SendMailAsync(new(f.Player, "declared fixture", "revoke context fixture",
            [new AdminAttachment(kind, amount, item)]), "test.fund-mail", "fund-" + Guid.NewGuid().ToString("N"), Ct))!.Value;
        await new MailRepository(db.DataSource, f.Clock).ClaimAsync(f.Player, id, "claim-" + id.ToString("N"), Ct);
        return id;
    }

    [Theory(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    [InlineData("PriestSoul")][InlineData("MageSoul")][InlineData("GuardianSoul")]
    public async Task ExactClassSoulRevokeStaysInItsOwnChainThroughTheNextRealCardCraft(string kind)
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        await GrantMail(db, f, kind, 10000);
        var admin = Admin(db, f.Clock);Assert.True(await admin.RevokeAsync(new(f.Player, kind, 7, null, "exact class"), "revoke", Ct));
        Assert.Equal(kind, await db.ScalarAsync<string>("SELECT currency FROM economy_ledger WHERE player_id=$1 AND request_id='revoke'", f.Player));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id='revoke' AND source_kind='AdminRevoke' AND season_id IS NULL", f.Player));
        var hero = kind.Replace("Soul", "", StringComparison.Ordinal);
        var definition = GameConfigCatalog.Current.Cards.First(c => c.Enabled && c.IsCodex && !c.InitiallyUnlocked && c.HeroClass?.ToString() == hero);
        var card = (await f.Progression.GetCardsAsync(f.Player, Ct)).Single(c => c.CardId == definition.CardId);
        await f.Progression.MutateCardAsync(f.Player, card.CardId, "craft-after-revoke", new(card.Version), true, Ct);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
        await Assert.ThrowsAsync<AdminConflictException>(() => admin.RevokeAsync(new(f.Player, kind, 7, null, "same request"), "revoke", Ct));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id='revoke'", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task ExistingAmbiguousClassSoulRowsAreNotReclassifiedByANewExactRevoke()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        await GrantMail(db, f, "MageSoul", 100);
        var old = Guid.CreateVersion7();
        await Sql(db, """
            INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at)
            VALUES($1,$2,'declared-unknown-history','ClassSoul',-1,99,'admin_revoke',$3)
            """, old, f.Player, f.Clock.Now.AddDays(-1));
        var before = await db.ScalarAsync<string>("SELECT row_to_json(l)::text FROM economy_ledger l WHERE ledger_id=$1", old);
        Assert.True(await Admin(db, f.Clock).RevokeAsync(new(f.Player, "MageSoul", 7, null, "new exact"), "exact-new", Ct));
        Assert.Equal(before, await db.ScalarAsync<string>("SELECT row_to_json(l)::text FROM economy_ledger l WHERE ledger_id=$1", old));
        Assert.Equal("MageSoul", await db.ScalarAsync<string>("SELECT currency FROM economy_ledger WHERE player_id=$1 AND request_id='exact-new'", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task CurrencyRevokeLedgerFaultRollsBackBalanceMailAndAuditThenTheOriginalKeyCanRetry()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        await GrantMail(db, f, "PriestSoul", 100);
        var before = await db.ScalarAsync<long>("SELECT priest_soul FROM player_materials WHERE player_id=$1", f.Player);
        var mails = await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE player_id=$1", f.Player);
        await Sql(db, """
            CREATE FUNCTION fail_revoke_currency() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'declared revoke ledger failure'; END; $$;
            CREATE TRIGGER fail_revoke_currency BEFORE INSERT ON economy_ledger
            FOR EACH ROW EXECUTE FUNCTION fail_revoke_currency();
            """);
        var admin = Admin(db, f.Clock);
        await Assert.ThrowsAsync<PostgresException>(() => admin.RevokeAsync(new(f.Player, "PriestSoul", 7, null, "rollback"), "rollback", Ct));
        Assert.Equal(before, await db.ScalarAsync<long>("SELECT priest_soul FROM player_materials WHERE player_id=$1", f.Player));
        Assert.Equal(mails, await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM admin_audit WHERE request_id='rollback'"));
        await Sql(db, "DROP TRIGGER fail_revoke_currency ON economy_ledger");
        Assert.True(await admin.RevokeAsync(new(f.Player, "PriestSoul", 7, null, "retry"), "rollback", Ct));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task SeasonalEquipmentRevokeUsesItsOriginalImmutableDefinitionAfterANewSeasonIsPublished()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        var item = await CraftingTestInputs.ItemAsync(db, f);
        f.Clock.Now = new DateTimeOffset(2027, 1, 1, 4, 0, 0, TimeSpan.Zero);
        var next = SeasonDefinition.FromCalendarDays("admin-next-season", new(2027, 1, 1), "declared-unavailable-new-config", "declared-new-stats");
        await f.Seasons.PublishAsync(next, new string('b', 64), Ct);
        Assert.True(await Admin(db, f.Clock).RevokeAsync(new(f.Player, "Equipment", 1, item.ToString("D"), "old item"), "old-equipment", Ct));
        Assert.Equal(1, await db.ScalarAsync<long>("""
            SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND item_id=$2 AND request_id='old-equipment'
              AND source_kind='AdminRevoke' AND season_id=$3 AND difficulty_id='D0'
              AND ruleset_id=$4 AND config_version=$5 AND stats_version=$6
            """, f.Player, item, f.Season.SeasonId, f.Season.RulesetId, f.Season.ConfigVersion, f.Season.StatsVersion));
        Assert.Equal(5, await db.ScalarAsync<short>("SELECT generated_difficulty FROM equipments WHERE instance_id=$1", item));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task LegacyEquipmentRevokeKeepsUnknownVersionContextNullDespiteAnActiveSeason()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);
        var mail = await GrantMail(db, f, "Equipment", 1, "Blue|Fire|Chest");
        var item = await db.ScalarAsync<Guid>("SELECT item_id FROM inventory_movements WHERE player_id=$1 AND request_id=$2 AND reason='mail.claim'", f.Player, mail.ToString("D"));
        Assert.True(await Admin(db, f.Clock).RevokeAsync(new(f.Player, "Equipment", 1, item.ToString("D"), "legacy"), "legacy-equipment", Ct));
        Assert.Equal(1, await db.ScalarAsync<long>("""
            SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND request_id='legacy-equipment' AND source_kind='AdminRevoke'
              AND season_id IS NULL AND difficulty_id IS NULL AND ruleset_id IS NULL AND config_version IS NULL AND stats_version IS NULL
            """, f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task MovementFaultRollsBackTheEquipmentLocationAndAuditAndAllowsExactlyOneRetry()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await CraftingTestInputs.CreateAsync(db);var item = await CraftingTestInputs.ItemAsync(db, f);
        await Sql(db, """
            CREATE FUNCTION fail_revoke_movement() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'declared revoke movement failure'; END; $$;
            CREATE TRIGGER fail_revoke_movement BEFORE INSERT ON inventory_movements
            FOR EACH ROW EXECUTE FUNCTION fail_revoke_movement();
            """);
        var admin = Admin(db, f.Clock);
        await Assert.ThrowsAsync<PostgresException>(() => admin.RevokeAsync(new(f.Player, "Equipment", 1, item.ToString("D"), "rollback"), "movement-retry", Ct));
        Assert.Equal("Inventory", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", item));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM admin_audit WHERE request_id='movement-retry'"));
        await Sql(db, "DROP TRIGGER fail_revoke_movement ON inventory_movements");
        Assert.True(await admin.RevokeAsync(new(f.Player, "Equipment", 1, item.ToString("D"), "retry"), "movement-retry", Ct));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND request_id='movement-retry'", f.Player));
    }
}
