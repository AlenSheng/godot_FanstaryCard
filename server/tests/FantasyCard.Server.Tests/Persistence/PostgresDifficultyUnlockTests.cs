using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresDifficultyUnlockTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task WholeUnlockChainRequiresTheRightSameMatchConditionAndDoesNotCountDeathOrReplay()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        var season = Define("unlock",new DateOnly(2026,11,2));var clock = new Clock(season.StartsAtUtc.AddHours(1));
        var player = await PlayerAsync(db,clock);var seasons = new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,new string('a',64),Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        using var metrics = new ServerMetrics();var repository = new SettlementRepository(db.DataSource,clock,metrics);
        var first = await TerminalAsync(db,season,player,0,false,false,RoomPlayerPhase.Extracted);
        await new SettlementCoordinator(repository,clock).ObserveAsync(first.Match,first.Snapshot);
        Assert.Equal(0,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await new SettlementCoordinator(new(db.DataSource,clock,metrics),clock).ObserveAsync(first.Match,first.Snapshot);
        Assert.Equal(1,await db.ScalarAsync<long>("SELECT count(*) FROM season_difficulty_completions WHERE player_id=$1",player));
        await CompleteAsync(db,repository,clock,season,player,0,false,false);
        Assert.Equal(1,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,1,false,false);
        Assert.Equal(1,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,1,true,false);
        Assert.Equal(2,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,2,true,false);
        Assert.Equal(2,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,2,false,true);
        Assert.Equal(3,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,3,false,true,RoomPlayerPhase.Dead);
        Assert.Equal(3,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,3,false,true);
        Assert.Equal(3,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,3,false,true);
        Assert.Equal(4,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,4,false,true);
        Assert.Equal(4,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        await CompleteAsync(db,repository,clock,season,player,4,false,true);
        Assert.Equal(5,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
        Assert.Equal(10,await db.ScalarAsync<long>("SELECT count(*) FROM season_difficulty_completions WHERE player_id=$1",player));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ConcurrentAndLateOriginalSeasonCompletionsAreOnceOnlyAndCannotUnlockTheNextSeason()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        var original = Define("original-unlock",new DateOnly(2026,9,1));var next = Define("next-unlock",new DateOnly(2026,10,13));
        var clock = new Clock(original.StartsAtUtc.AddHours(1));var player = await PlayerAsync(db,clock);
        var seasons = new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(original,new string('a',64),Ct);
        await seasons.PublishAsync(next,new string('b',64),Ct);await seasons.EnsurePlayerAsync(player,original.ContextFor(0),Ct);
        var first = await TerminalAsync(db,original,player,0,false,false,RoomPlayerPhase.Extracted);
        var second = await TerminalAsync(db,original,player,0,false,false,RoomPlayerPhase.Extracted);
        clock.Now = next.StartsAtUtc.AddHours(1);await seasons.EnsurePlayerAsync(player,next.ContextFor(0),Ct);
        using var metrics = new ServerMetrics();
        await Task.WhenAll(new SettlementCoordinator(new(db.DataSource,clock,metrics),clock).ObserveAsync(first.Match,first.Snapshot),
            new SettlementCoordinator(new(db.DataSource,clock,metrics),clock).ObserveAsync(second.Match,second.Snapshot));
        await new SettlementCoordinator(new(db.DataSource,clock,metrics),clock).ObserveAsync(first.Match,first.Snapshot);
        Assert.Equal(1,await seasons.GetUnlockedDifficultyAsync(player,original.SeasonId,Ct));
        Assert.Equal(0,await seasons.GetUnlockedDifficultyAsync(player,next.SeasonId,Ct));
        Assert.Equal(2,await db.ScalarAsync<long>("SELECT count(*) FROM season_difficulty_completions WHERE player_id=$1",player));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task InvalidCompletionProofRollsBackTheSettlementOutboxAndUnlockTogether()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        var season = Define("bad-proof",new DateOnly(2026,11,2));var clock = new Clock(season.StartsAtUtc.AddHours(1));
        var player = await PlayerAsync(db,clock);var seasons = new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,new string('c',64),Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        var fixture = await TerminalAsync(db,season,player,0,false,false,RoomPlayerPhase.Extracted);
        using var details = JsonDocument.Parse(JsonSerializer.Serialize(new {roomId=fixture.Snapshot.RoomId,difficultyProgress=new {eliteCleared="true",bossCleared=false}},Json));
        using var metrics = new ServerMetrics();var repository = new SettlementRepository(db.DataSource,clock,metrics);
        await Assert.ThrowsAsync<InvalidDataException>(()=>repository.SettleAsync(fixture.Match,player,"Extracted",details.RootElement,[],Ct,season.ContextFor(0),season.ConfigVersion));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",fixture.Match));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_notification_outbox"));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM season_difficulty_completions"));
        Assert.Equal(0,await seasons.GetUnlockedDifficultyAsync(player,season.SeasonId,Ct));
    }

    private static async Task CompleteAsync(PostgresTestSchema db,SettlementRepository repository,Clock clock,SeasonDefinition season,
        Guid player,int difficulty,bool elite,bool boss,RoomPlayerPhase phase=RoomPlayerPhase.Extracted)
    {
        var fixture = await TerminalAsync(db,season,player,difficulty,elite,boss,phase);
        await new SettlementCoordinator(repository,clock).ObserveAsync(fixture.Match,fixture.Snapshot);
    }

    private static async Task<(Guid Match,BattleRoomSnapshot Snapshot)> TerminalAsync(PostgresTestSchema db,SeasonDefinition season,
        Guid player,int difficulty,bool elite,bool boss,RoomPlayerPhase phase)
    {
        // Declared terminal-checkpoint fixture: counts proof/transactions, not a completed gameplay route.
        var room = new BattleRoom(Guid.NewGuid(),season.ConfigVersion,CombatCardCatalog.Create(GameConfigCatalog.Current),73,season:season.ContextFor(difficulty));
        var cards = Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"MAG-{i:D2}")).ToArray();
        room.AddPlayer(new(player,HeroClass.Mage,cards,null));room.InitializeMap(ChaosMapGenerator.Generate(73,1));
        var snapshot = room.Capture();
        var cells = snapshot.Map!.Cells.Where(c=>boss?c.IsBoss:elite&&c.MonsterGroupId.StartsWith('E')).Select(c=>c.Position).Take(1).ToArray();
        snapshot = snapshot with {Players=snapshot.Players.Select(p=>p with {Phase=phase,Pve=null,ClearedCells=cells}).ToArray()};
        var match = Guid.NewGuid();
        await using (var command = db.DataSource.CreateCommand("""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm',$3,73,$4,'Running',$5,$6,$7,$8)
            """))
        {
            foreach (var value in new object[] {match,room.RoomId,$"D{difficulty}",season.ConfigVersion,season.StartsAtUtc,season.SeasonId,season.RulesetId,season.StatsVersion})command.Parameters.AddWithValue(value);
            await command.ExecuteNonQueryAsync(Ct);
        }
        await using (var command = db.DataSource.CreateCommand("INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')"))
        {command.Parameters.AddWithValue(match);command.Parameters.AddWithValue(player);await command.ExecuteNonQueryAsync(Ct);}
        return (match,snapshot);
    }

    private static SeasonDefinition Define(string id,DateOnly start) => SeasonDefinition.FromCalendarDays(id,start,GameConfigCatalog.Current.Version,"season-equipment-v1",highestOpenDifficulty:5);
    private static async Task<Guid> PlayerAsync(PostgresTestSchema db,Clock clock) =>
        (await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(Guid.NewGuid().ToString("N"),"Unlock "+Guid.NewGuid().ToString("N")[..8],RandomNumberGenerator.GetBytes(32),clock.Now,clock.Now.AddHours(1),Ct)).UserId;
    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public DateTimeOffset Now {get;set;}=now;
        public override DateTimeOffset GetUtcNow()=>Now;
    }
}
