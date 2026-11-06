using FantasyCard.Contracts.Mail;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresMailPermanentCopyTests
{
    private static readonly (string Kind, string Table, string Column, long Amount)[] MailCurrencies =
    [
        ("Gold", "player_wallets", "gold", 7), ("Diamond", "player_wallets", "diamond", 11),
        ("WarriorSoul", "player_materials", "warrior_soul", 13), ("PriestSoul", "player_materials", "priest_soul", 17),
        ("MageSoul", "player_materials", "mage_soul", 19), ("GuardianSoul", "player_materials", "guardian_soul", 23),
        ("EquipmentFragments", "player_materials", "equipment_fragments", 29)
    ];

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task UnversionedMailCreditsSevenCurrenciesAndKeepsLegacySourceInsteadOfTodaysSeason()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = new Dictionary<string, long>();
        foreach (var currency in MailCurrencies)
            before[currency.Kind] = await db.ScalarAsync<long>($"SELECT {currency.Column} FROM {currency.Table} WHERE player_id=$1", f.Player);
        var id = await Send(db, f, MailCurrencies.Select(c => new MailAttachmentResponse(c.Kind, c.Amount)).ToArray());
        await f.Mail.ClaimAsync(f.Player, id, "all-currencies", Ct);
        foreach (var currency in MailCurrencies)
        {
            Assert.Equal(before[currency.Kind] + currency.Amount, await db.ScalarAsync<long>($"SELECT {currency.Column} FROM {currency.Table} WHERE player_id=$1", f.Player));
            Assert.Equal(currency.Amount, await db.ScalarAsync<long>("SELECT delta FROM economy_ledger WHERE player_id=$1 AND request_id=$2 AND currency=$3", f.Player, id.ToString("D"), currency.Kind));
        }
        Assert.Equal(7, await db.ScalarAsync<long>("""
            SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id=$2 AND reason='mail.claim'
              AND source_kind='LegacyMail' AND season_id IS NULL AND difficulty_id IS NULL
              AND ruleset_id IS NULL AND config_version IS NULL AND stats_version IS NULL
            """, f.Player, id.ToString("D")));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT gold+equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2", f.Player, f.Season!.SeasonId));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task MailSoulThenRealCardCraftLeavesAContiguousPermanentCurrencyChain()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var id = await Send(db, f, new MailAttachmentResponse("WarriorSoul", 10000));
        await f.Mail.ClaimAsync(f.Player, id, "soul", Ct);
        var progression = new ProgressionRepository(db.DataSource, f.Clock);
        var definition = GameConfigCatalog.Current.Cards.First(c => c.Enabled && c.IsCodex && c.HeroClass is null && !c.InitiallyUnlocked);
        var card = (await progression.GetCardsAsync(f.Player, Ct)).Single(c => c.CardId == definition.CardId);
        await progression.MutateCardAsync(f.Player, card.CardId, "craft-after-mail", new CardMutationRequest(card.Version), true, Ct);
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND currency='WarriorSoul'", f.Player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task BatchMailKeepsEachOriginalIdentityAndReplayDoesNotWriteExtraCurrencyRows()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", f.Player);
        var first = await Send(db, f, new MailAttachmentResponse("Gold", 2), new MailAttachmentResponse("Gold", 3));
        var second = await Send(db, f, new MailAttachmentResponse("Gold", 9));
        var result = await f.Mail.ClaimAllAsync(f.Player, "batch-currencies", Ct);
        Assert.Equal(2, result.MailCount);Assert.Equal(before + 14, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", f.Player));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id=$2", f.Player, first.ToString("D")));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id=$2", f.Player, second.ToString("D")));
        await f.Mail.ClaimAllAsync(f.Player, "batch-currencies", Ct);await f.Mail.ClaimAllAsync(f.Player, "fresh-batch-key", Ct);
        Assert.Equal(3, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='mail.claim'", f.Player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task CurrencyLedgerFaultRollsBackBalanceClaimAndReceiptBeforeTheOriginalRequestRetries()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", f.Player);
        var id = await Send(db, f, new MailAttachmentResponse("Gold", 17));
        await Sql(db, """
            CREATE FUNCTION fail_mail_currency_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'declared mail ledger failure'; END; $$;
            CREATE TRIGGER fail_mail_currency_ledger BEFORE INSERT ON economy_ledger
            FOR EACH ROW EXECUTE FUNCTION fail_mail_currency_ledger();
            """);
        await Assert.ThrowsAsync<PostgresException>(() => f.Mail.ClaimAsync(f.Player, id, "currency-fault", Ct));
        Assert.Equal(before, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE mail_id=$1 AND claimed_at IS NOT NULL", id));
        await Sql(db, "DROP TRIGGER fail_mail_currency_ledger ON economy_ledger");
        await f.Mail.ClaimAsync(f.Player, id, "currency-fault", Ct);
        Assert.Equal(before + 17, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", f.Player));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND request_id=$2", f.Player, id.ToString("D")));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task EquipmentMailWritesItsExactItemMovementAndAFaultCannotLeaveAnUnrecordedMint()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var first = await Send(db, f, new MailAttachmentResponse("Equipment", 1, "Blue|Fire|Chest"));
        await f.Mail.ClaimAsync(f.Player, first, "equipment", Ct);
        var item = await db.ScalarAsync<Guid>("SELECT item_id FROM inventory_movements WHERE player_id=$1 AND request_id=$2 AND reason='mail.claim'", f.Player, first.ToString("D"));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND owner_id=$2 AND season_id IS NULL AND location='Inventory'", item, f.Player));
        var before = await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", f.Player);
        var second = await Send(db, f, new MailAttachmentResponse("Equipment", 1, "Blue|Water|Feet"));
        await Sql(db, """
            CREATE FUNCTION fail_mail_equipment_movement() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'declared mail movement failure'; END; $$;
            CREATE TRIGGER fail_mail_equipment_movement BEFORE INSERT ON inventory_movements
            FOR EACH ROW EXECUTE FUNCTION fail_mail_equipment_movement();
            """);
        await Assert.ThrowsAsync<PostgresException>(() => f.Mail.ClaimAsync(f.Player, second, "movement-fault", Ct));
        Assert.Equal(before, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", f.Player));
        await Sql(db, "DROP TRIGGER fail_mail_equipment_movement ON inventory_movements");
        await f.Mail.ClaimAsync(f.Player, second, "movement-fault", Ct);
        Assert.Equal(before + 1, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", f.Player));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND request_id=$2", f.Player, second.ToString("D")));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task SingleAndBatchCurrencyClaimsShareTheAccountLockAndKeepOneSourcePerGrant()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await db.ScalarAsync<long>("SELECT mage_soul FROM player_materials WHERE player_id=$1", f.Player);
        var first = await Send(db, f, new MailAttachmentResponse("MageSoul", 5));
        await Send(db, f, new MailAttachmentResponse("MageSoul", 7));
        await Task.WhenAll(f.Mail.ClaimAsync(f.Player, first, "single-currency", Ct), f.Mail.ClaimAllAsync(f.Player, "all-currency", Ct));
        Assert.Equal(before + 12, await db.ScalarAsync<long>("SELECT mage_soul FROM player_materials WHERE player_id=$1", f.Player));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND currency='MageSoul' AND reason='mail.claim'", f.Player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }
}
