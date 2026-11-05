using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresRewardRefreshFundingTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualRouterUsesOriginalQuoteAndSeasonWalletAndRestartReplaysWithoutAnotherPayment()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db,temporaryGold:3);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);using var metrics=new ServerMetrics();
        var snapshots=new RoomSnapshotRepository(db.DataSource,f.Clock,metrics);
        await using var rooms=new RoomRegistry(f.Clock);rooms.Register(f.Room,f.Match,startTicker:false);
        var lobby=RewardRefreshOriginalConfigTests.CreateConfig("refresh-next",alternate:true).Catalog;
        using var archive=new ConfigArchiveDirectory();
        PublishedConfigTestInputs.Store(archive.Root,f.Config.Version,f.Bytes,f.Config.ContentHash);
        var catalogs=new PublishedConfigCatalogs(lobby,archive.Root);
        var events=new RealtimeEventStore(f.Clock);var profile=PlayerProfile.Create(f.Player,"Refresh",f.Clock.Now);
        var command=new ClientCommand("choice.refresh","router-original",f.Room.Revision,new RewardChoiceRefreshCommandPayload());
        var first=await new RealtimeCommandRouter(events,f.Clock,rooms,economy,roomSnapshotRepository:snapshots,configurations:catalogs)
            .RouteAsync(profile,command,"refresh",Ct);
        Assert.Contains(first,e=>e.Type=="reward.choice");Assert.DoesNotContain(first,e=>e.Type.StartsWith("error.",StringComparison.Ordinal));
        Assert.Equal(96L,await Gold(db,f));Assert.Equal(0,f.Room.GetPlayer(f.Player).Inventory.GoldQuantity);
        Assert.Equal("Applied",(await economy.GetRewardRefreshAsync(f.Player,command.RequestId!,Ct))!.State);
        var restored=BattleRoom.Restore((await snapshots.GetAsync(f.Room.RoomId,Ct))!,CombatCardCatalog.Create(f.Config),73);
        await using var restarted=new RoomRegistry(f.Clock);restarted.Register(restored,f.Match,startTicker:false);
        var replay=await new RealtimeCommandRouter(events,f.Clock,restarted,economy,roomSnapshotRepository:new(db.DataSource,f.Clock,metrics),configurations:catalogs)
            .RouteAsync(profile,command,"restart",Ct);
        Assert.Equivalent(first.Single(e=>e.Type=="reward.choice").Payload,replay.Single(e=>e.Type=="reward.choice").Payload,strict:true);
        Assert.Equal(96L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));
        Assert.False(await economy.RefundReservedRewardRefreshAsync(f.Player,command.RequestId!,Ct));
        await AssertContext(db,f,1);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task InsufficientSeasonGoldNeverFallsBackToTheRichLegacyWallet()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_wallets SET gold=2 WHERE player_id=$1",f.Player);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        await Assert.ThrowsAsync<DomainValidationException>(()=>Reserve(economy,f,"short",7));
        Assert.Equal(2L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM reward_refresh_operations"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason LIKE 'reward.choice.refresh.%'"));
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData(false)] [InlineData(true)]
    [Trait("Category","PostgresIntegration")]
    public async Task RunningOldRoomCanPayAndRefundOnlyItsOriginalArchivedWalletAcrossRollover(bool reserveAfterRollover)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        if(!reserveAfterRollover)await Reserve(economy,f,"rollover",7);
        f.Clock.Now=f.Season.EndsAtUtc;
        var nextConfig=RewardRefreshOriginalConfigTests.CreateConfig("refresh-next",alternate:true).Catalog;
        var next=new SeasonDefinition("refresh-next-season","season-v1",nextConfig.Version,"next-stats",f.Clock.Now,f.Clock.Now.AddDays(42),5);
        var seasons=new SeasonRepository(db.DataSource,f.Clock);await seasons.PublishAsync(next,nextConfig.ContentHash,Ct);
        await seasons.EnsurePlayerAsync(f.Player,next.ContextFor(0),Ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_wallets SET gold=200 WHERE player_id=$1 AND season_id=$2",f.Player,next.SeasonId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_wallets SET archived_at=$3 WHERE player_id=$1 AND season_id=$2",f.Player,f.Season.SeasonId,f.Clock.Now);
        if(reserveAfterRollover)await Reserve(economy,f,"rollover",7);
        Assert.Equal(93L,await Gold(db,f));
        await CraftingTestInputs.SqlAsync(db,"UPDATE matches SET status='Completed' WHERE match_id=$1",f.Match);
        using var restarted=new EconomyRepository(db.DataSource,f.Clock);
        Assert.True(await restarted.RefundReservedRewardRefreshAsync(f.Player,"rollover",Ct));
        Assert.False(await restarted.RefundReservedRewardRefreshAsync(f.Player,"rollover",Ct));
        Assert.Equal(100L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));
        Assert.Equal(200L,await db.ScalarAsync<long>("SELECT gold FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",f.Player,next.SeasonId));
        Assert.Equal("Refunded",(await Reserve(restarted,f,"rollover",7)).State);
        await AssertContext(db,f,2);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ConcurrentReplayHasOneDebitAndOneRefundAndConflictingIdentityCannotSpend()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        var reservations=await Task.WhenAll(Enumerable.Range(0,4).Select(_=>Reserve(economy,f,"same",7)));
        Assert.All(reservations,r=>Assert.Equal("Reserved",r.State));Assert.Equal(93L,await Gold(db,f));
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>Reserve(economy,f,"same",8));
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>economy.ReserveRewardRefreshAsync(f.Player,f.Match,Guid.NewGuid(),f.Room.Revision,7,"same",Ct));
        var refunds=await Task.WhenAll(Enumerable.Range(0,4).Select(_=>economy.RefundReservedRewardRefreshAsync(f.Player,"same",Ct)));
        Assert.Single(refunds,result=>result);Assert.Equal(100L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM reward_refresh_operations"));await AssertContext(db,f,2);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task FaultAfterWalletDebitRollsBackTheReservationAndLedgerAndSameRequestCanRetry()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        await db.ExecuteAsync("""
            CREATE FUNCTION fail_refresh_reserve() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated refresh commit fault'; END $$;
            CREATE TRIGGER fail_refresh_reserve BEFORE INSERT ON reward_refresh_operations FOR EACH ROW EXECUTE FUNCTION fail_refresh_reserve();
            """);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        await Assert.ThrowsAsync<PostgresException>(()=>Reserve(economy,f,"retry",7));
        Assert.Equal(100L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE reason='reward.choice.refresh.reserve'"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='reward.choice.refresh.reserve'"));
        await db.ExecuteAsync("DROP TRIGGER fail_refresh_reserve ON reward_refresh_operations");
        await Reserve(economy,f,"retry",7);Assert.Equal(93L,await Gold(db,f));await AssertContext(db,f,1);
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("room")] [InlineData("owner")] [InlineData("bot")] [InlineData("settled")] [InlineData("not-running")]
    [Trait("Category","PostgresIntegration")]
    public async Task MissingAdmissionCannotChargeEitherWallet(string changed)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        var player=f.Player;var room=f.Room.RoomId;
        if(changed=="room")room=Guid.NewGuid();
        if(changed=="owner")player=await CraftingTestInputs.PlayerAsync(db,f.Clock);
        if(changed=="bot")await CraftingTestInputs.SqlAsync(db,"UPDATE match_players SET is_bot=true WHERE match_id=$1",f.Match);
        if(changed=="settled")await CraftingTestInputs.SqlAsync(db,"UPDATE match_players SET state='Settled' WHERE match_id=$1",f.Match);
        if(changed=="not-running")await CraftingTestInputs.SqlAsync(db,"UPDATE matches SET status='Completed' WHERE match_id=$1",f.Match);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        await Assert.ThrowsAsync<DomainValidationException>(()=>economy.ReserveRewardRefreshAsync(player,f.Match,room,f.Room.Revision,7,"invalid",Ct));
        Assert.Equal(100L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM reward_refresh_operations"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task GeneralWalletApiCannotUseRoomReservePurposeWithoutAMatchProof()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        await Assert.ThrowsAsync<DomainValidationException>(()=>new SeasonRepository(db.DataSource,f.Clock).ApplyAsync(f.Player,f.Room.Season!,-7,0,0,
            "reward.choice.refresh.reserve","no-proof",SeasonWalletPurpose.RoomRefreshReserve,Ct));
        Assert.Equal(100L,await Gold(db,f));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task RecoveryUsesTheDurableReceiptOrRefundsOnlyTheRecordedSeasonPayer()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);using var metrics=new ServerMetrics();
        await Reserve(economy,f,"applied-before-crash",7);await Reserve(economy,f,"reserved-before-crash",7);
        f.Room.RefreshRewardChoice(f.Player,f.Room.Revision,7,"applied-before-crash");
        var snapshots=new RoomSnapshotRepository(db.DataSource,f.Clock,metrics);await snapshots.SaveIfDueAsync(f.Room.Capture(),Ct);
        f.Clock.Now=f.Clock.Now.AddSeconds(31);
        await using var rooms=new RoomRegistry(f.Clock);
        using var worker=new RewardRefreshRecoveryWorker(economy,rooms,snapshots,f.Clock,NullLogger<RewardRefreshRecoveryWorker>.Instance);
        await worker.StartAsync(Ct);
        await db.WaitForScalarAsync(0L,"SELECT count(*) FROM reward_refresh_operations WHERE state='Reserved'");
        await worker.StopAsync(Ct);
        Assert.Equal("Applied",(await economy.GetRewardRefreshAsync(f.Player,"applied-before-crash",Ct))!.State);
        Assert.Equal("Refunded",(await economy.GetRewardRefreshAsync(f.Player,"reserved-before-crash",Ct))!.State);
        Assert.Equal(93L,await Gold(db,f));Assert.Equal(900L,await Legacy(db,f));await AssertContext(db,f,3);
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData(false)] [InlineData(true)]
    [Trait("Category","PostgresIntegration")]
    public async Task V048ReservationsKeepTheirActualLegacyPayerEvenWhenTheirMatchWasSeasonal(bool seasonalMatch)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:false);await ApplyThrough48(db);
        var f=await Create(db,legacy:!seasonalMatch);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_wallets SET gold=gold-7 WHERE player_id=$1",f.Player);
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO reward_refresh_operations(player_id,request_id,match_id,room_id,expected_revision,account_gold,state,recover_after,created_at,updated_at)
            VALUES($1,'before-v49',$2,$3,$4,7,'Reserved',$5,$5,$5)
            """,f.Player,f.Match,f.Room.RoomId,f.Room.Revision,f.Clock.Now);
        await db.MigrateAsync();
        Assert.Equal("LegacyWallet",await db.ScalarAsync<string>("SELECT funding_scope FROM reward_refresh_operations"));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM reward_refresh_operations WHERE season_id IS NULL AND config_version IS NULL AND stats_version IS NULL"));
        f.Clock.Now=f.Season.EndsAtUtc;
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        Assert.True(await economy.RefundReservedRewardRefreshAsync(f.Player,"before-v49",Ct));
        Assert.False(await economy.RefundReservedRewardRefreshAsync(f.Player,"before-v49",Ct));
        Assert.Equal(900L,await Legacy(db,f));Assert.Equal(100L,await Gold(db,f));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='reward.choice.refresh.refund' AND season_id IS NULL AND config_version IS NULL AND delta=7"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task NewLegacyRoomKeepsItsLegacyWalletAndOriginalConfigInBothLedgerEntries()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db,legacy:true);
        using var economy=new EconomyRepository(db.DataSource,f.Clock);
        await Reserve(economy,f,"legacy",7);Assert.Equal(893L,await Legacy(db,f));Assert.Equal(100L,await Gold(db,f));
        Assert.True(await economy.RefundReservedRewardRefreshAsync(f.Player,"legacy",Ct));Assert.Equal(900L,await Legacy(db,f));
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason LIKE 'reward.choice.refresh.%' AND source_kind='RoomRewardRefresh' AND season_id IS NULL AND difficulty_id='Standard' AND config_version=$1",f.Config.Version));
    }

    private sealed record Fixture(Guid Player,Guid Match,BattleRoom Room,GameConfigCatalog Config,byte[] Bytes,SeasonDefinition Season,CraftingClock Clock);
    private static async Task<Fixture> Create(PostgresTestSchema db,int temporaryGold=0,bool legacy=false)
    {
        var source=RewardRefreshOriginalConfigTests.CreateConfig("refresh-original");var config=source.Catalog;
        var season=SeasonDefinition.FromCalendarDays("archive-season",new(2026,11,1),config.Version,"archive-control-stats",highestOpenDifficulty:5);
        var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));var player=await CraftingTestInputs.PlayerAsync(db,clock);
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,config.ContentHash,Ct);
        await seasons.EnsurePlayerAsync(player,season.ContextFor(5),Ct);
        await seasons.ApplyAsync(player,season.ContextFor(5),100,0,0,"test.refresh-funding","seed",SeasonWalletPurpose.General,Ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_wallets SET gold=900 WHERE player_id=$1",player);
        var room=RewardRefreshOriginalConfigTests.ChoiceRoom(config,player,temporaryGold,legacy);var match=Guid.NewGuid();
        Guid? preparationId=null;
        if(!legacy)
        {
            await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",player);
            var deckVersion=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",player);
            var prepared=await new PreparationRepository(db.DataSource,clock,configurations:new(config)).CreateAsync(player,"refresh-preparation",
                new(HeroClassDto.Mage,deckVersion,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D5",season.SeasonId,
                    LootPreferenceElement:room.GetPlayer(player).LootPreferenceElement),Ct);
            Assert.Equal(CreatePreparationStatus.Created,prepared.Status);
            preparationId=prepared.Preparation!.PreparationId;
            Assert.Null(prepared.Preparation.Snapshot.BorrowedTemplateId);
            Assert.Equal(room.GetPlayer(player).LootPreferenceElement,prepared.Preparation.Snapshot.LootPreferenceElement);
        }
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm',$3,73,$4,'Running',$5,$6,$7,$8)
            """,match,room.RoomId,legacy?"Standard":"D5",config.Version,clock.Now,
            legacy?DBNull.Value:season.SeasonId,legacy?DBNull.Value:season.RulesetId,legacy?DBNull.Value:season.StatsVersion);
        await using(var participant=db.DataSource.CreateCommand("INSERT INTO match_players(match_id,player_id,is_bot,state,preparation_id) VALUES($1,$2,false,'Active',$3)"))
        {
            participant.Parameters.AddWithValue(match);participant.Parameters.AddWithValue(player);
            participant.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Uuid,(object?)preparationId??DBNull.Value);
            await participant.ExecuteNonQueryAsync(Ct);
        }
        return new(player,match,room,config,source.Bytes,season,clock);
    }
    private static Task<RewardRefreshReservation> Reserve(EconomyRepository economy,Fixture f,string request,long amount)=>
        economy.ReserveRewardRefreshAsync(f.Player,f.Match,f.Room.RoomId,f.Room.Revision,amount,request,Ct);
    private static Task<long> Gold(PostgresTestSchema db,Fixture f)=>db.ScalarAsync<long>("SELECT gold FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",f.Player,f.Season.SeasonId);
    private static Task<long> Legacy(PostgresTestSchema db,Fixture f)=>db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",f.Player);
    private static async Task AssertContext(PostgresTestSchema db,Fixture f,long count)
    {
        Assert.Equal(count,await db.ScalarAsync<long>("""
            SELECT count(*) FROM economy_ledger WHERE reason LIKE 'reward.choice.refresh.%' AND player_id=$1 AND season_id=$2
                AND difficulty_id='D5' AND ruleset_id='season-v1' AND config_version=$3 AND stats_version=$4
            """,f.Player,f.Season.SeasonId,f.Config.Version,f.Season.StatsVersion));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM reward_refresh_operations WHERE funding_scope<>'SeasonWallet'"));
    }
    private static async Task ApplyThrough48(PostgresTestSchema db)
    {
        await db.ExecuteAsync("CREATE TABLE schema_migrations(version integer PRIMARY KEY,name varchar(160) NOT NULL,checksum varchar(64) NOT NULL,applied_at timestamptz NOT NULL)");
        var assembly=typeof(DatabaseMigrator).Assembly;
        foreach(var resource in assembly.GetManifestResourceNames().Where(n=>n.Contains(".Persistence.Migrations.V",StringComparison.Ordinal)&&n.EndsWith(".sql",StringComparison.Ordinal)).Order(StringComparer.Ordinal))
        {
            var filename=resource[(resource.LastIndexOf(".V",StringComparison.Ordinal)+1)..];
            var version=int.Parse(filename.AsSpan(1,3),CultureInfo.InvariantCulture);if(version>48)continue;
            await using var stream=assembly.GetManifestResourceStream(resource)!;using var reader=new StreamReader(stream,Encoding.UTF8);
            var sql=await reader.ReadToEndAsync(Ct);await db.ExecuteAsync(sql);
            var hash=Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(sql.Replace("\r\n","\n",StringComparison.Ordinal))));
            await CraftingTestInputs.SqlAsync(db,"INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES($1,$2,$3,now())",version,filename[6..^4],hash);
        }
    }
}
