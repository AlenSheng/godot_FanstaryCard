using System.Security.Cryptography;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonBorrowedDeckTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData(HeroClassDto.Priest)] [InlineData(HeroClassDto.Mage)] [InlineData(HeroClassDto.Guardian)]
    [Trait("Category","PostgresIntegration")]
    public async Task AllCapsBorrowWithoutOwnedCopiesOrSavedDeckAndNeverChangePermanentAssets(HeroClassDto hero)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        var season = Define();var clock = new Clock(season.StartsAtUtc);var player = await PlayerAsync(db,clock);
        var seasons = new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,new string('a',64),Ct);
        await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        await Sql(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",player);
        await Sql(db,"DELETE FROM player_decks WHERE player_id=$1 AND hero_class=$2",player,(short)hero);
        await Sql(db,"UPDATE player_cards SET unlocked=false,copy_count=0,level=5 WHERE player_id=$1",player);
        // One missing row also has no ownership record, rather than a locked row.
        await Sql(db,"DELETE FROM player_cards WHERE player_id=$1 AND card_id='C01'",player);
        await Sql(db,"UPDATE class_weapons SET level=1 WHERE player_id=$1",player);
        var before = await AssetsAsync(db,player);
        var repository = new PreparationRepository(db.DataSource,clock);
        var template = GameConfigCatalog.Current.BorrowedDeck((HeroClass)(int)hero);
        for (var difficulty=0;difficulty<=5;difficulty++)
        {
            var request = Request(hero,difficulty);
            var created = await repository.CreateAsync(player,"loan-"+difficulty,request,Ct);
            Assert.Equal(CreatePreparationStatus.Created,created.Status);
            var snapshot = created.Preparation!.Snapshot;
            Assert.Equal(template.TemplateId,snapshot.BorrowedTemplateId);
            Assert.Equal(template.CardIds,snapshot.CardIds);
            Assert.Equal(difficulty,snapshot.ClassWeaponLevel);
            Assert.All(snapshot.CardLevels!,level=>Assert.Equal(difficulty,level));
            Assert.Equal(1,snapshot.ActualClassWeaponLevel);
            Assert.Equal(0,snapshot.ActualCardLevels![0]);
            Assert.All(snapshot.ActualCardLevels.Skip(1),level=>Assert.Equal(5,level));
            Assert.Equal(hero switch {HeroClassDto.Mage=>70,HeroClassDto.Priest=>80,_=>100},snapshot.MaximumHp);
            var replay = await repository.CreateAsync(player,"loan-"+difficulty,request,Ct);
            Assert.Equal(CreatePreparationStatus.Replayed,replay.Status);
            Assert.Equal(created.Preparation.PreparationId,replay.Preparation!.PreparationId);
            Assert.Equal(CreatePreparationStatus.RequestConflict,(await repository.CreateAsync(player,"loan-"+difficulty,request with {UseBorrowedDeck=false},Ct)).Status);
            Assert.Equal(CancelPreparationStatus.Cancelled,await repository.CancelAsync(player,created.Preparation.PreparationId,"cancel-"+difficulty,Ct));
        }
        Assert.Equal(before,await AssetsAsync(db,player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM preparation_assets"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements"));
        Assert.Equal(CreatePreparationStatus.DeckVersionConflict,(await repository.CreateAsync(player,"own-missing",Request(hero,0) with {UseBorrowedDeck=false},Ct)).Status);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task BorrowingDoesNotBypassSeasonPersonalUnlockOrOwnedDeckCopyValidation()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        var season=Define();var clock=new Clock(season.StartsAtUtc.AddSeconds(-1));var player=await PlayerAsync(db,clock);
        var seasons=new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,new string('a',64),Ct);
        var repository=new PreparationRepository(db.DataSource,clock);
        var request=Request(HeroClassDto.Mage,0);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CreateAsync(player,"legacy",request with {SeasonId=null,Difficulty="Standard"},Ct));
        clock.Now=season.StartsAtUtc;
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CreateAsync(player,"locked",request with {Difficulty="D1"},Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CreateAsync(player,"wrong",request with {SeasonId="other"},Ct));
        var version=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",player);
        await Sql(db,"UPDATE player_cards SET unlocked=false,copy_count=0 WHERE player_id=$1",player);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CreateAsync(player,"own",request with {UseBorrowedDeck=false,DeckVersion=version},Ct));
        clock.Now=season.EndsAtUtc;
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CreateAsync(player,"closed",request,Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM preparations"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_season_state"));
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("valid")] [InlineData("missing")] [InlineData("changed")] [InlineData("bot")]
    [Trait("Category","PostgresIntegration")]
    public async Task MatchLaunchAndRecoveryPreserveBorrowedSourceAndQuarantineTamperedSnapshots(string mutation)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var season=Define();var clock=new Clock(season.StartsAtUtc);var player=await PlayerAsync(db,clock);
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,new string('a',64),Ct);
        await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        await Sql(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",player);
        var before=await AssetsAsync(db,player);
        var preparation=(await new PreparationRepository(db.DataSource,clock).CreateAsync(player,"prepare",Request(HeroClassDto.Mage,3),Ct)).Preparation!;
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,clock,metrics);
        await matcher.EnqueueAsync(player,"queue",new(preparation.PreparationId),Ct);clock.Now=clock.Now.AddSeconds(31);
        var pending=Assert.IsType<PendingMatch>(await matcher.TryCreateMatchAsync(Ct));
        await matcher.MarkReadyAsync(player,clock.Now,Ct);
        var launch=Assert.IsType<ReadyMatchLaunch>(await matcher.ClaimReadyMatchAsync(clock.Now,Ct));
        Assert.Equal("loan-mage",Assert.Single(launch.Assignment.Players,value=>!value.IsBot).BorrowedTemplateId);
        var snapshots=new RoomSnapshotRepository(db.DataSource,clock,metrics);
        await using (var rooms=new RoomRegistry(clock))
        {
            using var coordinator=new RoomReadyCoordinator(matcher,rooms,snapshots,new RealtimeEventStore(clock),new ConnectionRegistry(),clock,NullLogger<RoomReadyCoordinator>.Instance);
            Assert.True(await coordinator.ProcessNextAsync(clock.Now,Ct));
            Assert.True(rooms.ContainsRoom(pending.RoomId));
        }
        var stored=(await snapshots.GetAsync(pending.RoomId,Ct))!;
        var borrowed=Assert.Single(stored.Players,value=>value.PlayerId==player);
        Assert.Equal("loan-mage",borrowed.BorrowedTemplateId);
        Assert.Equal(3,borrowed.Combat.WeaponLevel);
        Assert.All(borrowed.Combat.Deck.Hand.Concat(borrowed.Combat.Deck.Library).Concat(borrowed.Combat.Deck.Discard),card=>Assert.Equal(3,card.Level));
        var invalid=stored with {Revision=stored.Revision+20,Players=stored.Players.Select(value=>value.PlayerId==player?value with {BorrowedTemplateId=null}:value).ToArray()};
        await Assert.ThrowsAsync<InvalidOperationException>(()=>snapshots.SaveIfDueAsync(invalid,Ct));
        if(mutation!="valid")
        {
            // Locate by ID, never depend on the randomized player array order.
            await Sql(db,"""
                UPDATE room_snapshots s SET snapshot_json=jsonb_set(snapshot_json,'{players}',
                    (SELECT jsonb_agg(CASE WHEN p->>'playerId'=$2 THEN
                        CASE WHEN $3='missing' THEN p-'borrowedTemplateId'
                            WHEN $3='bot' THEN jsonb_set(p-'borrowedTemplateId','{isBot}','true')
                            ELSE jsonb_set(p,'{borrowedTemplateId}','"loan-priest"') END
                        ELSE p END) FROM jsonb_array_elements(s.snapshot_json->'players') p)) WHERE room_id=$1
                """,pending.RoomId,player.ToString("D"),mutation);
        }
        var raw=await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",pending.RoomId);
        var health=new RoomRecoveryState();await using var recovered=new RoomRegistry(clock);
        await new RoomRecoveryWorker(snapshots,recovered,health,clock,NullLogger<RoomRecoveryWorker>.Instance).StartAsync(Ct);
        Assert.Equal(mutation=="valid",health.Capture().IsHealthy);
        Assert.Equal(mutation=="valid",recovered.ContainsRoom(pending.RoomId));
        Assert.Equal(raw,await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",pending.RoomId));
        Assert.Equal(before,await AssetsAsync(db,player));
        if(mutation!="valid")
        {
            await Assert.ThrowsAsync<InvalidOperationException>(()=>snapshots.GetAsync(pending.RoomId,Ct));
            Assert.Equal([pending.RoomId],health.Capture().FailedRoomIds);
        }
        else
        {
            await recovered.RemoveAsync(pending.RoomId);
            var terminal=stored with {Revision=stored.Revision+30,Players=stored.Players.Select(value=>value with {Phase=RoomPlayerPhase.Extracted,Pve=null}).ToArray()};
            await Sql(db,"UPDATE match_players SET state='Settled' WHERE match_id=$1",pending.MatchId);
            await snapshots.SaveIfDueAsync(terminal,Ct);
            Assert.Equal("loan-mage",Assert.Single((await snapshots.GetOwnedTerminalAsync(player,pending.RoomId,pending.MatchId,Ct))!.Snapshot.Players,value=>value.PlayerId==player).BorrowedTemplateId);
        }
    }

    private static CreatePreparationRequest Request(HeroClassDto hero,int difficulty)=>new(hero,0,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D"+difficulty,"loans",true);
    private static SeasonDefinition Define()=>SeasonDefinition.FromCalendarDays("loans",new DateOnly(2026,11,2),GameConfigCatalog.Current.Version,"loan-stats",highestOpenDifficulty:5);
    private static async Task<Guid> PlayerAsync(PostgresTestSchema db,Clock clock)=>(await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(Guid.NewGuid().ToString("N"),"Borrow "+Guid.NewGuid().ToString("N")[..8],RandomNumberGenerator.GetBytes(32),clock.Now,clock.Now.AddHours(1),Ct)).UserId;
    private static Task<string> AssetsAsync(PostgresTestSchema db,Guid player)=>db.ScalarAsync<string>("""
        SELECT jsonb_build_object(
            'cards',(SELECT jsonb_agg(to_jsonb(c) ORDER BY card_id) FROM player_cards c WHERE player_id=$1),
            'weapons',(SELECT jsonb_agg(to_jsonb(w) ORDER BY hero_class) FROM class_weapons w WHERE player_id=$1),
            'decks',(SELECT jsonb_agg(to_jsonb(d) ORDER BY hero_class) FROM player_decks d WHERE player_id=$1),
            'slots',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.deck_id,c.slot_index) FROM player_deck_cards c JOIN player_decks d ON d.deck_id=c.deck_id WHERE d.player_id=$1),
            'consumables',(SELECT to_jsonb(c) FROM player_consumables c WHERE player_id=$1))::text
        """,player);
    private static async Task Sql(PostgresTestSchema db,string sql,params object[] values)
    {
        await using var command=db.DataSource.CreateCommand(sql);
        foreach(var value in values)command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
    private sealed class Clock(DateTimeOffset now):TimeProvider
    {
        public DateTimeOffset Now{get;set;}=now;
        public override DateTimeOffset GetUtcNow()=>Now;
    }
}
