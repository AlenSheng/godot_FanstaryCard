using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Config;

/// <summary>Clock tests use empty unstarted rooms only, never a prepared player, map or gameplay attempt.</summary>
public sealed class SeasonFirstFortnightActorClockTests
{
    private static readonly JsonSerializerOptions EvidenceJson = new() { WriteIndented = true };
    public static bool Enabled => Environment.GetEnvironmentVariable("FANTASYCARD_RUN_F01_CLOCK") == "1";

    [Fact(Skip = "Explicit F01 actor clock preflight; empty room, no map or encounter.", SkipUnless = nameof(Enabled))]
    public async Task RealActorPeriodicTimerCannotAddAutomaticFramesToTheExplicitDriver()
    {
        var config = GameConfigCatalog.Current;
        var season = SeasonDefinition.FromCalendarDays("f01-clock", new(2026, 11, 1), config.Version, "season-equipment-v1");
        var context = season.ContextFor(0);
        var startsAt = season.StartsAtUtc.AddDays(13).AddHours(18);
        var clock = new SeasonFirstFortnightTimeProvider(startsAt);
        var room = new BattleRoom(Guid.NewGuid(), config.Version, CombatCardCatalog.Create(config), 430001, season: context);
        var frames = new List<object>();
        await using (var actor = new RoomActor(room, clock, startTicker: true))
        {
            Assert.Equal(1, clock.ActiveTimers);
            var driver = await SeasonFirstFortnightActorClock.BindAsync(actor, clock, room.RoomId, context, startsAt,
                TimeSpan.FromMilliseconds(200), TestContext.Current.CancellationToken);
            for (var index = 1; index <= 2; index++)
            {
                var snapshot = await driver.AdvanceOneFrameAsync(TestContext.Current.CancellationToken);
                Assert.Equal(TimeSpan.FromMilliseconds(index * 100), snapshot.Elapsed);
                Assert.Equal(startsAt.AddMilliseconds(index * 100), clock.GetUtcNow());
                Assert.Empty(snapshot.Players);
                Assert.Null(snapshot.Map);
                frames.Add(new { index, snapshot.Elapsed, now = clock.GetUtcNow(), no_players_or_map = true });
            }
            await Assert.ThrowsAsync<InvalidOperationException>(() => driver.AdvanceOneFrameAsync(TestContext.Current.CancellationToken));
            var stable = await driver.CaptureStableAsync(TestContext.Current.CancellationToken);
            Assert.Equal(TimeSpan.FromMilliseconds(200), stable.Elapsed);
        }
        Assert.Equal(0, clock.ActiveTimers);
        Write("explicit-frames.original.json", new { startsAt, frames, original_periodic_timer_active_during_test = true,
            disposed_active_timers = clock.ActiveTimers, actual_gameplay_starts = 0, real_player_or_map_used = false });
    }

