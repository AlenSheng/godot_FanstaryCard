using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

/// <summary>Budgeted persistent F01 calendar. A failed current case is retained and never automatically restarted.</summary>
public sealed class PostgresFirstFortnightCalendarTests
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    public static bool Enabled => PostgresMigrationTests.HasTestDatabase
        && Environment.GetEnvironmentVariable("FANTASYCARD_RUN_F01_CALENDAR") == "1";

    public sealed class ActorState
    {
        public string Id { get; set; } = "";
        public Guid Player { get; set; }
        public int ConsecutiveDeaths { get; set; }
        public bool Censored { get; set; }
    }
    public sealed class Progress
    {
        public string Task { get; set; } = "season-balance-20261102-f01-calendar";
        public string Schema { get; set; } = "";
        public string ConfigVersion { get; set; } = "";
        public string ContentHash { get; set; } = "";
        public List<ActorState> Actors { get; set; } = [];
        public int NextIndex { get; set; }
        public string? CurrentCase { get; set; }
        public string Status { get; set; } = "Initializing";
        public List<string> Finished { get; set; } = [];
        public List<string> Skipped { get; set; } = [];
        public string? ManualLobbyResumeCase { get; set; }
    }
    private sealed record Scheduled(string Id, string Actor, int Day, int Hour);

    [Fact(Skip = "Explicit budgeted persistent F01 calendar, not an automatic ordinary test.", SkipUnless = nameof(Enabled))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ActualNineActorsContinueThroughTheOriginalFourteenDayCalendar()
    {
        var budgetPath = Required("FANTASYCARD_F01_BUDGET");
        using var budgetDocument = JsonDocument.Parse(File.ReadAllText(budgetPath));
        var budget = budgetDocument.RootElement;
        var permit = new SeasonFirstFortnightExecutionPermit(budget.GetProperty("approved").GetBoolean(), budget.GetProperty("synthetic").GetBoolean(),
            budget.GetProperty("maximum").GetInt32(), budget.GetProperty("decisionReference").GetString());
        permit.RequireRealLaunch();
        using var plan = JsonDocument.Parse(File.ReadAllText(budget.GetProperty("initial_plan").GetProperty("source").GetString()!));
        var schedule = plan.RootElement.GetProperty("attempts").EnumerateArray().Select(value => new Scheduled(
            value.GetProperty("id").GetString()!, value.GetProperty("actor").GetString()!, value.GetProperty("day").GetInt32(), value.GetProperty("shanghai_start_hour").GetInt32()))
            .OrderBy(value => value.Day).ThenBy(value => value.Hour).ThenBy(value => value.Actor, StringComparer.Ordinal).ToArray();
        Assert.Equal(252, schedule.Length);
        var allowed = schedule.Select(value => value.Id).Concat(budget.GetProperty("smoke_case_ids").EnumerateArray().Select(value => value.GetString()!)).ToHashSet(StringComparer.Ordinal);
        var journal = new SeasonFirstFortnightAttemptJournal(budget.GetProperty("journal").GetString()!, permit.Maximum, allowed);
        var output = Required("FANTASYCARD_F01_CALENDAR_OUTPUT");
        Directory.CreateDirectory(output);
        var control = Required("FANTASYCARD_F01_CALENDAR_CONTROL");
        var limit = int.Parse(Required("FANTASYCARD_F01_CALENDAR_MAX_NEW"), System.Globalization.CultureInfo.InvariantCulture);
        Assert.InRange(limit, 1, 252);
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("f01-calendar-current17", new(2026, 11, 1), config.Version,
            "season-equipment-v1", highestOpenDifficulty: 5);
        var definitions = SeasonFirstFortnightInputsTests.DeclareActors().ToDictionary(value => value.Id, StringComparer.Ordinal);
        var connectionString = Required("FANTASYCARD_TEST_POSTGRES");
        await using var admin = NpgsqlDataSource.Create(connectionString);
        Progress progress;
        if (File.Exists(control))
        {
            progress = JsonSerializer.Deserialize<Progress>(File.ReadAllText(control), Json)!;
            Assert.Equal("season-balance-20261102-f01-calendar", progress.Task);
            Assert.Equal(config.Version, progress.ConfigVersion);
            Assert.Equal(config.ContentHash, progress.ContentHash);
            Assert.Null(progress.CurrentCase); // An interrupted case needs its original handle reconciled, not a new start.
        }
        else
        {
            progress = new() { Schema = "f01_calendar_" + Guid.NewGuid().ToString("N"), ConfigVersion = config.Version, ContentHash = config.ContentHash };
            Save(control, progress);
            await using var create = admin.CreateCommand("CREATE SCHEMA " + progress.Schema);
            await create.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
        }
        Assert.Matches("^f01_calendar_[a-f0-9]{32}$", progress.Schema);
        var settings = new NpgsqlConnectionStringBuilder(connectionString) { SearchPath = progress.Schema, Pooling = false };
        await using var source = NpgsqlDataSource.Create(settings.ConnectionString);
        var ct = TestContext.Current.CancellationToken;
        await new DatabaseMigrator(source, NullLogger<DatabaseMigrator>.Instance).StartAsync(ct);
        if (progress.Actors.Count == 0)
        {
            var clock = new SeasonFirstFortnightTimeProvider(season.StartsAtUtc.AddHours(9));
            await new SeasonRepository(source, clock).PublishAsync(season, config.ContentHash, ct);
            foreach (var actor in definitions.Values.OrderBy(value => value.Id, StringComparer.Ordinal))
            {
                var profile = await new IdentityRepository(source, new PlayerProvisioningService()).SignInLocalAsync("f01-calendar-device",
                    "f01-" + Guid.NewGuid().ToString("N")[..12], RandomNumberGenerator.GetBytes(32), clock.GetUtcNow(), clock.GetUtcNow().AddHours(1), ct);
                if (actor.HistoricalOwnershipAssumed) await DeclareHistory(source, profile.UserId, actor, ct);
                await new SeasonRepository(source, clock).EnsurePlayerAsync(profile.UserId, season.ContextFor(0), ct);
                progress.Actors.Add(new() { Id = actor.Id, Player = profile.UserId });
                Save(control, progress);
            }
            progress.Status = "Ready";
            Save(control, progress);
        }
        Assert.Equal(9, progress.Actors.Count);
        var newStarts = 0;
        while (progress.NextIndex < schedule.Length && newStarts < limit)
        {
            var scheduled = schedule[progress.NextIndex];
            var state = progress.Actors.Single(value => value.Id == scheduled.Actor);
            if (state.Censored)
            {
                progress.Skipped.Add(scheduled.Id); progress.NextIndex++; Save(control, progress); continue;
            }
            var actor = definitions[scheduled.Actor];
            var directory = Path.Combine(output, scheduled.Id);
            if (Directory.Exists(directory))
            {
                Assert.Equal(scheduled.Id, progress.ManualLobbyResumeCase);
                directory = Path.Combine(directory, "reconciled-before-start-r1");
            }
            Assert.False(Directory.Exists(directory));
            Directory.CreateDirectory(directory);
            progress.CurrentCase = scheduled.Id;
            progress.Status = "Lobby";
            Save(control, progress);
            var startsAt = season.StartsAtUtc.AddDays(scheduled.Day - 1).AddHours(scheduled.Hour);
            var clock = new SeasonFirstFortnightTimeProvider(startsAt);
            using var lobbyTrace = new StreamWriter(Path.Combine(directory, "lobby.original.jsonl"));
            var lobby = new SeasonFirstFortnightLobby(source, clock, season, lobbyTrace);
            var before = await lobby.RunAsync(state.Player, actor, scheduled.Id, state.ConsecutiveDeaths, ct);
            Write(directory, "before.original.json", new { scheduled, state.Player, before.Checkpoint });
            var preparations = new PreparationRepository(source, clock);
            var prepared = await preparations.CreateAsync(state.Player, scheduled.Id + "-prepare", before.Request, ct);
            Assert.Equal(CreatePreparationStatus.Created, prepared.Status);
            using var metrics = new ServerMetrics();
            var options = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["Matchmaking:BotFillDelaySeconds"] = "0" }).Build();
            var matchmaking = new MatchmakingRepository(source, clock, metrics, options);
            var snapshots = new RoomSnapshotRepository(source, clock, metrics);
            var red = new SeasonRedDropCoordinator(new SeasonRedMintRepository(source, clock, new PublishedConfigCatalogs(config), options), snapshots);
            await using var rooms = new RoomRegistry(clock, redDrops: red);
            using var ready = new RoomReadyCoordinator(matchmaking, rooms, snapshots, new RealtimeEventStore(clock), new ConnectionRegistry(),
                clock, NullLogger<RoomReadyCoordinator>.Instance);
            var admission = new SeasonFirstFortnightAdmissionController(source, matchmaking, ready, rooms,
                new SeasonFirstFortnightPreparedController(preparations, clock, season), clock, permit, journal);
            progress.Status = "Admission"; Save(control, progress);
            var admitted = await admission.AdmitAsync(scheduled.Id, actor, state.Player, prepared.Preparation!.PreparationId, startsAt, ct);
            newStarts++;
            Write(directory, "admitted.original.json", new { admitted.MatchId, admitted.RoomId, admitted.ActualSeed, admitted.InitialState });
            var policy = new SeasonFirstFortnightMechanicalPlayer(actor, state.Player, admitted.ActualSeed);
            var current = admitted.InitialState;
            var casts = 0; var pvpCasts = 0;
            using (var actions = new StreamWriter(Path.Combine(directory, "actions.original.jsonl")))
            {
                while (current.Elapsed < TimeSpan.FromSeconds(1200) && current.Players.Any(value => value.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)))
                {
                    var action = await admitted.Actor.ExecuteAsync(policy.Decide(clock.GetUtcNow()), ct);
                    if (action.Mutated)
                    {
                        actions.WriteLine(JsonSerializer.Serialize(action)); actions.Flush();
                        if (action.Kind == "cast") { casts++; if (JsonSerializer.SerializeToElement(action.Detail).GetProperty("phaseBefore").GetInt32() == (int)RoomPlayerPhase.Pvp) pvpCasts++; }
                    }
                    current = await admitted.Frames.AdvanceOneFrameAsync(ct);
                }
            }
            current = await admitted.Frames.CaptureStableAsync(ct);
            Write(directory, "terminal-or-censored.original.json", current);
            var primary = current.Players.Single(value => value.PlayerId == state.Player);
            if (primary.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted))
            {
                state.Censored = true;
                journal.Phase(scheduled.Id, "calendar-censored", new { admitted.MatchId, admitted.RoomId, current.Elapsed, phase = primary.Phase });
            }
            else
            {
                await snapshots.SaveIfDueAsync(current, ct);
                var settlements = new SettlementRepository(source, clock, metrics);
                await new SettlementCoordinator(settlements, clock).ObserveAsync(admitted.MatchId, current);
                var settled = await settlements.GetForMatchAsync(state.Player, admitted.MatchId, ct);
                await settlements.CommitHoldsAsync(settled.SettlementId, ct);
                Write(directory, "settlement.original.json", settled);
                state.ConsecutiveDeaths = primary.Phase == RoomPlayerPhase.Dead ? state.ConsecutiveDeaths + 1 : 0;
                // Preserve the post-run real balance before the next lobby rather than seeding model income.
                var progression = new ProgressionRepository(source, clock);
                Write(directory, "after.original.json", new { scheduled, primary.Phase, elapsed_seconds = current.Elapsed.TotalSeconds,
                    primary_elapsed_observation = current.Observations, casts, pvpCasts, state.ConsecutiveDeaths,
                    wallet = await new SeasonRepository(source, clock).GetWalletAsync(state.Player, season.ContextFor(0), ct),
                    inventory = await progression.GetInventoryAsync(state.Player, ct), cards = await progression.GetCardsAsync(state.Player, ct),
                    journey = await new SeasonJourneyRepository(source, clock, new(config)).GetAsync(state.Player, ct, season.SeasonId),
                    unlocked = await new SeasonRepository(source, clock).GetUnlockedDifficultyAsync(state.Player, season.SeasonId, ct) });
                journal.Phase(scheduled.Id, "calendar-settled", new { admitted.MatchId, admitted.RoomId, admitted.ActualSeed, settled.Result,
                    elapsed_seconds = current.Elapsed.TotalSeconds, casts, pvpCasts });
            }
            await rooms.RemoveAsync(admitted.RoomId);
            Assert.Equal(0, clock.ActiveTimers);
            progress.Finished.Add(scheduled.Id); progress.NextIndex++; progress.CurrentCase = null; progress.ManualLobbyResumeCase = null; progress.Status = "Ready"; Save(control, progress);
        }
        progress.Status = progress.NextIndex == schedule.Length ? "Completed" : "BatchBoundary";
        Save(control, progress);
        Write(output, "batch-" + progress.NextIndex + ".original.json", new { progress.Schema, progress.Status, progress.NextIndex,
            progress.Finished, progress.Skipped, progress.Actors, new_actual_starts = newStarts,
            schema_intentionally_retained_for_same_profile_continuation = true, F01_complete = false });
    }

    private static async Task DeclareHistory(NpgsqlDataSource source, Guid player, SeasonFirstFortnightInputsTests.Actor actor, CancellationToken ct)
    {
        await using var connection = await source.OpenConnectionAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(ct);
        async Task Sql(string text, params object[] values)
        {
            await using var command = new NpgsqlCommand(text, connection, transaction);
            foreach (var value in values) command.Parameters.AddWithValue(value);
            await command.ExecuteNonQueryAsync(ct);
        }
        await Sql("UPDATE player_cards SET unlocked=true,copy_count=GREATEST(copy_count,1),level=5,version=version+1 WHERE player_id=$1 AND card_id=ANY($2)", player, actor.Cards);
        await Sql("UPDATE class_weapons SET level=5,version=version+1 WHERE player_id=$1 AND hero_class=$2", player, (short)actor.Hero);
        await Sql("DELETE FROM player_deck_cards c USING player_decks d WHERE c.deck_id=d.deck_id AND d.player_id=$1 AND d.hero_class=$2", player, (short)actor.Hero);
        for (var index = 0; index < actor.Cards.Length; index++) await Sql("INSERT INTO player_deck_cards(deck_id,slot_index,card_id) SELECT deck_id,$3,$4 FROM player_decks WHERE player_id=$1 AND hero_class=$2", player, (short)actor.Hero, index, actor.Cards[index]);
        await Sql("UPDATE player_decks SET version=version+1 WHERE player_id=$1 AND hero_class=$2", player, (short)actor.Hero);
        await transaction.CommitAsync(ct);
    }
    private static string Required(string key) => Environment.GetEnvironmentVariable(key) ?? throw new InvalidOperationException(key + " required.");
    private static void Save(string path, Progress state)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var temporary = path + ".next";
        using (var stream = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
        { JsonSerializer.Serialize(stream, state, Json); stream.Flush(flushToDisk: true); }
        File.Move(temporary, path, overwrite: true);
    }
    private static void Write(string directory, string name, object value)
    {
        var path = Path.Combine(directory, name); Assert.False(File.Exists(path));
        File.WriteAllText(path, JsonSerializer.Serialize(value, Json));
    }
}
