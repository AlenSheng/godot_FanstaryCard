using System.Security.Cryptography;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonMatchmakingTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task InterleavedDifficultiesNeverShareAMatchAndLaunchReplayPreservesThePinnedContext()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        var prepared = new List<(Prepared Value, int Difficulty)>();
        for (var i = 0; i < 4; i++)
        {
            var difficulty = i % 2;
            var value = await PrepareAsync(db, clock, season, difficulty);
            prepared.Add((value, difficulty));
            await repository.EnqueueAsync(value.Player, "queue", new(value.Preparation.PreparationId), Ct);
            clock.Now = clock.Now.AddSeconds(1);
        }
        Assert.Null(await repository.TryCreateMatchAsync(Ct));
        clock.Now = clock.Now.AddSeconds(31);
        var pending = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal(prepared.Where(p => p.Difficulty == 0).Select(p => p.Value.Player).Order(), pending.PlayerIds.Order());
        foreach (var player in pending.PlayerIds) await repository.MarkReadyAsync(player, clock.Now, Ct);
        var launch = Assert.IsType<ReadyMatchLaunch>(await repository.ClaimReadyMatchAsync(clock.Now, Ct));
        Assert.Equal(season.ContextFor(0), launch.Assignment.Season);
        Assert.Equal(season.ConfigVersion, launch.Assignment.ConfigVersion);
        Assert.Equal(4, launch.Assignment.Players.Count);
        Assert.All(launch.Assignment.Players.Where(p => !p.IsBot), player =>
        {
            Assert.Equal(0, player.WeaponLevel);
            Assert.All(player.CardLevels!, level => Assert.Equal(0, level));
        });
        Assert.Equal("D0", await db.ScalarAsync<string>("SELECT difficulty FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements m JOIN equipments e ON e.instance_id=m.item_id WHERE m.reason='match.start' AND m.season_id='current' AND e.origin_season_id='current' AND e.asset_scope='ActiveSeason'"));
        var replay = Assert.IsType<ReadyMatchLaunch>(await new MatchmakingRepository(db.DataSource, clock, metrics).ClaimReadyMatchAsync(clock.Now, Ct));
        Assert.Equal(launch.Assignment.Season, replay.Assignment.Season);
        Assert.Equal(launch.Assignment.Players.Select(p => p.PlayerId).Order(), replay.Assignment.Players.Select(p => p.PlayerId).Order());
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='match.start'"));
        Assert.Equal(0, await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", pending.PlayerIds[0]));
        var next = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal(prepared.Where(p => p.Difficulty == 1).Select(p => p.Value.Player).Order(), next.PlayerIds.Order());
        Assert.Equal("D1", await db.ScalarAsync<string>("SELECT difficulty FROM matches WHERE match_id=$1", next.MatchId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AnOlderIncompleteGroupDoesNotBlockAnotherFullDifficultyGroup()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        var waiting = await PrepareAsync(db, clock, season, 0);
        await repository.EnqueueAsync(waiting.Player, "queue", new(waiting.Preparation.PreparationId), Ct);
        clock.Now = clock.Now.AddSeconds(1);
        var players = new List<Guid>();
        for (var i = 0; i < 4; i++)
        {
            var ready = await PrepareAsync(db, clock, season, 1);
            players.Add(ready.Player);
            await repository.EnqueueAsync(ready.Player, "queue", new(ready.Preparation.PreparationId), Ct);
        }
        var pending = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal(players.Order(), pending.PlayerIds.Order());
        Assert.Null(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal("Queued", await db.ScalarAsync<string>("SELECT status FROM preparations WHERE preparation_id=$1", waiting.Preparation.PreparationId));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ConcurrentMatchersNeverAssignATicketTwiceOrMixDifficulties()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        var players = new List<Guid>();
        for (var i = 0; i < 8; i++)
        {
            var prepared = await PrepareAsync(db, clock, season, i % 2, equipment: false);
            players.Add(prepared.Player);
            await repository.EnqueueAsync(prepared.Player, "queue", new(prepared.Preparation.PreparationId), Ct);
        }
        clock.Now = clock.Now.AddSeconds(31);
        var results = (await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => repository.TryCreateMatchAsync(Ct)))).OfType<PendingMatch>().ToList();
        while (await repository.TryCreateMatchAsync(Ct) is { } remainder) results.Add(remainder);
        Assert.Equal(players.Order(), results.SelectMany(m => m.PlayerIds).Order());
        Assert.Equal(8L, await db.ScalarAsync<long>("SELECT count(*) FROM match_players WHERE NOT is_bot"));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM match_players mp JOIN preparations p ON p.preparation_id=mp.preparation_id JOIN matches m ON m.match_id=mp.match_id WHERE m.season_id IS DISTINCT FROM p.season_id OR m.difficulty <> 'D'||p.difficulty_id::text OR m.config_version<>p.config_version OR m.ruleset_id<>p.ruleset_id OR m.stats_version<>p.stats_version"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task QueuedSeasonEndCancelsTheTicketAndReleasesEquipmentWithoutSpendingPotions()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.EndsAtUtc.AddSeconds(-10));
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var value = await PrepareAsync(db, clock, season, 0);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        var ticket = await repository.EnqueueAsync(value.Player, "queue", new(value.Preparation.PreparationId), Ct);
        clock.Now = season.EndsAtUtc;
        Assert.Null(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal("Cancelled", (await repository.GetTicketAsync(value.Player, ticket.TicketId, Ct)).Status);
        Assert.Equal("Expired", await db.ScalarAsync<string>("SELECT status FROM preparations WHERE preparation_id=$1", value.Preparation.PreparationId));
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND season_id='current' AND reason IN ('preparation.lock','preparation.release')", value.Player));
        await AssertEquipmentAndPotionsAsync(db, value, "Equipped", 1);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task FirstSeasonStartInvalidatesBothLegacyQueueAndUnqueuedLegacyPreparation()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc.AddSeconds(-10));
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var queued = await PrepareAsync(db, clock, null, 0);
        var active = await PrepareAsync(db, clock, null, 0);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        await repository.EnqueueAsync(queued.Player, "queue", new(queued.Preparation.PreparationId), Ct);
        clock.Now = season.StartsAtUtc;
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.EnqueueAsync(active.Player, "queue", new(active.Preparation.PreparationId), Ct));
        Assert.Null(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM matches"));
        await AssertEquipmentAndPotionsAsync(db, queued, "Equipped", 1);
        await AssertEquipmentAndPotionsAsync(db, active, "Equipped", 1);
        Assert.Equal(2L, await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE status='Expired'"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AStartingMatchAtSeasonEndIsAbortedWithoutCreatingARoomOrConsumingAssets()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.EndsAtUtc.AddSeconds(-45));
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var value = await PrepareAsync(db, clock, season, 0);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        await repository.EnqueueAsync(value.Player, "queue", new(value.Preparation.PreparationId), Ct);
        clock.Now = clock.Now.AddSeconds(31);
        var pending = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(Ct));
        Assert.Equal(season.EndsAtUtc, pending.ReadyDeadline);
        await repository.MarkReadyAsync(value.Player, clock.Now, Ct);
        clock.Now = season.EndsAtUtc;
        await using var rooms = new RoomRegistry(clock);
        var snapshots = new RoomSnapshotRepository(db.DataSource, clock, metrics);
        using var coordinator = new RoomReadyCoordinator(repository, rooms, snapshots, new RealtimeEventStore(clock),
            new ConnectionRegistry(), clock, NullLogger<RoomReadyCoordinator>.Instance);
        Assert.True(await coordinator.ProcessNextAsync(clock.Now, Ct));
        Assert.Empty(rooms.GetRoomIds());
        Assert.Equal("Aborted", await db.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        Assert.Equal("Removed", await db.ScalarAsync<string>("SELECT state FROM match_players WHERE match_id=$1 AND player_id=$2", pending.MatchId, value.Player));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='match.start'"));
        Assert.False(await coordinator.ProcessNextAsync(clock.Now, Ct));
        await AssertEquipmentAndPotionsAsync(db, value, "Equipped", 1);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AnAdmittedLaunchingMatchRecoversAfterSeasonEndWithNoAdditionalAssetSpend()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.EndsAtUtc.AddMinutes(-2));
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var value = await PrepareAsync(db, clock, season, 2);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        await repository.EnqueueAsync(value.Player, "queue", new(value.Preparation.PreparationId), Ct);
        clock.Now = clock.Now.AddSeconds(31);
        await repository.TryCreateMatchAsync(Ct);
        await repository.MarkReadyAsync(value.Player, clock.Now, Ct);
        var launch = Assert.IsType<ReadyMatchLaunch>(await repository.ClaimReadyMatchAsync(clock.Now, Ct));
        clock.Now = season.EndsAtUtc;
        var replay = Assert.IsType<ReadyMatchLaunch>(await new MatchmakingRepository(db.DataSource, clock, metrics).ClaimReadyMatchAsync(clock.Now, Ct));
        Assert.False(replay.Aborted);
        Assert.Equal(season.ContextFor(2), replay.Assignment.Season);
        Assert.Equal(launch.Assignment.Players.Select(p => p.PlayerId).Order(), replay.Assignment.Players.Select(p => p.PlayerId).Order());
        Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='match.start'"));
        await AssertEquipmentAndPotionsAsync(db, value, "InMatchEquipped", 0);
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("context")]
    [InlineData("projection")]
    [Trait("Category", "PostgresIntegration")]
    public async Task CorruptedPreparedContextOrProjectionCannotConsumeAssets(string corruption)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.StartsAtUtc);
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var value = await PrepareAsync(db, clock, season, 0);
        using var metrics = new ServerMetrics();
        var repository = new MatchmakingRepository(db.DataSource, clock, metrics);
        await repository.EnqueueAsync(value.Player, "queue", new(value.Preparation.PreparationId), Ct);
        clock.Now = clock.Now.AddSeconds(31);
        await repository.TryCreateMatchAsync(Ct);
        await repository.MarkReadyAsync(value.Player, clock.Now, Ct);
        await using (var change = db.DataSource.CreateCommand(corruption == "context"
            ? "UPDATE preparations SET snapshot_json=jsonb_set(snapshot_json,'{season,statsVersion}','\"wrong\"') WHERE preparation_id=$1"
            : "UPDATE preparations SET snapshot_json=jsonb_set(snapshot_json,'{classWeaponLevel}','5') WHERE preparation_id=$1"))
        {
            change.Parameters.AddWithValue(value.Preparation.PreparationId); await change.ExecuteNonQueryAsync(Ct);
        }
        await Assert.ThrowsAsync<InvalidOperationException>(() => repository.ClaimReadyMatchAsync(clock.Now, Ct));
        Assert.Equal("Ready", await db.ScalarAsync<string>("SELECT state FROM match_players WHERE player_id=$1", value.Player));
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='match.start'"));
        await AssertEquipmentAndPotionsAsync(db, value, "PreparationLocked", 1);
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task AReservationWaitingForAPlayerLockCannotSpendAssetsAfterSeasonEnd()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var season = Define(); var clock = new Clock(season.EndsAtUtc.AddMinutes(-2));
        await new SeasonRepository(db.DataSource, clock).PublishAsync(season, new string('a', 64), Ct);
        var value = await PrepareAsync(db, clock, season, 0);
        using var metrics = new ServerMetrics();
        var applicationName = "season-claim-" + Guid.NewGuid().ToString("N");
        var settings = new NpgsqlConnectionStringBuilder(db.ConnectionString) { ApplicationName = applicationName };
        await using var source = NpgsqlDataSource.Create(settings.ConnectionString);
        var repository = new MatchmakingRepository(source, clock, metrics);
        await repository.EnqueueAsync(value.Player, "queue", new(value.Preparation.PreparationId), Ct);
        clock.Now = clock.Now.AddSeconds(31);
        var pending = Assert.IsType<PendingMatch>(await repository.TryCreateMatchAsync(Ct));
        await repository.MarkReadyAsync(value.Player, clock.Now, Ct);
        await using var blocker = await db.DataSource.OpenConnectionAsync(Ct);
        await using var transaction = await blocker.BeginTransactionAsync(Ct);
        await using (var hold = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", blocker, transaction))
        {
            hold.Parameters.AddWithValue(value.Player); await hold.ExecuteScalarAsync(Ct);
        }
        var claim = repository.ClaimReadyMatchAsync(clock.Now, Ct);
        var until = DateTimeOffset.UtcNow.AddSeconds(10);
        bool waiting;
        do
        {
            waiting = await db.ScalarAsync<bool>("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=$1 AND wait_event_type='Lock')", applicationName);
            if (!waiting) await Task.Delay(25, Ct);
        } while (!waiting && DateTimeOffset.UtcNow < until);
        Assert.True(waiting, "The owned claimant must actually wait for the held player lock.");
        clock.Now = season.EndsAtUtc;
        await transaction.CommitAsync(Ct);
        var rejected = await Assert.ThrowsAsync<MatchReadyException>(() => claim);
        Assert.Equal("CONTEXT_UNAVAILABLE", rejected.Code);
        Assert.Equal("Starting", await db.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", pending.MatchId));
        await AssertEquipmentAndPotionsAsync(db, value, "PreparationLocked", 1);
        var aborted = Assert.IsType<ReadyMatchLaunch>(await repository.ClaimReadyMatchAsync(clock.Now, Ct));
        Assert.True(aborted.Aborted);
        await AssertEquipmentAndPotionsAsync(db, value, "Equipped", 1);
    }

    private static SeasonDefinition Define() => SeasonDefinition.FromCalendarDays("current", new DateOnly(2026, 11, 2),
        GameConfigCatalog.Current.Version, "season-equipment-v1", highestOpenDifficulty: 5);

    private static async Task<Prepared> PrepareAsync(PostgresTestSchema db, Clock clock, SeasonDefinition? season, int difficulty, bool equipment = true)
    {
        var key = Guid.NewGuid().ToString("N");
        var player = (await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            key, "Queue " + key[..12], RandomNumberGenerator.GetBytes(32), clock.Now, clock.Now.AddHours(1), Ct)).UserId;
        if (season is not null)
        {
            await new SeasonRepository(db.DataSource, clock).EnsurePlayerAsync(player, season.ContextFor(0), Ct);
            await using var unlock = db.DataSource.CreateCommand("UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1");
            unlock.Parameters.AddWithValue(player); await unlock.ExecuteNonQueryAsync(Ct);
        }
        await using (var seed = db.DataSource.CreateCommand("""
            WITH weapons AS (
                UPDATE class_weapons SET level=5 WHERE player_id=$1 RETURNING player_id
            ), cards AS (
                UPDATE player_cards SET level=5 WHERE player_id=$1 AND unlocked RETURNING player_id
            )
            UPDATE player_consumables SET health_potion_count=1 WHERE player_id=$1
            """))
        {
            seed.Parameters.AddWithValue(player); await seed.ExecuteNonQueryAsync(Ct);
        }
        Guid? item = equipment ? Guid.NewGuid() : null;
        if (item is not null)
        {
            await using var insert = db.DataSource.CreateCommand("""
                INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
                VALUES ($1,$2,'Head','Blue',0,'Equipped',$3,'Fire',$4,$4,$5,$6,$7,$8)
                """);
            insert.Parameters.AddWithValue(item.Value); insert.Parameters.AddWithValue(player); insert.Parameters.AddWithValue(clock.Now);
            insert.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, (object?)season?.SeasonId ?? DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, season is null ? DBNull.Value : "ActiveSeason");
            insert.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, (object?)season?.StatsVersion ?? DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar, season is null ? DBNull.Value : "NaturalDrop");
            insert.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Smallint, season is null ? DBNull.Value : (short)difficulty);
            await insert.ExecuteNonQueryAsync(Ct);
        }
        var version = await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2", player);
        var result = await new PreparationRepository(db.DataSource, clock).CreateAsync(player, "prepare", new(
            HeroClassDto.Mage, version, [item, null, null, null, null], BackpackTierDto.Free, [], 1,
            season is null ? "Standard" : "D" + difficulty, season?.SeasonId), Ct);
        Assert.Equal(CreatePreparationStatus.Created, result.Status);
        return new(player, result.Preparation!, item);
    }

    private static async Task AssertEquipmentAndPotionsAsync(PostgresTestSchema db, Prepared prepared, string location, int potions)
    {
        Assert.Equal(location, await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", prepared.Equipment!.Value));
        Assert.Equal(potions, await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", prepared.Player));
    }
    private sealed record Prepared(Guid Player, PreparationResponse Preparation, Guid? Equipment);
    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now { get; set; } = now;
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
