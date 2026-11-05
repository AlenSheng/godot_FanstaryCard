using System.Text.Json;
using FantasyCard.Contracts.Mail;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Seasons;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresMailPermanentCopyTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;
    private const string Required = "Requires isolated PostgreSQL.";
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static readonly JsonSerializerOptions WebJson = new(JsonSerializerDefaults.Web);
    private sealed record Fixture(Guid Player, CraftingClock Clock, MailRepository Mail, SeasonDefinition? Season);
    private static Task Sql(PostgresTestSchema db, string sql, params object[] values) => CraftingTestInputs.SqlAsync(db, sql, values);

    private static async Task<Fixture> Create(PostgresTestSchema db, bool publish = true)
    {
        var clock = new CraftingClock(new DateTimeOffset(2026, 11, 1, 4, 0, 0, TimeSpan.Zero));
        var player = await CraftingTestInputs.PlayerAsync(db, clock);
        await Sql(db, "DELETE FROM mail_messages WHERE player_id=$1", player);
        SeasonDefinition? season = null;
        if (publish)
        {
            var config = GameConfigCatalog.Current;
            season = SeasonDefinition.FromCalendarDays("mail-copy-season", new(2026, 11, 1), config.Version, "season-equipment-v1");
            var seasons = new SeasonRepository(db.DataSource, clock);
            await seasons.PublishAsync(season, config.ContentHash, Ct);
            await seasons.EnsurePlayerAsync(player, season.ContextFor(0), Ct);
        }
        return new(player, clock, new(db.DataSource, clock), season);
    }

    private static async Task<Guid> Send(PostgresTestSchema db, Fixture f, params MailAttachmentResponse[] attachments)
    {
        var id = Guid.CreateVersion7();
        var payload = JsonSerializer.Serialize(attachments, WebJson);
        await using var command = db.DataSource.CreateCommand("""
            INSERT INTO mail_messages(mail_id,player_id,title,body,sender,attachments_json,sent_at)
            VALUES($1,$2,'declared fixture','permanent copy fixture','system',$3::jsonb,$4)
            """);
        command.Parameters.AddWithValue(id);command.Parameters.AddWithValue(f.Player);
        command.Parameters.AddWithValue(payload);command.Parameters.AddWithValue(f.Clock.Now);
        await command.ExecuteNonQueryAsync(Ct);
        return id;
    }

    private static Task<int> Copies(PostgresTestSchema db, Guid player, string card) => db.ScalarAsync<int>("""
        SELECT c.copy_count+COALESCE(r.extra_count,0) FROM player_cards c
        LEFT JOIN player_card_reserves r USING(player_id,card_id) WHERE c.player_id=$1 AND c.card_id=$2
        """, player, card);

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task LegacyMailKeepsActivationSemanticsWithoutInventingPermanentCopyAdoption()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db, false);
        var id = await Send(db, f, new MailAttachmentResponse("Card", 3, "C01"));
        Assert.NotNull(await f.Mail.ClaimAsync(f.Player, id, "legacy", Ct));
        Assert.Equal(1, await Copies(db, f.Player, "C01"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM player_card_copy_modes WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task PublishedPolicyCreditsExactDuplicateAndNewCardQuantitiesBeforeOpeningShopOrCodex()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var locked = GameConfigCatalog.Current.Cards.First(card => card.Enabled && card.IsCodex && !card.InitiallyUnlocked).CardId;
        await Sql(db, "UPDATE player_cards SET level=3 WHERE player_id=$1 AND card_id='C01'", f.Player);
        var before = await Copies(db, f.Player, "C01");
        var id = await Send(db, f, new MailAttachmentResponse("Card", 2, "C01"), new MailAttachmentResponse("Card", 3, "C01"), new MailAttachmentResponse("Card", 2, locked));
        var result = (await f.Mail.ClaimAsync(f.Player, id, "exact", Ct))!;
        Assert.False(result.AlreadyClaimed);Assert.Equal(3, result.Granted.Count);
        Assert.Equal(before + 5, await Copies(db, f.Player, "C01"));Assert.Equal(2, await Copies(db, f.Player, locked));
        Assert.Equal(3, await db.ScalarAsync<int>("SELECT level::integer FROM player_cards WHERE player_id=$1 AND card_id='C01'", f.Player));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1 AND reason='mail.claim' AND request_id=$2", f.Player, id.ToString("D")));
        Assert.Equal(7, await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM card_copy_ledger WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM shop_purchases WHERE player_id=$1", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task SingleAndBatchClaimsSerializeInAccountThenMailOrderAndMintEachOriginalMailOnce()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await Copies(db, f.Player, "C01");
        var first = await Send(db, f, new MailAttachmentResponse("Card", 2, "C01"));var second = await Send(db, f, new MailAttachmentResponse("Card", 3, "C01"));
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(Ct);deadline.CancelAfter(TimeSpan.FromSeconds(20));
        await Task.WhenAll(f.Mail.ClaimAsync(f.Player, first, "single", deadline.Token), f.Mail.ClaimAllAsync(f.Player, "batch", deadline.Token));
        Assert.Equal(before + 5, await Copies(db, f.Player, "C01"));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1", f.Player));
        Assert.Equal(2, await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE player_id=$1 AND claimed_at IS NOT NULL", f.Player));
        Assert.True((await f.Mail.ClaimAsync(f.Player, second, "another", Ct))!.AlreadyClaimed);
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task DurableReplayAndFreshKeysDoNotRepeatGrantsAndLedgerRetainsMailIdentityAfterDeletion()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await Copies(db, f.Player, "C01");var id = await Send(db, f, new MailAttachmentResponse("Card", 4, "C01"));
        var claimed = await f.Mail.ClaimAsync(f.Player, id, "replay", Ct);
        var replay = await new MailRepository(db.DataSource, f.Clock).ClaimAsync(f.Player, id, "replay", Ct);
        Assert.Equal(JsonSerializer.Serialize(claimed), JsonSerializer.Serialize(replay));
        Assert.True((await f.Mail.ClaimAsync(f.Player, id, "new-key", Ct))!.AlreadyClaimed);
        Assert.Equal(before + 4, await Copies(db, f.Player, "C01"));
        Assert.True(await f.Mail.DeleteAsync(f.Player, id, Ct));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1 AND reason='mail.claim' AND request_id=$2 AND delta=4", f.Player, id.ToString("D")));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task FailureAfterCardGrantRollsBackCopiesPolicyLedgerAndClaimThenRetriesExactlyOnce()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await Copies(db, f.Player, "C01");var id = await Send(db, f, new MailAttachmentResponse("Card", 2, "C01"), new MailAttachmentResponse("UnsupportedFixture", 1));
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Mail.ClaimAsync(f.Player, id, "rollback", Ct));
        Assert.Equal(before, await Copies(db, f.Player, "C01"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM player_card_copy_modes WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE mail_id=$1 AND claimed_at IS NOT NULL", id));
        await Sql(db, "UPDATE mail_messages SET attachments_json='[{\"kind\":\"Card\",\"amount\":2,\"itemId\":\"C01\"}]'::jsonb WHERE mail_id=$1", id);
        Assert.NotNull(await f.Mail.ClaimAsync(f.Player, id, "rollback", Ct));
        Assert.Equal(before + 2, await Copies(db, f.Player, "C01"));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task InvalidIdentityAndOverflowCannotMintPartialAssetsOrClaimTheMail()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var before = await Copies(db, f.Player, "C01");
        var invalid = await Send(db, f, new MailAttachmentResponse("Card", 2, "not-an-existing-player-card"));
        await Assert.ThrowsAsync<DomainValidationException>(() => f.Mail.ClaimAsync(f.Player, invalid, "identity", Ct));
        var overflow = await Send(db, f, new MailAttachmentResponse("Card", (long)int.MaxValue + 1, "C01"));
        await Assert.ThrowsAsync<OverflowException>(() => f.Mail.ClaimAsync(f.Player, overflow, "overflow", Ct));
        Assert.Equal(before, await Copies(db, f.Player, "C01"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE player_id=$1 AND claimed_at IS NOT NULL", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task PermanentCopiesSurviveSeasonClosureWithoutReclassifyingUnversionedMailAsNewSeasonLoot()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var first = await Send(db, f, new MailAttachmentResponse("Card", 2, "C01"));await f.Mail.ClaimAsync(f.Player, first, "before-end", Ct);
        var before = await Copies(db, f.Player, "C01");
        f.Clock.Now = f.Season!.EndsAtUtc.AddDays(1);
        var id = await Send(db, f, new MailAttachmentResponse("Card", 3, "C01"));await f.Mail.ClaimAsync(f.Player, id, "after-end", Ct);
        Assert.Equal(before + 3, await Copies(db, f.Player, "C01"));
        Assert.Equal(1, await db.ScalarAsync<long>("SELECT count(*) FROM player_card_copy_modes WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM season_journey_grant_ledger WHERE player_id=$1", f.Player));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM shop_purchases WHERE player_id=$1", f.Player));
    }

    [Fact(Skip = Required, SkipUnless = nameof(HasTestDatabase))][Trait("Category", "PostgresIntegration")]
    public async Task AnotherAccountCannotClaimTheMailAndAnIdempotencyKeyCannotBeReusedForDifferentMail()
    {
        await using var db = await PostgresTestSchema.CreateAsync(true);var f = await Create(db);
        var other = await CraftingTestInputs.PlayerAsync(db, f.Clock);var first = await Send(db, f, new MailAttachmentResponse("Card", 2, "C01"));
        var second = await Send(db, f, new MailAttachmentResponse("Card", 3, "C01"));var before = await Copies(db, f.Player, "C01");
        Assert.Null(await f.Mail.ClaimAsync(other, first, "wrong-owner", Ct));
        await f.Mail.ClaimAsync(f.Player, first, "same-key", Ct);
        await Assert.ThrowsAsync<IdempotencyConflictException>(() => f.Mail.ClaimAsync(f.Player, second, "same-key", Ct));
        Assert.Equal(before + 2, await Copies(db, f.Player, "C01"));
        Assert.Equal(0, await db.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE mail_id=$1 AND claimed_at IS NOT NULL", second));
    }
}
