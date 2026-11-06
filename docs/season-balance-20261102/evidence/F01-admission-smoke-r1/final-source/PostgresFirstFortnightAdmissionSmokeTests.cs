using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Persistence;

/// <summary>Budgeted new F01 normal-match diagnostic. Passive primary, real fill bots; never calendar-profile income.</summary>
public sealed class PostgresFirstFortnightAdmissionSmokeTests
{
    private static readonly JsonSerializerOptions EvidenceJson = new() { WriteIndented = true };
    public static bool Enabled => PostgresMigrationTests.HasTestDatabase
        && Environment.GetEnvironmentVariable("FANTASYCARD_RUN_F01_ADMISSION_SMOKE") == "1";

    [Fact(Skip = "Explicit budgeted F01 diagnostic, not part of an automatic full test run.", SkipUnless = nameof(Enabled))]
    [Trait("Category", "PostgresIntegration")]
    public async Task ActualReadyBotsExplicitClockAndTerminalSettlementUseOneDurableStart()
    {
        var budgetPath = Environment.GetEnvironmentVariable("FANTASYCARD_F01_BUDGET") ?? throw new InvalidOperationException("Actual F01 budget required.");
        using var budget = JsonDocument.Parse(File.ReadAllText(budgetPath));
        var spec = budget.RootElement;
        var permit = new SeasonFirstFortnightExecutionPermit(spec.GetProperty("approved").GetBoolean(),
            spec.GetProperty("synthetic").GetBoolean(), spec.GetProperty("maximum").GetInt32(), spec.GetProperty("decisionReference").GetString());
        permit.RequireRealLaunch();
        var caseId = Environment.GetEnvironmentVariable("FANTASYCARD_F01_SMOKE_CASE") ?? throw new InvalidOperationException("Frozen diagnostic case required.");
        var allowed = spec.GetProperty("smoke_case_ids").EnumerateArray().Select(value => value.GetString()!).ToHashSet(StringComparer.Ordinal);
        Assert.Contains(caseId, allowed);
        var journal = new SeasonFirstFortnightAttemptJournal(spec.GetProperty("journal").GetString()!, permit.Maximum, allowed);
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_F01_ADMISSION_SMOKE_OUTPUT") ?? throw new InvalidOperationException("New diagnostic output required.");
        Assert.False(Directory.Exists(output));
        Directory.CreateDirectory(output);
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("f01-admission-smoke", new(2026, 11, 1), config.Version, "season-equipment-v1");
        var startsAt = season.StartsAtUtc.AddHours(9);
        var clock = new SeasonFirstFortnightTimeProvider(startsAt);
        var seasons = new SeasonRepository(db.DataSource, clock);
        Assert.True(await seasons.PublishAsync(season, config.ContentHash, ct));
        var actor = SeasonFirstFortnightInputsTests.DeclareActors().Single(value => value.Id == "F01-novice-Priest");
        var identity = new IdentityRepository(db.DataSource, new PlayerProvisioningService());
        var profile = await identity.SignInLocalAsync("owned-smoke-device", "f01-" + Guid.NewGuid().ToString("N")[..12],
            RandomNumberGenerator.GetBytes(32), startsAt, startsAt.AddHours(1), ct);
        var preparations = new PreparationRepository(db.DataSource, clock);
        var prep = await preparations.CreateAsync(profile.UserId, caseId + "-prepare",
            new(HeroClassDto.Priest, 1, new Guid?[5], BackpackTierDto.Free, Array.Empty<int>(), 0, "D0", season.SeasonId), ct);
        Assert.Equal(CreatePreparationStatus.Created, prep.Status);
        using var metrics = new ServerMetrics();
        var settings = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            { ["Matchmaking:BotFillDelaySeconds"] = "0" }).Build();
        var matchmaking = new MatchmakingRepository(db.DataSource, clock, metrics, settings);
        var snapshots = new RoomSnapshotRepository(db.DataSource, clock, metrics);
        await using var rooms = new RoomRegistry(clock);
        using var ready = new RoomReadyCoordinator(matchmaking, rooms, snapshots, new RealtimeEventStore(clock),
            new ConnectionRegistry(), clock, NullLogger<RoomReadyCoordinator>.Instance);
        var controller = new SeasonFirstFortnightAdmissionController(db.DataSource, matchmaking, ready, rooms,
            new SeasonFirstFortnightPreparedController(preparations, clock, season), clock, permit, journal);
        var admitted = await controller.AdmitAsync(caseId, actor, profile.UserId, prep.Preparation!.PreparationId, startsAt, ct);
        Write(output, "admitted.original.json", new { caseId, admitted.MatchId, admitted.RoomId, admitted.ActualSeed,
            admitted.InitialState, passive_primary_diagnostic = true, no_income_into_calendar_profiles = true });
        var current = admitted.InitialState;
        using (var frames = new StreamWriter(Path.Combine(output, "frames.original.jsonl")))
        {
            while (current.Elapsed < TimeSpan.FromSeconds(1200)
                   && current.Players.Any(value => value.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)))
            {
                current = await admitted.Frames.AdvanceOneFrameAsync(ct);
                if (current.Elapsed.Ticks % TimeSpan.FromSeconds(2.5).Ticks == 0)
                    frames.WriteLine(JsonSerializer.Serialize(new { current.Elapsed, now = clock.GetUtcNow(),
                        players = current.Players.Select(value => new { value.PlayerId, value.IsBot, value.Phase, value.Combat.Hp }) }));
            }
        }
        current = await admitted.Frames.CaptureStableAsync(ct);
        Write(output, "terminal-or-censored.original.json", current);
        var primary = current.Players.Single(value => value.PlayerId == profile.UserId);
        Assert.Equal(RoomPlayerPhase.Dead, primary.Phase);
        Assert.Equal(0, primary.Combat.Hp);
        await snapshots.SaveIfDueAsync(current, ct);
        var settlements = new SettlementRepository(db.DataSource, clock, metrics);
        await new SettlementCoordinator(settlements, clock).ObserveAsync(admitted.MatchId, current);
        var settled = await settlements.GetForMatchAsync(profile.UserId, admitted.MatchId, ct);
        Write(output, "settlement.original.json", settled);
        Assert.Equal("Dead", settled.Result);
        Assert.Equal(admitted.MatchId, settled.MatchId);
        Assert.Equal(profile.UserId, settled.PlayerId);
        Assert.Equal(0L, await db.ScalarAsync<long>("SELECT gold+equipment_fragments+blueprint_marks+orange_blueprint_marks FROM player_season_wallets WHERE player_id=$1 AND season_id=$2", profile.UserId, season.SeasonId));
        journal.Phase(caseId, "diagnostic-finished", new { admitted.MatchId, admitted.RoomId, admitted.ActualSeed,
            result = settled.Result, current.Elapsed, remaining_active_npcs = current.Players.Count(value => value.IsBot && value.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted)),
            calendar_income_merged = false });
        await rooms.RemoveAsync(admitted.RoomId);
        Assert.Equal(0, clock.ActiveTimers);
        Write(output, "result.original.json", new { caseId, actual_gameplay_starts = 1, normal_participants = 4,
            actual_fill_bots = 3, actual_seed = admitted.ActualSeed, primary = "passive-no-player-actions",
            actual_result = settled.Result, elapsed_seconds = current.Elapsed.TotalSeconds,
            actual_terminal_settlement = true, calendar_profiles_run = false, F01_complete = false,
            no_calendar_income_merged = true, active_timers_after_cleanup = clock.ActiveTimers });
    }

    private static void Write(string output, string name, object value)
    {
        var path = Path.Combine(output, name);
        Assert.False(File.Exists(path));
        File.WriteAllText(path, JsonSerializer.Serialize(value, EvidenceJson));
    }
}
