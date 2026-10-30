using System.Security.Cryptography;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSystemMailLocalizationTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("test_mailmeta", "seed_gold", 7, false)]
    [InlineData("test2_mailmeta", "seed2_fragments", 2, true)]
    [Trait("Category", "PostgresIntegration")]
    public async Task Seed_metadata_repair_preserves_claimed_rewards_and_does_not_duplicate_mail(
        string name, string claimedTemplate, int expectedCount, bool fragments)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var now = DateTimeOffset.UtcNow;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var player = await identity.SignInLocalAsync("mail-device", name, RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var mail = new MailRepository(database.DataSource, TimeProvider.System);
        var first = await mail.GetAsync(player.UserId, ct);
        Assert.Equal(expectedCount, first.Items.Count);
        Assert.All(first.Items, item =>
        {
            Assert.NotNull(item.TemplateId);
            Assert.Equal("system", item.SenderRole);
            Assert.Empty(item.TemplateArgs!);
        });
        var target = Assert.Single(first.Items, item => item.TemplateId == claimedTemplate);
        Assert.Equal(100000L, Assert.Single(target.Attachments).Amount);
        Assert.NotNull(await mail.ClaimAsync(player.UserId, target.Id, "claim-before-repair", ct));
        var claimedAt = await database.ScalarAsync<string>("SELECT claimed_at::text FROM mail_messages WHERE mail_id=$1", target.Id);
        var attachments = await database.ScalarAsync<string>("SELECT attachments_json::text FROM mail_messages WHERE mail_id=$1", target.Id);
        await using (var legacy = database.DataSource.CreateCommand(
            "UPDATE mail_messages SET template_id='',template_args='{}'::jsonb,sender_role='' WHERE mail_id=$1"))
        {
            legacy.Parameters.AddWithValue(target.Id);
            Assert.Equal(1, await legacy.ExecuteNonQueryAsync(ct));
        }

        await identity.SignInLocalAsync("second-device", name, RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var repaired = await mail.GetAsync(player.UserId, ct);
        Assert.Equal(expectedCount, repaired.Items.Count);
        var repairedTarget = Assert.Single(repaired.Items, item => item.Id == target.Id);
        Assert.Equal(claimedTemplate, repairedTarget.TemplateId);
        Assert.True(repairedTarget.IsRead);
        Assert.True(repairedTarget.IsClaimed);
        Assert.Equal(claimedAt, await database.ScalarAsync<string>("SELECT claimed_at::text FROM mail_messages WHERE mail_id=$1", target.Id));
        Assert.Equal(attachments, await database.ScalarAsync<string>("SELECT attachments_json::text FROM mail_messages WHERE mail_id=$1", target.Id));
        var version = await database.ScalarAsync<long>("SELECT version FROM mail_messages WHERE mail_id=$1", target.Id);
        await using (var oldTitle = database.DataSource.CreateCommand("UPDATE mail_messages SET title='Older seed title' WHERE mail_id=$1"))
        {
            oldTitle.Parameters.AddWithValue(target.Id);
            Assert.Equal(1, await oldTitle.ExecuteNonQueryAsync(ct));
        }
        await identity.SignInLocalAsync("third-device", name, RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal(version, await database.ScalarAsync<long>("SELECT version FROM mail_messages WHERE mail_id=$1", target.Id));
        Assert.Equal((long)expectedCount, await database.ScalarAsync<long>("SELECT count(*) FROM mail_messages WHERE player_id=$1", player.UserId));
        Assert.True((await mail.ClaimAsync(player.UserId, target.Id, "claim-after-repair", ct))!.AlreadyClaimed);
        var balance = fragments
            ? await database.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1", player.UserId)
            : await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId);
        Assert.Equal(100000L, balance);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Recall_persists_exact_reason_and_free_admin_mail_is_not_inferred_from_its_title()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var now = DateTimeOffset.UtcNow;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var player = await identity.SignInLocalAsync("device", "Mail owner", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await using (var wallet = database.DataSource.CreateCommand("UPDATE player_wallets SET gold=100 WHERE player_id=$1"))
        {
            wallet.Parameters.AddWithValue(player.UserId);
            Assert.Equal(1, await wallet.ExecuteNonQueryAsync(ct));
        }
        var admin = new AdminRepository(database.DataSource, TimeProvider.System,
            new ConnectionRegistry(), new RealtimeEventStore(TimeProvider.System));
        const string reason = "  Fire  Gold: 装备 {amount} {reason}\n管理员原文  ";
        Assert.True(await admin.RevokeAsync(new(player.UserId, "Gold", 7, null, reason), "localized-revoke", ct) is true);
        var mail = new MailRepository(database.DataSource, TimeProvider.System);
        var recalled = Assert.Single((await mail.GetAsync(player.UserId, ct)).Items);
        Assert.Equal("item_reclamation", recalled.TemplateId);
        Assert.Equal("admin", recalled.SenderRole);
        Assert.Equal("Gold", Assert.Single(recalled.TemplateArgs!, argument => argument.Key == "kind").Value);
        Assert.Equal("7", Assert.Single(recalled.TemplateArgs!, argument => argument.Key == "amount").Value);
        Assert.Equal(reason, Assert.Single(recalled.TemplateArgs!, argument => argument.Key == "reason").Value);
        Assert.EndsWith(reason, recalled.Body);
        Assert.EndsWith(reason, recalled.BodyEn);
        Assert.Equal(93L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        var freeId = await admin.SendMailAsync(new(player.UserId, recalled.Title, "Free authored Fire Gold 装备", []),
            "message", "free-mail-same-title", ct);
        var free = Assert.Single((await mail.GetAsync(player.UserId, ct)).Items, item => item.Id == freeId);
        Assert.Null(free.TemplateId);
        Assert.Empty(free.TemplateArgs!);
        Assert.Equal("admin", free.SenderRole);
        Assert.Equal("Free authored Fire Gold 装备", free.Body);
        Assert.Empty(free.Attachments);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Legacy_mail_with_no_metadata_is_read_unchanged_even_when_it_looks_like_a_recall()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var now = DateTimeOffset.UtcNow;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var player = await identity.SignInLocalAsync("device", "Legacy mail", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        const string body = "管理员收回：Gold × 7。原因：Free text {reason} Fire Gold 装备";
        await using (var insert = database.DataSource.CreateCommand(
            "INSERT INTO mail_messages(mail_id,player_id,title,body,sender,attachments_json,sent_at) VALUES($1,$2,'道具收回通知',$3,'Game Admin','[]'::jsonb,$4)"))
        {
            insert.Parameters.AddWithValue(Guid.CreateVersion7());
            insert.Parameters.AddWithValue(player.UserId);
            insert.Parameters.AddWithValue(body);
            insert.Parameters.AddWithValue(now);
            Assert.Equal(1, await insert.ExecuteNonQueryAsync(ct));
        }
        var legacy = Assert.Single((await new MailRepository(database.DataSource, TimeProvider.System).GetAsync(player.UserId, ct)).Items);
        Assert.Null(legacy.TemplateId);
        Assert.Null(legacy.SenderRole);
        Assert.Empty(legacy.TemplateArgs!);
        Assert.Equal(body, legacy.Body);
        Assert.Equal("", legacy.BodyEn);
        Assert.False(legacy.IsClaimed);
        Assert.False(legacy.IsRead);
    }
}
