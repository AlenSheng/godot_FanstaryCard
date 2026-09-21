using System.Security.Cryptography;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresCardUpgradeTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Each_upgrade_uses_its_own_soul_pool_and_replays_without_changing_quality()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        foreach (var (id, currency, cost) in new[]
        {
            ("C01", "WarriorSoul", 5), ("PRI-01", "PriestSoul", 8),
            ("MAG-01", "MageSoul", 8), ("GUA-01", "GuardianSoul", 8)
        })
        {
            var card = (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == id);
            Assert.True(card.CanUpgrade);
            Assert.Equal(cost, card.UpgradeCost);
            Assert.Equal(0, card.UpgradeCopyCost);
            var request = new CardMutationRequest(card.Version);
            var upgraded = await repository.UpgradeCardAsync(player, id, "upgrade-" + id, request, ct);
            Assert.Equal(1, upgraded.Card.Level);
            Assert.Equal(card.Rarity, upgraded.Card.Rarity);
            Assert.Equal(card.CopyCount, upgraded.Card.CopyCount);
            Assert.Equal(currency, upgraded.CurrencyKind);
            Assert.Equal(cost, upgraded.SoulAmount);
            Assert.Equal(10000 - cost, Balance(upgraded.Materials, currency));
            Assert.Equal(card.NextEffect, upgraded.Card.CurrentEffect);
            Assert.Equal(upgraded, await repository.UpgradeCardAsync(player, id, "upgrade-" + id, request, ct));
            await Assert.ThrowsAsync<IdempotencyConflictException>(() => repository.UpgradeCardAsync(
                player, id, "upgrade-" + id, new(card.Version + 1), ct));
            await Assert.ThrowsAsync<DomainValidationException>(() => repository.UpgradeCardAsync(
                player, id, "stale-" + id, request, ct));
        }
        Assert.Equal(4L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='card.upgrade'", player));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Fourth_and_fifth_levels_consume_souls_without_card_copies()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        var card = (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == "C01");
        for (var level = 1; level <= 3; level++)
            card = (await repository.UpgradeCardAsync(player, card.CardId, "level-" + level, new(card.Version), ct)).Card;
        Assert.True(card.CanUpgrade);
        Assert.Equal(0, card.UpgradeCopyCost);
        for (var level = 4; level <= 5; level++)
        {
            var request = new CardMutationRequest(card.Version);
            var upgraded = await repository.UpgradeCardAsync(player, card.CardId, "level-" + level, request, ct);
            Assert.Equal(0, upgraded.ConsumedCopies);
            Assert.Equal(1, upgraded.Card.CopyCount);
            Assert.Equal(level, upgraded.Card.Level);
            Assert.Equal(upgraded, await repository.UpgradeCardAsync(player, card.CardId, "level-" + level, request, ct));
            card = upgraded.Card;
        }
        Assert.False(card.CanUpgrade);
        Assert.Null(card.NextEffect);
        Assert.Equal(0, card.UpgradeCost);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.UpgradeCardAsync(
            player, card.CardId, "no-sixth-level", new(card.Version), ct));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Insufficient_souls_roll_back_and_concurrent_upgrade_replays_spend_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database, 0);
        var repository = new ProgressionRepository(database.DataSource);
        var original = (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == "MAG-01");
        var request = new CardMutationRequest(original.Version);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.UpgradeCardAsync(
            player, original.CardId, "insufficient", request, ct));
        Assert.Equal(original, (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == original.CardId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1", player));
        await using (var fund = database.DataSource.CreateCommand("UPDATE player_materials SET mage_soul=8 WHERE player_id=$1"))
        {
            fund.Parameters.AddWithValue(player);
            await fund.ExecuteNonQueryAsync(ct);
        }
        var results = await Task.WhenAll(Enumerable.Range(0, 4).Select(_ =>
            repository.UpgradeCardAsync(player, original.CardId, "once", request, ct)));
        Assert.All(results, result => Assert.Equal(results[0], result));
        Assert.Equal(0, results[0].Materials.MageSoul);
        Assert.Equal(1, results[0].Card.Level);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1", player));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Preparation_freezes_trained_level_despite_later_upgrades()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        var card = (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == "C01");
        card = (await repository.UpgradeCardAsync(player, card.CardId, "first-level", new(card.Version), ct)).Card;
        var deck = (await repository.GetDecksAsync(player, ct)).Single(deck => deck.HeroClass == HeroClassDto.Mage);
        var loadout = await repository.GetLoadoutAsync(player, HeroClass.Mage, ct);
        var preparations = new PreparationRepository(database.DataSource, TimeProvider.System);
        var prepared = await preparations.CreateAsync(player, "frozen-levels", new(
            HeroClassDto.Mage, deck.Version, loadout!.EquipmentIds, BackpackTierDto.Free, [], 0, "Standard"), ct);
        Assert.Equal(CreatePreparationStatus.Created, prepared.Status);
        var snapshot = prepared.Preparation!.Snapshot;
        Assert.Equal(20, snapshot.CardLevels!.Count);
        var snapshotCard = Assert.Single(
            snapshot.CardIds.Select((id, index) => (id, level: snapshot.CardLevels[index])),
            item => item.id == "C01");
        Assert.Equal(1, snapshotCard.level);
        await repository.UpgradeCardAsync(player, card.CardId, "after-preparation", new(card.Version), ct);
        var restored = await new PreparationRepository(database.DataSource, TimeProvider.System).GetActiveAsync(player, ct);
        Assert.Equal(snapshot.CardLevels, restored!.Snapshot.CardLevels);
        Assert.Equal(2, (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == "C01").Level);
    }

    private static async Task<Guid> CreatePlayerAsync(PostgresTestSchema database, long souls = 10000)
    {
        var ct = TestContext.Current.CancellationToken;
        var now = DateTimeOffset.UtcNow;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var player = await identity.SignInLocalAsync(Guid.NewGuid().ToString("N"), "Upgrade player",
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await using var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET warrior_soul=$1,priest_soul=$1,mage_soul=$1,guardian_soul=$1 WHERE player_id=$2");
        command.Parameters.AddWithValue(souls);
        command.Parameters.AddWithValue(player.UserId);
        await command.ExecuteNonQueryAsync(ct);
        return player.UserId;
    }

    private static long Balance(MaterialsResponse materials, string currency) => currency switch
    {
        "WarriorSoul" => materials.WarriorSoul, "PriestSoul" => materials.PriestSoul,
        "MageSoul" => materials.MageSoul, "GuardianSoul" => materials.GuardianSoul,
        _ => throw new InvalidOperationException("Unexpected soul currency.")
    };
}
