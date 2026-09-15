using System.Security.Cryptography;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresCardEconomyTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_codex_craft_and_dismantle_use_each_soul_pool_and_replay_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        var cards = await repository.GetCardsAsync(player, ct);
        Assert.Equal(200, cards.Count);
        Assert.Equal(51, cards.Count(card => card.Unlocked));
        Assert.Equal(149, cards.Count(card => !card.Unlocked && card.CopyCount == 0));
        Assert.All(cards, card => Assert.True(card.CraftCost > 0));

        var candidates = new HeroClass?[] { null, HeroClass.Priest, HeroClass.Mage, HeroClass.Guardian }
            .Select(heroClass => GameConfigCatalog.Current.Cards.First(card =>
                card.IsCodex && card.HeroClass == heroClass && card.Quality == "Purple"))
            .ToArray();
        foreach (var definition in candidates)
        {
            var initial = cards.Single(card => card.CardId == definition.CardId);
            var requestId = "craft-" + definition.CardId;
            var request = new CardMutationRequest(initial.Version);
            var crafted = await repository.MutateCardAsync(player, definition.CardId, requestId, request, true, ct);
            Assert.True(crafted.Card.Unlocked);
            Assert.Equal(1, crafted.Card.CopyCount);
            Assert.Equal(initial.CraftCost, crafted.SoulAmount);
            Assert.Equal(initial.CurrencyKind, crafted.CurrencyKind);
            Assert.Equal(1000 - initial.CraftCost, Balance(crafted.Materials, crafted.CurrencyKind));
            Assert.Equal(crafted, await repository.MutateCardAsync(player, definition.CardId, requestId, request, true, ct));
            await Assert.ThrowsAsync<IdempotencyConflictException>(() => repository.MutateCardAsync(
                player, definition.CardId, requestId, new(initial.Version + 1), true, ct));
            await Assert.ThrowsAsync<DomainValidationException>(() => repository.MutateCardAsync(
                player, definition.CardId, requestId + "-stale", request, true, ct));

            var dismantleRequest = new CardMutationRequest(crafted.Card.Version);
            var dismantled = await repository.MutateCardAsync(player, definition.CardId, "dismantle-" + definition.CardId, dismantleRequest, false, ct);
            Assert.False(dismantled.Card.Unlocked);
            Assert.Equal(0, dismantled.Card.CopyCount);
            Assert.Equal(initial.CraftCost / 4, dismantled.SoulAmount);
            Assert.Equal(1000 - initial.CraftCost + initial.CraftCost / 4, Balance(dismantled.Materials, dismantled.CurrencyKind));
            Assert.Equal(dismantled, await repository.MutateCardAsync(player, definition.CardId,
                "dismantle-" + definition.CardId, dismantleRequest, false, ct));
            Assert.Equal(2L, await database.ScalarAsync<long>(
                "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND currency=$2", player, crafted.CurrencyKind));
        }
        Assert.True((await new EconomyReconciliationRepository(database.DataSource).InspectAsync(ct)).IsHealthy);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Saved_decks_are_protected_and_owned_cards_cannot_be_acquired_again()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        var decks = await repository.GetDecksAsync(player, ct);
        var cardId = decks[0].CardIds[0];
        var original = (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == cardId);
        Assert.False(original.CanDismantle);
        Assert.Contains("saved deck", original.BlockedReason!, StringComparison.Ordinal);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.MutateCardAsync(
            player, cardId, "protected", new(original.Version), false, ct));
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.MutateCardAsync(
            player, cardId, "duplicate", new(original.Version), true, ct));
        Assert.Equal(decks.SelectMany(deck => deck.CardIds),
            (await repository.GetDecksAsync(player, ct)).SelectMany(deck => deck.CardIds));
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Cumulative_upgrade_spend_is_refunded_once_and_last_copy_resets_level()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database);
        var repository = new ProgressionRepository(database.DataSource);
        var cardId = GameConfigCatalog.Current.Cards.First(card => card.IsCodex && card.Quality == "Blue").CardId;
        await using (var seed = database.DataSource.CreateCommand(
            "UPDATE player_cards SET unlocked=true,copy_count=1,level=3 WHERE player_id=$1 AND card_id=$2"))
        {
            seed.Parameters.AddWithValue(player);
            seed.Parameters.AddWithValue(cardId);
            await seed.ExecuteNonQueryAsync(ct);
        }
        var trained = (await repository.GetCardsAsync(player, ct)).Single(card => card.CardId == cardId);
        Assert.Equal(84, trained.UpgradeSoulSpent);
        Assert.Equal(33, trained.DismantleRefund);
        var last = await repository.MutateCardAsync(player, cardId, "remove-trained", new(trained.Version), false, ct);
        Assert.Equal(33, last.SoulAmount);
        Assert.Equal(1045, last.Materials.WarriorSoul);
        Assert.Equal(0, last.Card.Level);
        Assert.False(last.Card.Unlocked);
        var recrafted = await repository.MutateCardAsync(player, cardId, "recraft", new(last.Card.Version), true, ct);
        Assert.Equal(0, recrafted.Card.Level);
        Assert.Equal(12, recrafted.Card.DismantleRefund);
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Insufficient_souls_and_concurrent_requests_cannot_duplicate_or_partially_apply()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await CreatePlayerAsync(database, 0);
        var repository = new ProgressionRepository(database.DataSource);
        var card = (await repository.GetCardsAsync(player, ct)).First(item => !item.Unlocked && item.HeroClass is null);
        var request = new CardMutationRequest(card.Version);
        await Assert.ThrowsAsync<DomainValidationException>(() => repository.MutateCardAsync(
            player, card.CardId, "poor", request, true, ct));
        Assert.Equal(card, (await repository.GetCardsAsync(player, ct)).Single(item => item.CardId == card.CardId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1", player));
        await using (var fund = database.DataSource.CreateCommand("UPDATE player_materials SET warrior_soul=$1 WHERE player_id=$2"))
        {
            fund.Parameters.AddWithValue(card.CraftCost);
            fund.Parameters.AddWithValue(player);
            await fund.ExecuteNonQueryAsync(ct);
        }
        var results = await Task.WhenAll(Enumerable.Range(0, 4).Select(_ =>
            repository.MutateCardAsync(player, card.CardId, "same-key", request, true, ct)));
        Assert.All(results, result => Assert.Equal(results[0], result));
        Assert.Equal(0, results[0].Materials.WarriorSoul);
        Assert.Equal(1, results[0].Card.CopyCount);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1", player));
    }

    private static async Task<Guid> CreatePlayerAsync(PostgresTestSchema database, long souls = 1000)
    {
        var ct = TestContext.Current.CancellationToken;
        var now = DateTimeOffset.UtcNow;
        var identity = new IdentityRepository(database.DataSource, new PlayerProvisioningService());
        var profile = await identity.SignInLocalAsync(Guid.NewGuid().ToString("N"), "Card player",
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), ct);
        await using var command = database.DataSource.CreateCommand(
            "UPDATE player_materials SET warrior_soul=$1,priest_soul=$1,mage_soul=$1,guardian_soul=$1 WHERE player_id=$2");
        command.Parameters.AddWithValue(souls);
        command.Parameters.AddWithValue(profile.UserId);
        await command.ExecuteNonQueryAsync(ct);
        return profile.UserId;
    }

    private static long Balance(MaterialsResponse materials, string currency) => currency switch
    {
        "WarriorSoul" => materials.WarriorSoul, "PriestSoul" => materials.PriestSoul,
        "MageSoul" => materials.MageSoul, "GuardianSoul" => materials.GuardianSoul,
        _ => throw new InvalidOperationException("Unexpected currency.")
    };
}
