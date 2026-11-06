using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;

namespace FantasyCard.Server.Tests.Persistence;

/// <summary>Actual F01 preparation inputs and cancellation; deliberately no matchmaking, map or encounter clock.</summary>
public sealed class PostgresFirstFortnightPreparationTests
{
    private static readonly int[] Days = [1, 7, 14];
    private static readonly int[] Hours = [9, 18];
    private static readonly BackpackTierDto[] PaidTiers = [BackpackTierDto.Advanced, BackpackTierDto.Top];
    private static readonly int[] AdvancedSafeSlots = [2];
    private static readonly int[] TopSafeSlots = [0, 1, 35];
    private static readonly JsonSerializerOptions EvidenceJson = new() { WriteIndented = true };
    public static bool Enabled => PostgresMigrationTests.HasTestDatabase
        && Environment.GetEnvironmentVariable("FANTASYCARD_RUN_F01_PREPARATION") == "1";

    [Fact(Skip = "Explicit isolated F01 preparation preflight, no gameplay starts.", SkipUnless = nameof(Enabled))]
    [Trait("Category", "PostgresIntegration")]
    public async Task NineDeclaredActorsBindActualPreparationsAtDay1Day7Day14WithoutStartingMaps()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("f01-prepared-calendar", new(2026, 11, 1), config.Version,
            "season-equipment-v1", highestOpenDifficulty: 5);
        var clock = new Clock(season.StartsAtUtc.AddHours(9));
        var seasons = new SeasonRepository(db.DataSource, clock);
        Assert.True(await seasons.PublishAsync(season, config.ContentHash, ct));
        var repository = new PreparationRepository(db.DataSource, clock);
        var controller = new SeasonFirstFortnightPreparedController(repository, clock, season);
        var accounts = new List<(SeasonFirstFortnightInputsTests.Actor Actor, Guid Player, long DeckVersion)>();
        foreach (var actor in SeasonFirstFortnightInputsTests.DeclareActors())
        {
            var player = await AccountAsync(db, clock.Now);
            if (actor.HistoricalOwnershipAssumed) await DeclareHistoricalOwnershipAsync(db, player, actor);
            await seasons.EnsurePlayerAsync(player, season.ContextFor(0), ct);
            var version = await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=$2", player, (short)actor.Hero);
            accounts.Add((actor, player, version));
            var unavailablePotion = await repository.CreateAsync(player, "f01-potion-unavailable", Request(actor, version, season.SeasonId, potionCount: 1), ct);
            Assert.Equal(CreatePreparationStatus.AssetUnavailable, unavailablePotion.Status);
            await Assert.ThrowsAsync<DomainValidationException>(() => repository.CreateAsync(player, "f01-locked-d1",
                Request(actor, version, season.SeasonId) with { Difficulty = "D1" }, ct));
            Assert.Equal(0, await seasons.GetUnlockedDifficultyAsync(player, season.SeasonId, ct));
            Assert.Null(await repository.GetActiveAsync(player, ct));
        }
        var observations = new List<object>();
        foreach (var day in Days)
        foreach (var hour in Hours)
        {
            clock.Now = season.StartsAtUtc.AddDays(day - 1).AddHours(hour);
            foreach (var (actor, player, version) in accounts)
            {
                var requestId = $"f01-prep-{day}-{hour}";
                var request = Request(actor, version, season.SeasonId);
                var created = await repository.CreateAsync(player, requestId, request, ct);
                Assert.Equal(CreatePreparationStatus.Created, created.Status);
                var preparation = Assert.IsType<PreparationResponse>(created.Preparation);
                var replay = await repository.CreateAsync(player, requestId, request, ct);
                Assert.Equal(CreatePreparationStatus.Replayed, replay.Status);
                Assert.Equal(JsonSerializer.Serialize(preparation), JsonSerializer.Serialize(replay.Preparation));
                var bound = await controller.BindAsync(actor, player, preparation.PreparationId, clock.Now, 410000 + day * 100 + hour, ct);
                var state = bound.UnstartedRoom.CapturePlayer(player);
                Assert.NotNull(state.Inventory);
                Assert.Equal(clock.Now, bound.ScheduledAtUtc);
                Assert.Equal(season.ContextFor(0), bound.Context);
                Assert.Equal(clock.Now, preparation.CreatedAt);
                Assert.Equal(clock.Now.AddMinutes(30), preparation.ExpiresAt);
                Assert.Equal(0, state.Combat.WeaponLevel);
                Assert.All(bound.Snapshot.CardLevels!, level => Assert.Equal(0, level));
                Assert.All(bound.Snapshot.ActualCardLevels!, level => Assert.Equal(actor.PermanentWeaponLevel, level));
                Assert.Equal(actor.PermanentWeaponLevel, bound.Snapshot.ActualClassWeaponLevel);
                Assert.Equal(config.Backpack("Free").Capacity, state.Inventory.Capacity);
                Assert.Empty(state.Inventory.Items);
                Assert.Empty(bound.Snapshot.SafeSlotIndexes);
                Assert.Equal(TimeSpan.Zero, bound.UnstartedRoom.Elapsed);
                Assert.Null(state.Pve);
                observations.Add(new { actor.Id, day, hour, bound.ScheduledAtUtc, preparation.PreparationId,
                    snapshot = bound.Snapshot, state = new { state.Combat.MaximumHp, state.Combat.WeaponLevel,
                        state.Inventory.Capacity, state.Inventory.SafeSlots }, original_historical_fixture = actor.HistoricalOwnershipAssumed,
                    actual_gameplay_starts = 0, matched_or_hold_consumed = false });
                Assert.Equal(CancelPreparationStatus.Cancelled, await repository.CancelAsync(player, preparation.PreparationId, requestId + "-cancel", ct));
                Assert.Equal(CancelPreparationStatus.Cancelled, await repository.CancelAsync(player, preparation.PreparationId, requestId + "-cancel", ct));
                Assert.Null(await repository.GetActiveAsync(player, ct));
                Assert.Equal(0L, await ActiveHoldsAsync(db, player));
            }
        }
        Assert.Equal(54, observations.Count);
        foreach (var (_, player, _) in accounts)
        {
            Assert.Equal(0L, await db.ScalarAsync<long>("SELECT gold+diamond FROM player_wallets WHERE player_id=$1", player));
            Assert.Equal(0L, await db.ScalarAsync<long>("SELECT gold+equipment_fragments+blueprint_marks+orange_blueprint_marks FROM player_season_wallets WHERE player_id=$1 AND season_id=$2", player, season.SeasonId));
            Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1", player));
        }
        Write("calendar-preparations.original.json", new { observations, accounts = 9, preparation_bindings = 54,
            original_player_unlocked_difficulty = 0, candidate_season_global_maximum = 5,
            maximum_is_a_fixture_not_a_release_recommendation = true, actual_gameplay_starts = 0 });
    }

    [Fact(Skip = "Explicit F01 prepared-asset control fixture, no gameplay starts or cohort income.", SkipUnless = nameof(Enabled))]
    [Trait("Category", "PostgresIntegration")]
    public async Task PreparedControllerRetainsLegalArmorAndActualBagPotionHoldsAndRejectsMismatchedInputs()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("f01-prepared-controls", new(2026, 11, 1), config.Version, "season-equipment-v1");
        var clock = new Clock(season.StartsAtUtc.AddHours(9));
        var seasons = new SeasonRepository(db.DataSource, clock);
        Assert.True(await seasons.PublishAsync(season, config.ContentHash, ct));
        var player = await AccountAsync(db, clock.Now);
        var actor = SeasonFirstFortnightInputsTests.DeclareActors().Single(value => value.Cohort == "novice" && value.Hero == HeroClass.Mage);
        await seasons.EnsurePlayerAsync(player, season.ContextFor(0), ct);
        var item = Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db, """
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES($1,$2,'Head','Blue',5,'Inventory',$3,'Water','DrawInterval',$4,$4,'ActiveSeason','season-equipment-v1','AdminGrant',0)
            """, item, player, clock.Now, season.SeasonId);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_consumables SET health_potion_count=1,advanced_bag_count=1,top_bag_count=1 WHERE player_id=$1", player);
        var worn = await new ProgressionRepository(db.DataSource, clock).SaveLoadoutAsync(player, HeroClass.Mage,
            new Guid?[] { item, null, null, null, null }, "f01-control-equip", 1, clock.Now, ct);
        Assert.Equal(SaveLoadoutStatus.Updated, worn.Status);
        var repository = new PreparationRepository(db.DataSource, clock);
        var controller = new SeasonFirstFortnightPreparedController(repository, clock, season);
        var observations = new List<object>();
        foreach (var tier in PaidTiers)
        {
            var safeSlots = tier == BackpackTierDto.Advanced ? AdvancedSafeSlots : TopSafeSlots;
            var request = Request(actor, 1, season.SeasonId, potionCount: 1) with
                { EquipmentIds = new Guid?[] { item, null, null, null, null }, BackpackTier = tier, SafeSlotIndexes = safeSlots };
            var result = await repository.CreateAsync(player, "f01-control-" + tier, request, ct);
            Assert.True(result.Status == CreatePreparationStatus.Created, result.Detail);
            var preparation = Assert.IsType<PreparationResponse>(result.Preparation);
            var bound = await controller.BindAsync(actor, player, preparation.PreparationId, clock.Now, 420000, ct);
            var state = bound.UnstartedRoom.CapturePlayer(player);
            Assert.NotNull(state.Inventory);
            Assert.Equal(0, state.Combat.WeaponLevel);
            Assert.Equal(5, Assert.Single(state.WornArmor!).Equipment!.Level);
            Assert.Equal(item.ToString("D"), Assert.Single(state.WornArmor!).ItemId);
            Assert.Equal(config.Backpack(tier.ToString()).Capacity, state.Inventory.Capacity);
            Assert.Equal(safeSlots, state.Inventory.SafeSlotIndexes);
            Assert.Equal(ExplorationItemKind.HealthPotion, Assert.Single(state.Inventory.Items).Kind);
            Assert.Equal(TimeSpan.Zero, bound.UnstartedRoom.Elapsed);
            var badLevels = preparation with { Snapshot = preparation.Snapshot with { CardLevels = Enumerable.Repeat(5, 20).ToArray() } };
            Assert.Throws<InvalidOperationException>(() => SeasonFirstFortnightPreparedController.BindCaptured(actor, player, badLevels, season, clock.Now, 420000));
            var badBag = preparation with { Snapshot = preparation.Snapshot with { BackpackCapacity = 20 } };
            Assert.Throws<InvalidOperationException>(() => SeasonFirstFortnightPreparedController.BindCaptured(actor, player, badBag, season, clock.Now, 420000));
            var badSeason = preparation with { Snapshot = preparation.Snapshot with { Season = preparation.Snapshot.Season! with { SeasonId = "another-season" } } };
            Assert.Throws<InvalidOperationException>(() => SeasonFirstFortnightPreparedController.BindCaptured(actor, player, badSeason, season, clock.Now, 420000));
            await Assert.ThrowsAsync<InvalidOperationException>(() => controller.BindAsync(actor, player, Guid.NewGuid(), clock.Now, 420000, ct));
            observations.Add(new { tier, preparation.PreparationId, snapshot = preparation.Snapshot,
                actual_room_armor_level = Assert.Single(state.WornArmor!).Equipment!.Level,
                state.Inventory.Capacity, state.Inventory.SafeSlotIndexes, prepared_potions = state.Inventory.Items.Count,
                controls_are_explicit_fixture_assets_not_cohort_income = true, actual_gameplay_starts = 0 });
            Assert.Equal(CancelPreparationStatus.Cancelled, await repository.CancelAsync(player, preparation.PreparationId, "f01-control-cancel-" + tier, ct));
            Assert.Equal(0L, await ActiveHoldsAsync(db, player));
            Assert.Equal(1, await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player));
            Assert.Equal("Equipped", await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", item));
        }
        var expired = await repository.CreateAsync(player, "f01-expired-control", Request(actor, 1, season.SeasonId), ct);
        var expiring = Assert.IsType<PreparationResponse>(expired.Preparation);
        clock.Now = clock.Now.AddMinutes(31);
        await Assert.ThrowsAsync<InvalidOperationException>(() => controller.BindAsync(actor, player, expiring.PreparationId, clock.Now, 420000, ct));
        await repository.CancelAsync(player, expiring.PreparationId, "f01-expired-cancel", ct);
        Assert.Equal(0L, await ActiveHoldsAsync(db, player));
        Write("prepared-controls.original.json", new { observations, mismatch_levels_and_bag_rejected = true,
            different_preparation_and_expired_preparation_rejected = true, held_assets_not_consumed_by_binding = true,
            cohort_income_merged = false, actual_gameplay_starts = 0 });
    }

    private static CreatePreparationRequest Request(SeasonFirstFortnightInputsTests.Actor actor, long version,
        string seasonId, int potionCount = 0) => new((HeroClassDto)(int)actor.Hero, version,
            new Guid?[5], BackpackTierDto.Free, Array.Empty<int>(), potionCount, "D0", seasonId);

    private static async Task<Guid> AccountAsync(PostgresTestSchema db, DateTimeOffset now)
    {
        var identity = new IdentityRepository(db.DataSource, new PlayerProvisioningService());
        var profile = await identity.SignInLocalAsync("f01-owned-device", "f01-" + Guid.NewGuid().ToString("N")[..12],
            RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), TestContext.Current.CancellationToken);
        return profile.UserId;
    }

    private static async Task DeclareHistoricalOwnershipAsync(PostgresTestSchema db, Guid player, SeasonFirstFortnightInputsTests.Actor actor)
    {
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_cards SET unlocked=true,copy_count=GREATEST(copy_count,1),level=5,version=version+1 WHERE player_id=$1 AND card_id=ANY($2)", player, actor.Cards);
        await CraftingTestInputs.SqlAsync(db, "UPDATE class_weapons SET level=5,version=version+1 WHERE player_id=$1 AND hero_class=$2", player, (short)actor.Hero);
        await CraftingTestInputs.SqlAsync(db, "DELETE FROM player_deck_cards c USING player_decks d WHERE d.deck_id=c.deck_id AND d.player_id=$1 AND d.hero_class=$2", player, (short)actor.Hero);
        for (var index = 0; index < actor.Cards.Length; index++)
            await CraftingTestInputs.SqlAsync(db, "INSERT INTO player_deck_cards(deck_id,card_id,slot_index) SELECT deck_id,$1,$4 FROM player_decks WHERE player_id=$2 AND hero_class=$3",
                actor.Cards[index], player, (short)actor.Hero, index);
        await CraftingTestInputs.SqlAsync(db, "UPDATE player_decks SET version=version+1 WHERE player_id=$1 AND hero_class=$2", player, (short)actor.Hero);
    }

    private static Task<long> ActiveHoldsAsync(PostgresTestSchema db, Guid player) => db.ScalarAsync<long>("""
        SELECT count(*) FROM preparation_assets a JOIN preparations p USING(preparation_id)
        WHERE p.player_id=$1 AND p.status IN('Active','Queued','Matched')
        """, player);

    private static void Write(string name, object value)
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_F01_PREPARATION_OUTPUT")
            ?? throw new InvalidOperationException("New owned F01 preparation output required.");
        Directory.CreateDirectory(output);
        var path = Path.Combine(output, name);
        Assert.False(File.Exists(path));
        File.WriteAllText(path, JsonSerializer.Serialize(value, EvidenceJson));
    }

    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
