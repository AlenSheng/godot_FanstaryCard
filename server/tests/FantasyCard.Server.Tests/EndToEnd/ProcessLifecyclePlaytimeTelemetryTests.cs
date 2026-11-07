using System.Globalization;
using System.Numerics;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Telemetry;
using FantasyCard.Server.Tests.Persistence;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Fact(Skip="Requires an owned local PostgreSQL database.",SkipUnless=nameof(HasPrivateDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task PersistedTerminalClocksDriveNetHourlyPercentilesIncludingDeathsZeroAndUnlocatedFinancialRows()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"playtime-and-quantiles");await db.MigrateAsync();
        var config=GameConfigCatalog.Current;var epoch=DateTimeOffset.UtcNow.AddMinutes(-10);var clock=new PlaytimeTestClock(epoch.AddMinutes(5));
        var season=SeasonDefinition.FromCalendarDays("clock-season",DateOnly.FromDateTime(epoch.UtcDateTime).AddDays(-1),config.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,config.ContentHash,TestContext.Current.CancellationToken,config);
        var players=new List<Guid>();var snapshots=new List<(Guid Match,FantasyCard.Domain.Rooms.BattleRoom Room)>();
        for(var i=0;i<3;i++)
        {
            var identity=await SeedPlayerAsync(db,"Playtime "+i,TestContext.Current.CancellationToken);players.Add(identity.Id);
            var setup=await SeedSeasonCreditRoom(db,config,season,identity.Id,.75,TestContext.Current.CancellationToken);
            var room=FantasyCard.Domain.Rooms.BattleRoom.Restore(setup.Room.Capture() with{StartedAtUtc=epoch},CombatCardCatalog.Create(config),73);
            room.Advance(TimeSpan.FromSeconds(i<2?45:60),epoch.AddSeconds(i<2?45:60));
            if(i<2){room.MarkPlayerDisconnected(identity.Id);room.Advance(TimeSpan.FromSeconds(15),epoch.AddSeconds(60));}
            else{var duration=room.RequestExtraction(identity.Id);room.Advance(duration,epoch.AddSeconds(60)+duration);}
            snapshots.Add((setup.Match,room));
        }
        using var metrics=new ServerMetrics();var repository=new RoomSnapshotRepository(db.DataSource,clock,metrics);var settlement=new SettlementRepository(db.DataSource,clock,metrics);
        foreach(var item in snapshots)
        {
            await repository.SaveIfDueAsync(item.Room.Capture(),TestContext.Current.CancellationToken);
            // This empty-asset checkpoint tests new observation fields in the
            // actual coordinator receipt, not ordinary asset settlement again.
            await new SettlementCoordinator(settlement,clock).ObserveAsync(item.Match,item.Room.Capture());
        }
        await SqlAsync(db,"UPDATE player_season_wallets SET gold=100 WHERE player_id=$1 AND season_id=$2",TestContext.Current.CancellationToken,players[0],season.SeasonId);
        await seasons.ApplyAsync(players[0],season.ContextFor(0),-1,0,0,"test.playtime.cost","debit",SeasonWalletPurpose.General,TestContext.Current.CancellationToken);
        await seasons.ApplyAsync(players[2],season.ContextFor(0),10,0,0,"test.playtime.income","credit",SeasonWalletPurpose.General,TestContext.Current.CancellationToken);
        var read=new PlaytimeTelemetryRepository(db.DataSource);var before=await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db);
        var report=await read.ReadAsync(epoch,epoch.AddMinutes(6),"Gold",season.SeasonId,false,TestContext.Current.CancellationToken);
        var group=Assert.Single(report.Groups);Assert.Equal(3,group.Players);Assert.Equal(1,group.ZeroNetPlayers);Assert.Equal(1,group.NegativeNetPlayers);
        Assert.Equal("-60.000000",group.P10.DecimalDisplay);Assert.Equal("0.000000",group.P50.DecimalDisplay);
        var last=snapshots[2].Room.GetPlayer(players[2]).TerminalRoomElapsed!.Value;
        Assert.Equal(PlaytimeStatistics.Rate(10,last.Ticks),group.P90);Assert.Equal("9",group.NetAmount);Assert.True(report.CompleteForWindow);Assert.True(report.RatesAvailable);
        var details=await db.ScalarAsync<string>("SELECT details_json::text FROM match_settlements WHERE match_id=$1",snapshots[0].Match);
        using(var document=JsonDocument.Parse(details))
        {
            Assert.Equal(epoch,document.RootElement.GetProperty("startedAtUtc").GetDateTimeOffset());Assert.Equal("00:01:00",document.RootElement.GetProperty("terminalRoomElapsed").GetString());
        }
        var saved=(await repository.GetAsync(snapshots[0].Room.RoomId,TestContext.Current.CancellationToken))!;
        Assert.Equal(TimeSpan.FromSeconds(60),saved.Players[0].TerminalRoomElapsed);Assert.Equal(epoch,saved.StartedAtUtc);
        Assert.Equal(before,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));
        var untimed=await SeedPlayerAsync(db,"Unknown playtime",TestContext.Current.CancellationToken);await seasons.EnsurePlayerAsync(untimed.Id,season.ContextFor(0),TestContext.Current.CancellationToken);
        await seasons.ApplyAsync(untimed.Id,season.ContextFor(0),4,0,0,"test.playtime.income","untimed",SeasonWalletPurpose.General,TestContext.Current.CancellationToken);
        var incomplete=await read.ReadAsync(epoch,epoch.AddMinutes(6),"Gold",season.SeasonId,false,TestContext.Current.CancellationToken);
        Assert.Equal(1,incomplete.FlowPlayersWithoutKnownClock);Assert.Equal("4",incomplete.NetWithoutKnownClock);Assert.False(incomplete.CompleteForWindow);Assert.Equal(report.Groups,incomplete.Groups);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-playtime-window",report,incomplete,sourceClocks=snapshots.Select(s=>new{s.Match,s.Room.StartedAtUtc,player=s.Room.Capture().Players[0]}),
            readOnlyFingerprintUnchanged=true,controlledAuthoritativeClockFixture=true,realHumanActivityClaimed=false,gameplayCasts=0});
    }

    private sealed class PlaytimeTestClock(DateTimeOffset now):TimeProvider {public override DateTimeOffset GetUtcNow()=>now;}
}