    [Fact(Skip = "Explicit F01 wrong-clock guard preflight; empty room, no gameplay.", SkipUnless = nameof(Enabled))]
    public async Task ForeignClockOrActorChangesAreRejectedWithoutAnAutomaticRetry()
    {
        var config = GameConfigCatalog.Current;
        var context = new SeasonContext("f01-clock-guards", 0, "season-v1", config.Version, "season-equipment-v1");
        var startsAt = new DateTimeOffset(2026, 11, 1, 1, 0, 0, TimeSpan.Zero);
        var clock = new SeasonFirstFortnightTimeProvider(startsAt);
        var room = new BattleRoom(Guid.NewGuid(), config.Version, CombatCardCatalog.Create(config), 430002, season: context);
        await using var actor = new RoomActor(room, clock, startTicker: false);
        await Assert.ThrowsAsync<InvalidOperationException>(() => SeasonFirstFortnightActorClock.BindAsync(actor, clock,
            Guid.NewGuid(), context, startsAt, TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken));
        var driver = await SeasonFirstFortnightActorClock.BindAsync(actor, clock, room.RoomId, context, startsAt,
            TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken);
        clock.AdvanceExplicitly(TimeSpan.FromMilliseconds(100));
        await Assert.ThrowsAsync<InvalidOperationException>(() => driver.AdvanceOneFrameAsync(TestContext.Current.CancellationToken));
        await Assert.ThrowsAsync<InvalidOperationException>(() => driver.AdvanceOneFrameAsync(TestContext.Current.CancellationToken));
        var snapshot = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), TestContext.Current.CancellationToken);
        Assert.Equal(TimeSpan.Zero, snapshot.Elapsed);
        Assert.Empty(snapshot.Players);
        Assert.Null(snapshot.Map);
        var cleanClock = new SeasonFirstFortnightTimeProvider(startsAt);
        var secondDriver = await SeasonFirstFortnightActorClock.BindAsync(actor, cleanClock, room.RoomId, context, startsAt,
            TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken);
        await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100), startsAt.AddMilliseconds(100)), TestContext.Current.CancellationToken);
        await Assert.ThrowsAsync<InvalidOperationException>(() => secondDriver.AdvanceOneFrameAsync(TestContext.Current.CancellationToken));
        await Assert.ThrowsAsync<InvalidOperationException>(() => secondDriver.CaptureStableAsync(TestContext.Current.CancellationToken));
        Write("foreign-clock-guards.original.json", new { wrong_actor_rejected = true, external_clock_change_rejected = true,
            faulted_driver_retry_rejected = true, foreign_actor_tick_rejected = true, actual_gameplay_starts = 0,
            all_rooms_empty_and_unstarted = true });
    }

    [Fact(Skip = "Explicit F01 original-start guard; no map or gameplay admission.", SkipUnless = nameof(Enabled))]
    public async Task OriginalStartTimeAndPreparedPrototypeCannotBeReplacedByADeclaredClock()
    {
        var config = GameConfigCatalog.Current;
        var context = new SeasonContext("f01-clock-start", 0, "season-v1", config.Version, "season-equipment-v1");
        var startsAt = new DateTimeOffset(2026, 11, 14, 10, 0, 0, TimeSpan.Zero);
        var clock = new SeasonFirstFortnightTimeProvider(startsAt);
        var catalog = CombatCardCatalog.Create(config);
        var empty = new BattleRoom(Guid.NewGuid(), config.Version, catalog, 430003, season: context).Capture();
        var oldEpoch = new DateTimeOffset(2026, 11, 20, 0, 0, 0, TimeSpan.Zero);
        var restored = BattleRoom.Restore(empty with { StartedAtUtc = oldEpoch }, catalog, 430003);
        await using (var actor = new RoomActor(restored, clock, startTicker: false))
            await Assert.ThrowsAsync<InvalidOperationException>(() => SeasonFirstFortnightActorClock.BindAsync(actor, clock,
                restored.RoomId, context, startsAt, TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken));
        var owned = SeasonFirstFortnightInputsTests.DeclareActors().First();
        var prepared = SeasonFirstFortnightInputsTests.CreateUnstartedRoom(owned, context, Guid.NewGuid(), 430004);
        await using (var actor = new RoomActor(prepared, clock, startTicker: false))
            await Assert.ThrowsAsync<InvalidOperationException>(() => SeasonFirstFortnightActorClock.BindAsync(actor, clock,
                prepared.RoomId, context, startsAt, TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken));
        var matching = BattleRoom.Restore(empty with { StartedAtUtc = startsAt }, catalog, 430003);
        await using (var actor = new RoomActor(matching, clock, startTicker: false))
        {
            var driver = await SeasonFirstFortnightActorClock.BindAsync(actor, clock, matching.RoomId, context, startsAt,
                TimeSpan.FromSeconds(1), TestContext.Current.CancellationToken);
            var stable = await driver.CaptureStableAsync(TestContext.Current.CancellationToken);
            Assert.Equal(startsAt, stable.StartedAtUtc);
            Assert.Equal(TimeSpan.Zero, stable.Elapsed);
            Assert.Empty(stable.Players);
            Assert.Null(stable.Map);
        }
        Write("original-start-guards.original.json", new { startsAt, oldEpoch, wrong_original_start_rejected = true,
            player_without_map_admission_rejected = true, matching_original_metadata_kept = true,
            actual_gameplay_starts = 0, no_map_initialized_or_advanced = true });
    }

    private static void Write(string name, object value)
    {
        var output = Environment.GetEnvironmentVariable("FANTASYCARD_F01_CLOCK_OUTPUT")
            ?? throw new InvalidOperationException("New F01 clock evidence directory required.");
        Directory.CreateDirectory(output);
        var path = Path.Combine(output, name);
        Assert.False(File.Exists(path));
        File.WriteAllText(path, JsonSerializer.Serialize(value, EvidenceJson));
    }
}
