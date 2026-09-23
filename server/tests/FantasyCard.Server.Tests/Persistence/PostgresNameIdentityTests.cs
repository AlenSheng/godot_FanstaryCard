using System.Security.Cryptography;
using FantasyCard.Contracts.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresNameIdentityTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Returning_login_repairs_missing_cards_and_preserves_complete_account()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var now = DateTimeOffset.UtcNow;
        var ct = TestContext.Current.CancellationToken;
        var player = await identity.SignInLocalAsync("device-one", "Cache player",
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var before = await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_cards WHERE player_id=$1", player.UserId);
        await using (var delete = database.DataSource.CreateCommand(
            "DELETE FROM player_cards WHERE player_id=$1 AND card_id=(SELECT card_id FROM player_cards WHERE player_id=$1 LIMIT 1)"))
        {
            delete.Parameters.AddWithValue(player.UserId);
            Assert.Equal(1, await delete.ExecuteNonQueryAsync(ct));
        }
        await identity.SignInLocalAsync("device-two", "Cache player",
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal(before, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_cards WHERE player_id=$1", player.UserId));
        await identity.SignInLocalAsync("device-three", "Cache player",
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal(before, await database.ScalarAsync<long>(
            "SELECT count(*) FROM player_cards WHERE player_id=$1", player.UserId));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Same_device_different_names_create_separate_accounts_and_returning_names_restore_assets()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var now = DateTimeOffset.UtcNow;
        var ct = TestContext.Current.CancellationToken;
        var first = await identity.SignInLocalAsync("shared-device", "Alice", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await using (var gold = database.DataSource.CreateCommand("UPDATE player_wallets SET gold=321 WHERE player_id=$1"))
        {
            gold.Parameters.AddWithValue(first.UserId);
            await gold.ExecuteNonQueryAsync(ct);
        }
        var second = await identity.SignInLocalAsync("shared-device", "Bob", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.NotEqual(first.UserId, second.UserId);
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", second.UserId));

        var returning = await identity.SignInLocalAsync("different-device", "  ＡＬＩＣＥ  ", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal(first.UserId, returning.UserId);
        Assert.Equal("Alice", returning.DisplayName);
        Assert.Equal(321L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", returning.UserId));
        Assert.Equal(2L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
        Assert.Equal(6L, await database.ScalarAsync<long>("SELECT count(*) FROM class_weapons"));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Names_owned_by_platform_accounts_cannot_be_claimed_by_local_login_or_another_platform_identity()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var now = DateTimeOffset.UtcNow;
        var ct = TestContext.Current.CancellationToken;
        var platform = await identity.SignInExternalAsync("steam", "platform-one", "Steam Player", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await Assert.ThrowsAsync<PlayerNameConflictException>(() => identity.SignInLocalAsync(
            "shared-device", "ＳＴＥＡＭ ＰＬＡＹＥＲ", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct));
        await Assert.ThrowsAsync<PlayerNameConflictException>(() => identity.SignInExternalAsync(
            "steam", "platform-two", "steam player", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct));
        var returning = await identity.SignInExternalAsync("steam", "platform-one", "Different caption", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        Assert.Equal(platform.UserId, returning.UserId);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM players"));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM external_identities WHERE provider='local-name'"));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Unique_index_rejects_duplicate_names_and_local_profile_updates_cannot_change_account_identity()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var profiles = new PlayerRepository(database.DataSource);
        var now = DateTimeOffset.UtcNow;
        var ct = TestContext.Current.CancellationToken;
        var local = await identity.SignInLocalAsync("shared-device", "Alice", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        var platform = await identity.SignInExternalAsync("steam", "platform-one", "Bob", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await Assert.ThrowsAsync<PlayerNameConflictException>(() => profiles.UpdateAsync(
            local.UserId, new("Charlie", null, local.Version), "rename-local", now, ct));
        await Assert.ThrowsAsync<PlayerNameConflictException>(() => profiles.UpdateAsync(
            platform.UserId, new("ＡＬＩＣＥ", null, platform.Version), "rename-conflict", now, ct));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT version FROM players WHERE user_id=$1", local.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM idempotency_records"));
        var selected = await profiles.UpdateAsync(local.UserId, new("ALICE", HeroClassDto.Guardian, local.Version), "select-class", now, ct);
        Assert.Equal(UpdatePlayerResult.Updated, selected.Status);
        Assert.Equal(HeroClassDto.Guardian, selected.Profile!.SelectedClass);
        Assert.Equal(selected, await profiles.UpdateAsync(local.UserId, new("ALICE", HeroClassDto.Guardian, local.Version), "select-class", now, ct));
        Assert.Equal(local.UserId, (await identity.SignInLocalAsync("other-device", "alice", RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct)).UserId);

        await using var duplicate = database.DataSource.CreateCommand("UPDATE players SET display_name='alice' WHERE user_id=$1");
        duplicate.Parameters.AddWithValue(platform.UserId);
        var error = await Assert.ThrowsAsync<PostgresException>(() => duplicate.ExecuteNonQueryAsync(ct));
        Assert.Equal(PostgresErrorCodes.UniqueViolation, error.SqlState);
        Assert.Equal("ux_players_display_name_key", error.ConstraintName);
    }
}
