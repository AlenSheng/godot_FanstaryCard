using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonArchiveTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private const string Required="Requires isolated PostgreSQL.";

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task BoundedPagesResumeWithOriginalLoadoutAndNeverMoveNewSeasonOrPermanentAssets()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        var oldItems=new List<Guid>();for(var i=0;i<7;i++)oldItems.Add(await CraftingTestInputs.ItemAsync(db,p,level:3));
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='Equipped' WHERE instance_id=$1",oldItems[0]);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_loadouts SET chest_id=$1 WHERE player_id=$2 AND hero_class=2",oldItems[0],p.Player);
        var next=await Next(db,p);var newItem=await CraftingTestInputs.ItemAsync(db,p with {Season=next},slot:"Head");
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_loadouts SET head_id=$1 WHERE player_id=$2 AND hero_class=2",newItem,p.Player);
        var before=await Permanent(db,p.Player);var seen=new List<SeasonArchivePage>();
        for(var page=0;page<5;page++)
        {
            // Recreate the repository between pages, rather than retain an in-memory cursor.
            var step=await new SeasonRepository(db.DataSource,p.Clock).AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,2,Ct);
            Assert.InRange(step.ArchivedItems,0,2);seen.Add(step);if(step.Status=="Completed")break;
        }
        Assert.Equal(4,seen.Count);Assert.Equal(7,seen.Sum(x=>x.ArchivedItems));Assert.Equal("Completed",seen[^1].Status);
        Assert.Single(seen.Select(x=>x.JobId).Distinct());
        Assert.Equal(7L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND season_id=$2 AND asset_scope='ArchivedSeason' AND location='SeasonArchive' AND level=3",p.Player,p.Season.SeasonId));
        Assert.Equal(7L,await db.ScalarAsync<long>("SELECT count(*) FROM season_archive_items WHERE player_id=$1",p.Player));
        Assert.Equal(oldItems[0],await db.ScalarAsync<Guid>("SELECT chest_id FROM season_archive_loadouts WHERE player_id=$1 AND hero_class=2",p.Player));
        Assert.Equal(newItem,await db.ScalarAsync<Guid>("SELECT head_id FROM player_loadouts WHERE player_id=$1 AND hero_class=2",p.Player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_loadouts WHERE player_id=$1 AND chest_id IS NOT NULL",p.Player));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND asset_scope='ActiveSeason' AND location='Inventory'",newItem));
        Assert.Equal(before,await Permanent(db,p.Player));
        var replay=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,2,Ct);Assert.Equal(0,replay.ArchivedItems);
        Assert.Equal(7L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='season.archive'",p.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ConcurrentWorkersCommitEachOriginalItemExactlyOnce()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        for(var i=0;i<9;i++)await CraftingTestInputs.ItemAsync(db,p);p.Clock.Now=p.Season.EndsAtUtc;
        var pages=await Task.WhenAll(Enumerable.Range(0,12).Select(_=>new SeasonRepository(db.DataSource,p.Clock).AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,1,Ct)));
        Assert.Single(pages.Select(x=>x.JobId).Distinct());Assert.Equal(9,pages.Sum(x=>x.ArchivedItems));
        Assert.Equal(9L,await db.ScalarAsync<long>("SELECT count(*) FROM season_archive_items"));
        Assert.Equal(9L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='season.archive'"));
        Assert.Equal("Completed",await db.ScalarAsync<string>("SELECT status FROM season_archive_jobs"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task MidPageDatabaseFaultRollsBackItemsAndCursorThenRecreatedWorkerContinuesTheSameJob()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        for(var i=0;i<5;i++)await CraftingTestInputs.ItemAsync(db,p);p.Clock.Now=p.Season.EndsAtUtc;
        var first=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,1,Ct);
        await CraftingTestInputs.SqlAsync(db,"""
            CREATE FUNCTION fail_archive_page() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
                IF (SELECT count(*) FROM season_archive_items) = 3 THEN RAISE EXCEPTION 'injected archive page failure'; END IF;
                RETURN NEW; END $$;
            CREATE TRIGGER fail_archive_page AFTER INSERT ON season_archive_items FOR EACH ROW EXECUTE FUNCTION fail_archive_page();
            """);
        var failure=await Assert.ThrowsAsync<PostgresException>(()=>p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,3,Ct));
        Assert.Equal("P0001",failure.SqlState);await p.Seasons.MarkArchiveFailureAsync(new(p.Player,p.Season.SeasonId),"postgres.P0001",Ct);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM season_archive_items"));
        Assert.Equal(first.Cursor,await db.ScalarAsync<Guid>("SELECT cursor_id FROM season_archive_jobs"));
        Assert.Equal("Failed",await db.ScalarAsync<string>("SELECT status FROM season_archive_jobs"));
        await CraftingTestInputs.SqlAsync(db,"DROP TRIGGER fail_archive_page ON season_archive_items");
        var resumed=await new SeasonRepository(db.DataSource,p.Clock).AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct);
        Assert.Equal(first.JobId,resumed.JobId);Assert.Equal("Completed",resumed.Status);Assert.Equal(4,resumed.ArchivedItems);
        Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='season.archive'"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task UnsettledOldMatchRemainsWaitingAndItsOriginalEquipmentIsNotTakenFromTheRoom()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        var active=await CraftingTestInputs.ItemAsync(db,p);var safe=await CraftingTestInputs.ItemAsync(db,p);var match=Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)
            """,match,Guid.NewGuid(),GameConfigCatalog.Current.Version,p.Clock.Now,p.Season.SeasonId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,p.Player);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1",active);
        p.Clock.Now=p.Season.EndsAtUtc;var page=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct);
        Assert.Equal("WaitingAssets",page.Status);Assert.Equal(1,page.ArchivedItems);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='InMatchEquipped' AND asset_scope='ActiveSeason'",active));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='SeasonArchive'",safe));
        // Declared durable settlement-completion fixture; real late settlement is
        // separately covered by PostgresSeasonSettlementTests, not simulated here.
        await CraftingTestInputs.SqlAsync(db,"UPDATE match_players SET settled_at=$2 WHERE match_id=$1",match,p.Clock.Now);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='Inventory',asset_scope='ArchivedSeason' WHERE instance_id=$1",active);
        var terminal=await new SeasonRepository(db.DataSource,p.Clock).AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct);
        Assert.Equal(page.JobId,terminal.JobId);Assert.Equal("Completed",terminal.Status);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task FullWarehouseExpiryRetainsTheOriginalHeldItemAndArchiveNeedsNoFreeActiveSlot()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        p.Clock.Now=p.Season.EndsAtUtc.AddHours(-1);var listed=await CraftingTestInputs.ItemAsync(db,p,"Orange",level:3);
        var market=new EconomyRepository(db.DataSource,p.Clock);
        await market.ListAsync(p.Player,"archive-list",new CreateMarketListingRequest(listed,100,"Gold",100,p.Season.SeasonId,1),Ct);
        for(var i=0;i<50;i++)await CraftingTestInputs.ItemAsync(db,p,"Blue",effect:null);
        p.Clock.Now=p.Season.EndsAtUtc;
        var first=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,32,Ct);Assert.Equal(32,first.ArchivedItems);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM market_return_holds WHERE equipment_id=$1 AND state='Pending'",listed));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='MarketReturnPending' AND asset_scope='ArchivedSeason' AND level=3",listed));
        var last=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,32,Ct);Assert.Equal("Completed",last.Status);
        Assert.Equal(50L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location='SeasonArchive'",p.Player));
        Assert.Equal(51L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1",p.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ArchivedWalletStillAcceptsOnlyOriginalLateCreditAndNeverFundsTheNextSeason()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);var next=await Next(db,p);
        await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct);
        var before=await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct);Assert.NotNull(before!.ArchivedAt);
        var late=await p.Seasons.ApplyAsync(p.Player,p.Season.ContextFor(0),123,17,0,"test.late","late-one",SeasonWalletPurpose.LateSettlement,Ct);
        Assert.Equal(before.Gold+123,late.Gold);Assert.Equal(before.EquipmentFragments+17,late.EquipmentFragments);Assert.Equal(before.ArchivedAt,late.ArchivedAt);
        Assert.Equal(0,(await p.Seasons.GetWalletAsync(p.Player,next.ContextFor(0),Ct))!.Gold);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Seasons.ApplyAsync(p.Player,p.Season.ContextFor(0),-1,0,0,"test.old-spend","old-spend",SeasonWalletPurpose.General,Ct));
        Assert.Equal("Completed",await db.ScalarAsync<string>("SELECT status FROM season_archive_jobs"));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ActiveAndUnknownSeasonsCannotCreateArchiveJobsAndScanBoundsRemainExplicit()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        Assert.Empty(await p.Seasons.GetArchiveWorkAsync(32,Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Seasons.AdvanceArchivePageAsync(p.Player,"unknown-season",10,Ct));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(()=>p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,101,Ct));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(()=>p.Seasons.GetArchiveWorkAsync(101,Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM season_archive_jobs"));
        p.Clock.Now=p.Season.EndsAtUtc;var work=Assert.Single(await p.Seasons.GetArchiveWorkAsync(32,Ct));Assert.Equal(p.Player,work.PlayerId);
        await p.Seasons.MarkArchiveFailureAsync(work,"archive.page.failed",Ct);
        Assert.Empty(await p.Seasons.GetArchiveWorkAsync(32,Ct));p.Clock.Now=p.Clock.Now.AddSeconds(6);
        Assert.Single(await p.Seasons.GetArchiveWorkAsync(32,Ct));
        Assert.Equal("Completed",(await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct)).Status);
        Assert.Empty(await p.Seasons.GetArchiveWorkAsync(32,Ct));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task HostedWorkerRunsTheDurableArchiveWithoutAnyGameActorOrOnlineClient()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var p=await CraftingTestInputs.CreateAsync(db);
        await CraftingTestInputs.ItemAsync(db,p);p.Clock.Now=p.Season.EndsAtUtc;
        using var worker=new SeasonArchiveWorker(p.Seasons,TimeProvider.System,NullLogger<SeasonArchiveWorker>.Instance);
        await worker.StartAsync(Ct);
        try
        {
            using var deadline=CancellationTokenSource.CreateLinkedTokenSource(Ct);deadline.CancelAfter(TimeSpan.FromSeconds(20));
            while(await db.ScalarAsync<long>("SELECT count(*) FROM season_archive_jobs WHERE status='Completed'")!=1)
                await Task.Delay(50,deadline.Token);
            Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location='SeasonArchive'",p.Player));
        }
        finally { await worker.StopAsync(Ct); }
    }

    private static async Task<SeasonDefinition> Next(PostgresTestSchema db,CraftingPlayer p)
    {
        var next=SeasonDefinition.FromCalendarDays("archive-next",DateOnly.FromDateTime(p.Season.EndsAtUtc.AddHours(8).DateTime),GameConfigCatalog.Current.Version,p.Season.StatsVersion,highestOpenDifficulty:5);
        await p.Seasons.PublishAsync(next,GameConfigCatalog.Current.ContentHash,Ct);p.Clock.Now=next.StartsAtUtc;
        await p.Seasons.EnsurePlayerAsync(p.Player,next.ContextFor(0),Ct);return next;
    }

    private static Task<string> Permanent(PostgresTestSchema db,Guid player)=>db.ScalarAsync<string>("""
        SELECT jsonb_build_object('wallet',(SELECT to_jsonb(w) FROM player_wallets w WHERE player_id=$1),
            'materials',(SELECT to_jsonb(m) FROM player_materials m WHERE player_id=$1),
            'cards',(SELECT jsonb_agg(to_jsonb(c) ORDER BY card_id) FROM player_cards c WHERE player_id=$1),
            'weapons',(SELECT jsonb_agg(to_jsonb(w) ORDER BY hero_class) FROM class_weapons w WHERE player_id=$1),
            'decks',(SELECT jsonb_agg(to_jsonb(d) ORDER BY hero_class) FROM player_decks d WHERE player_id=$1))::text
        """,player);
}
