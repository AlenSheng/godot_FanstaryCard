using System.Text.Json;
using FantasyCard.ConfigExporter;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonShopTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private sealed record Fixture(Guid Player,SeasonDefinition Season,CraftingClock Clock,EconomyRepository Shop,SeasonRepository Seasons);
    private static Task Sql(PostgresTestSchema db,string sql,params object[] args)=>CraftingTestInputs.SqlAsync(db,sql,args);
    private static PurchaseShopRequest Request(ShopResponse shop,string id,int quantity=1)
    {
        var offer=shop.Products.Single(p=>p.ProductId==id);
        return new(id,quantity,shop.Policy!.SeasonId,shop.ResetKey,shop.RotationKey,offer.PriceGold,shop.Policy.CatalogVersion);
    }
    private static async Task<Fixture> Create(PostgresTestSchema db,Func<int,int>? random=null)
    {
        var config=GameConfigCatalog.Current;var season=SeasonDefinition.FromCalendarDays("shop-a",new(2026,11,1),config.Version,"season-equipment-v1");
        var clock=new CraftingClock(season.StartsAtUtc.AddHours(12));var player=await CraftingTestInputs.PlayerAsync(db,clock);
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,config.ContentHash,Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        await seasons.ApplyAsync(player,season.ContextFor(0),5000,0,0,"test.shop-fund","fund",SeasonWalletPurpose.General,Ct);
        await Sql(db,"UPDATE player_wallets SET gold=777,diamond=88 WHERE player_id=$1",player);
        return new(player,season,clock,new(db.DataSource,clock,shopRandom:random),seasons);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task GoldAndFragmentsStayInTheOriginalSeasonWhileSoulsAndConsumablesStayPermanent()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);
        Assert.Equal("Active",view.Policy!.State);Assert.Equal(12,view.Products.Count);
        var first=await f.Shop.PurchaseAsync(f.Player,"fragments",Request(view,"equipment_fragments"),Ct);
        Assert.Equal(4880,first.GoldAfter);Assert.Equal(f.Season.SeasonId,first.SeasonId);
        var soul=await f.Shop.PurchaseAsync(f.Player,"souls",Request(view,"warrior_soul"),Ct);
        Assert.Equal(4700,soul.GoldAfter);await f.Shop.PurchaseAsync(f.Player,"potion",Request(view,"health_potion"),Ct);
        var wallet=await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct);Assert.Equal(4600,wallet!.Gold);Assert.Equal(20,wallet.EquipmentFragments);
        Assert.Equal(20,await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",f.Player));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1",f.Player));
        Assert.Equal(777,await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",f.Player));
        Assert.Equal(1,await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",f.Player));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ThreeClassChoicesShareOneAtomicDailyQuota()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);
        async Task<bool> Buy(string id)
        {try{await f.Shop.PurchaseAsync(f.Player,id,Request(view,id),Ct);return true;}catch(DomainValidationException){return false;}}
        Assert.Equal(1,(await Task.WhenAll(Buy("priest_soul"),Buy("mage_soul"),Buy("guardian_soul"))).Count(v=>v));
        var after=await f.Shop.GetShopAsync(f.Player,Ct);Assert.All(after.Products.Where(p=>p.Kind=="ClassSoul"),p=>Assert.Equal(1,p.Purchased));
        Assert.Equal(12,await db.ScalarAsync<long>("SELECT priest_soul+mage_soul+guardian_soul FROM player_materials WHERE player_id=$1",f.Player));
        Assert.Equal(4600,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.Gold);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task PaidBagsUseOneThreeItemStorageCapButNoInventedDailyPurchaseLimit()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);
        Assert.Equal(0,view.Products.Single(p=>p.ProductId=="advanced_bag").Limit);
        await f.Shop.PurchaseAsync(f.Player,"three",Request(view,"advanced_bag",3),Ct);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>f.Shop.PurchaseAsync(f.Player,"full",Request(view,"advanced_bag"),Ct));
        await Sql(db,"UPDATE player_consumables SET advanced_bag_count=advanced_bag_count-1 WHERE player_id=$1",f.Player);
        await f.Shop.PurchaseAsync(f.Player,"fourth-history",Request(view,"advanced_bag"),Ct);
        Assert.Equal(4,await db.ScalarAsync<long>("SELECT sum(quantity)::bigint FROM shop_purchases WHERE player_id=$1",f.Player));
        Assert.Equal(3,await db.ScalarAsync<int>("SELECT advanced_bag_count+top_bag_count FROM player_consumables WHERE player_id=$1",f.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task AFullCodexCanBuyAPackWithThreeRepeatedCopiesAndAnAlreadyOwnedDailyCard()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db,_=>0);
        await Sql(db,"UPDATE player_cards SET unlocked=true,copy_count=1 WHERE player_id=$1",f.Player);
        var view=await f.Shop.GetShopAsync(f.Player,Ct);var result=await f.Shop.PurchaseAsync(f.Player,"pack",Request(view,"card_pack"),Ct);
        var grant=Assert.Single(result.Grants!);Assert.Equal(3,grant.Amount);Assert.False(grant.NewlyUnlocked);Assert.Equal(4,grant.CopiesAfter);
        var single=view.Products.First(p=>p.ProductId.StartsWith("daily_card_",StringComparison.Ordinal));Assert.True(single.AlreadyOwned);
        var bought=await f.Shop.PurchaseAsync(f.Player,"single",Request(view,single.ProductId),Ct);Assert.False(Assert.Single(bought.Grants!).NewlyUnlocked);
        Assert.Equal(220,(await new ProgressionRepository(db.DataSource,f.Clock).GetCardsAsync(f.Player,Ct)).Count(p=>p.Unlocked));
        Assert.Equal(2,await db.ScalarAsync<long>("SELECT count(*) FROM card_copy_ledger WHERE player_id=$1",f.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task DurablePurchaseReplayIsFrozenAcrossConcurrentCallsRestartAndFinalSeasonClosure()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);var request=Request(view,"equipment_fragments");
        var replies=await Task.WhenAll(Enumerable.Range(0,4).Select(_=>f.Shop.PurchaseAsync(f.Player,"same",request,Ct)));
        Assert.All(replies,r=>Assert.Equal(JsonSerializer.Serialize(replies[0]),JsonSerializer.Serialize(r)));
        f.Clock.Now=f.Season.EndsAtUtc.AddDays(8);
        var replay=await new EconomyRepository(db.DataSource,f.Clock).PurchaseAsync(f.Player,"same",request,Ct);
        Assert.Equal(JsonSerializer.Serialize(replies[0]),JsonSerializer.Serialize(replay));
        Assert.Equal(1,await db.ScalarAsync<long>("SELECT count(*) FROM shop_purchases WHERE player_id=$1",f.Player));
        Assert.Equal(20,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.EquipmentFragments);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ShanghaiFourOClockCreatesExactlyOneNewQuotaWindow()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);f.Clock.Now=new(2026,11,3,19,59,59,TimeSpan.Zero);
        var old=await f.Shop.GetShopAsync(f.Player,Ct);await f.Shop.PurchaseAsync(f.Player,"before",Request(old,"equipment_fragments",3),Ct);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"over",Request(old,"equipment_fragments"),Ct));
        f.Clock.Now=f.Clock.Now.AddSeconds(1);var next=await f.Shop.GetShopAsync(f.Player,Ct);Assert.NotEqual(old.ResetKey,next.ResetKey);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"stale",Request(old,"equipment_fragments"),Ct));
        await f.Shop.PurchaseAsync(f.Player,"after",Request(next,"equipment_fragments",3),Ct);
        Assert.Equal(120,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.EquipmentFragments);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task RequestsQueuedBeforeFourOClockCannotSpendTheNewWindowWithOldTerms()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);f.Clock.Now=new(2026,11,3,19,59,59,TimeSpan.Zero);
        var old=await f.Shop.GetShopAsync(f.Player,Ct);await f.Shop.PurchaseAsync(f.Player,"old-full",Request(old,"equipment_fragments",3),Ct);
        await using var gate=await db.DataSource.OpenConnectionAsync(Ct);await using var transaction=await gate.BeginTransactionAsync(Ct);
        await using(var q=new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE",gate,transaction))
        {q.Parameters.AddWithValue(f.Player);await q.ExecuteScalarAsync(Ct);}
        int pid;await using(var q=new NpgsqlCommand("SELECT pg_backend_pid()",gate,transaction))pid=(int)(await q.ExecuteScalarAsync(Ct))!;
        async Task<bool> Buy(PurchaseShopRequest request,string id)
        {try{await f.Shop.PurchaseAsync(f.Player,id,request,Ct);return true;}catch(DomainValidationException){return false;}}
        var pending=Enumerable.Range(0,4).Select(i=>Buy(Request(old,"equipment_fragments"),"queued-"+i)).ToArray();
        using var wait=CancellationTokenSource.CreateLinkedTokenSource(Ct);wait.CancelAfter(TimeSpan.FromSeconds(8));
        while(true)
        {
            await using var q=db.DataSource.CreateCommand("""
                WITH RECURSIVE queued(pid) AS (
                    SELECT pid FROM pg_stat_activity WHERE $1=ANY(pg_blocking_pids(pid))
                    UNION
                    SELECT a.pid FROM pg_stat_activity a JOIN queued q ON q.pid=ANY(pg_blocking_pids(a.pid)))
                SELECT count(DISTINCT pid)::integer FROM queued
                """);q.Parameters.AddWithValue(pid);
            if((int)(await q.ExecuteScalarAsync(wait.Token))!>=4)break;
            await Task.Delay(20,wait.Token);
        }
        f.Clock.Now=f.Clock.Now.AddSeconds(1);await transaction.CommitAsync(Ct);
        Assert.All(await Task.WhenAll(pending),result=>Assert.False(result));
        var current=await f.Shop.GetShopAsync(f.Player,Ct);Assert.NotEqual(old.ResetKey,current.ResetKey);
        var outcomes=await Task.WhenAll(Enumerable.Range(0,6).Select(i=>Buy(Request(current,"equipment_fragments"),"new-race-"+i)));
        Assert.Equal(3,outcomes.Count(result=>result));
        var wallet=await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct);Assert.Equal(120,wallet!.EquipmentFragments);Assert.Equal(4280,wallet.Gold);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task FirstSeasonShopAdoptionKeepsLegacySingleCardsRefreshesAndUsedAccountQuotas()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var clock=new CraftingClock(new(2026,11,4,2,0,0,TimeSpan.Zero));
        var player=await CraftingTestInputs.PlayerAsync(db,clock);await Sql(db,"UPDATE player_wallets SET gold=5000 WHERE player_id=$1",player);
        using var shop=new EconomyRepository(db.DataSource,clock);
        await shop.PurchaseAsync(player,"legacy-fragments",new("equipment_fragments",3),Ct);
        await shop.PurchaseAsync(player,"legacy-class",new("priest_soul"),Ct);
        for(var i=0;i<3;i++)await shop.RefreshShopAsync(player,"legacy-refresh-"+i,Ct);
        var legacy=await shop.GetShopAsync(player,Ct);
        var season=SeasonDefinition.FromCalendarDays("first-shop-season",new(2026,11,4),GameConfigCatalog.Current.Version,"season-equipment-v1");
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,GameConfigCatalog.Current.ContentHash,Ct);
        await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);await seasons.ApplyAsync(player,season.ContextFor(0),5000,0,0,"test.adoption","adoption",SeasonWalletPurpose.General,Ct);
        var current=await shop.GetShopAsync(player,Ct);Assert.Equal(3,current.RefreshesUsed);
        static (string Id,string? Card,long Price) Single(ShopProductResponse offer)
        {using var p=JsonDocument.Parse(offer.Payload);return (offer.ProductId,p.RootElement.GetProperty("cardId").GetString(),offer.PriceGold);}
        Assert.Equal(legacy.Products.Where(p=>p.ProductId.StartsWith("daily_card_",StringComparison.Ordinal)).Select(Single),
            current.Products.Where(p=>p.ProductId.StartsWith("daily_card_",StringComparison.Ordinal)).Select(Single));
        await Assert.ThrowsAsync<DomainValidationException>(()=>shop.RefreshShopAsync(player,"new-refresh",Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>shop.PurchaseAsync(player,"new-fragments",Request(current,"equipment_fragments"),Ct));
        Assert.All(current.Products.Where(p=>p.Kind=="ClassSoul"),p=>Assert.Equal(1,p.Purchased));
        await Assert.ThrowsAsync<DomainValidationException>(()=>shop.PurchaseAsync(player,"new-class",Request(current,"mage_soul"),Ct));
        await shop.PurchaseAsync(player,"legacy-fragments",new("equipment_fragments",3),Ct);
        Assert.Equal(60,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_materials WHERE player_id=$1",player));
        var wallet=await seasons.GetWalletAsync(player,season.ContextFor(0),Ct);Assert.Equal(0,wallet!.EquipmentFragments);Assert.Equal(5000,wallet.Gold);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task SwitchingSeasonsInsideOneBusinessDayDoesNotRefillAccountQuotaOrUseTheOldWallet()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);f.Clock.Now=f.Season.EndsAtUtc.AddMinutes(-10);
        var old=await f.Shop.GetShopAsync(f.Player,Ct);await f.Shop.PurchaseAsync(f.Player,"old-three",Request(old,"equipment_fragments",3),Ct);
        var next=SeasonDefinition.FromCalendarDays("shop-b",DateOnly.FromDateTime(f.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),GameConfigCatalog.Current.Version,"season-equipment-v1");
        await f.Seasons.PublishAsync(next,GameConfigCatalog.Current.ContentHash,Ct);f.Clock.Now=next.StartsAtUtc.AddMinutes(10);
        await f.Seasons.EnsurePlayerAsync(f.Player,next.ContextFor(0),Ct);await f.Seasons.ApplyAsync(f.Player,next.ContextFor(0),5000,0,0,"test.fund-b","fund-b",SeasonWalletPurpose.General,Ct);
        var view=await f.Shop.GetShopAsync(f.Player,Ct);Assert.Equal(old.ResetKey,view.ResetKey);Assert.Equal(old.RotationKey,view.RotationKey);
        Assert.Equal(3,view.Products.Single(p=>p.ProductId=="equipment_fragments").Purchased);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"blocked",Request(view,"equipment_fragments"),Ct));
        Assert.Equal(60,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.EquipmentFragments);
        Assert.Equal(0,(await f.Seasons.GetWalletAsync(f.Player,next.ContextFor(0),Ct))!.EquipmentFragments);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task SwitchingPublishedConfigKeepsTheFrozenDailyCatalogAndItsAlreadyUsedQuota()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);f.Clock.Now=f.Season.EndsAtUtc.AddMinutes(-10);
        var old=await f.Shop.GetShopAsync(f.Player,Ct);await f.Shop.PurchaseAsync(f.Player,"old-soul",Request(old,"warrior_soul"),Ct);
        var tables=XlsxConfigReader.Read(Path.Combine(PublishedConfigTestInputs.FindRoot(),"config/FantasyCard_Config.xlsx"));
        var bytes=ConfigCompiler.Compile("shop-config-next",tables,out var hash);var config=GameConfigCatalog.Load(bytes);
        using var archive=new ConfigArchiveDirectory();PublishedConfigTestInputs.Store(archive.Root,config.Version,bytes,hash);
        var next=SeasonDefinition.FromCalendarDays("shop-next",DateOnly.FromDateTime(f.Season.EndsAtUtc.ToOffset(TimeSpan.FromHours(8)).Date),config.Version,"season-equipment-v1");
        await f.Seasons.PublishAsync(next,hash,Ct,config);f.Clock.Now=next.StartsAtUtc.AddMinutes(10);await f.Seasons.EnsurePlayerAsync(f.Player,next.ContextFor(0),Ct);
        await f.Seasons.ApplyAsync(f.Player,next.ContextFor(0),5000,0,0,"test.fund-next","fund-next",SeasonWalletPurpose.General,Ct);
        using var repository=new EconomyRepository(db.DataSource,f.Clock,new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root));
        var view=await repository.GetShopAsync(f.Player,Ct);Assert.Equal(config.Version,view.Policy!.ConfigVersion);Assert.Equal(GameConfigCatalog.Current.Version,view.Policy.CatalogVersion);
        Assert.Equal(old.Products.Where(p=>p.ProductId.StartsWith("daily_card_",StringComparison.Ordinal)).Select(p=>(p.ProductId,p.Payload,p.PriceGold)),
            view.Products.Where(p=>p.ProductId.StartsWith("daily_card_",StringComparison.Ordinal)).Select(p=>(p.ProductId,p.Payload,p.PriceGold)));
        Assert.Equal(1,view.Products.Single(p=>p.ProductId=="warrior_soul").Purchased);
        await repository.PurchaseAsync(f.Player,"two-next",Request(view,"warrior_soul",2),Ct);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.PurchaseAsync(f.Player,"over-next",Request(view,"warrior_soul"),Ct));
        Assert.Equal(4820,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.Gold);
        Assert.Equal(4640,(await f.Seasons.GetWalletAsync(f.Player,next.ContextFor(0),Ct))!.Gold);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ACommitFaultRollsBackGoldFragmentsReceiptsAndReplayTogether()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);var request=Request(view,"equipment_fragments");
        await db.ExecuteAsync("CREATE FUNCTION fail_shop() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated shop commit fault'; END $$; CREATE TRIGGER shop_fault BEFORE INSERT ON shop_purchases FOR EACH ROW EXECUTE FUNCTION fail_shop();");
        await Assert.ThrowsAsync<PostgresException>(()=>f.Shop.PurchaseAsync(f.Player,"fault",request,Ct));
        var wallet=await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct);Assert.Equal(5000,wallet!.Gold);Assert.Equal(0,wallet.EquipmentFragments);
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT count(*) FROM shop_purchases WHERE player_id=$1",f.Player));
        await db.ExecuteAsync("DROP TRIGGER shop_fault ON shop_purchases;");await f.Shop.PurchaseAsync(f.Player,"fault",request,Ct);
        Assert.Equal(4880,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.Gold);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task MissingOrChangedTermsAndAnEmptySeasonWalletNeverSpendThePermanentGoldBalance()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);var request=Request(view,"warrior_soul");
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"old-client",new("warrior_soul"),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"price",request with {ExpectedPriceGold=1},Ct));
        await f.Seasons.ApplyAsync(f.Player,f.Season.ContextFor(0),-5000,0,0,"test.empty","empty",SeasonWalletPurpose.General,Ct);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"empty",request,Ct));
        Assert.Equal(777,await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",f.Player));
        Assert.Equal(0,await db.ScalarAsync<long>("SELECT warrior_soul FROM player_materials WHERE player_id=$1",f.Player));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ConcurrentGlobalRefreshesKeepThreeReceiptsAndDoNotResetAtUtcMidnight()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);f.Clock.Now=new(2026,11,3,23,59,0,TimeSpan.Zero);await f.Shop.GetShopAsync(f.Player,Ct);
        var players=new List<Guid>{f.Player};for(var i=0;i<5;i++)players.Add(await CraftingTestInputs.PlayerAsync(db,f.Clock));
        async Task<bool> Refresh(Guid player)
        {try{await f.Shop.RefreshShopAsync(player,"refresh",Ct);return true;}catch(DomainValidationException){return false;}}
        Assert.Equal(3,(await Task.WhenAll(players.Select(Refresh))).Count(v=>v));
        Assert.Equal(3,await db.ScalarAsync<long>("SELECT count(*) FROM season_shop_refresh_receipts"));
        f.Clock.Now=f.Clock.Now.AddMinutes(2);await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.RefreshShopAsync(f.Player,"utc",Ct));
        Assert.Equal(3,(await f.Shop.GetShopAsync(f.Player,Ct)).RefreshesUsed);
        var winner=await db.ScalarAsync<Guid>("SELECT player_id FROM season_shop_refresh_receipts LIMIT 1");
        Assert.True((await f.Shop.RefreshShopAsync(winner,"refresh",Ct)).Replayed);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task PermanentCopyAdoptionSurvivesClosureAndCannotBeBypassedByOpeningCardsBeforeTheShop()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);f.Clock.Now=f.Season.EndsAtUtc.AddDays(1);
        var player=await CraftingTestInputs.PlayerAsync(db,f.Clock);await Sql(db,"UPDATE player_cards SET level=3 WHERE player_id=$1 AND card_id='C01'",player);
        // Simulate an operator-created definition whose additive marker was not filled yet.
        await Sql(db,"UPDATE season_definitions SET permanent_card_rule=NULL WHERE season_id=$1",f.Season.SeasonId);
        var card=(await new ProgressionRepository(db.DataSource,f.Clock).GetCardsAsync(player,Ct)).Single(c=>c.CardId=="C01");
        Assert.Equal(1,card.UpgradeCopyCost);Assert.False(card.CanUpgrade);
        Assert.Equal(GameConfigCatalog.Current.Version,await db.ScalarAsync<string>("SELECT enabled_by_config FROM player_card_copy_modes WHERE player_id=$1",player));
        Assert.False((await f.Shop.GetShopAsync(player,Ct)).Policy!.CanPurchase);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task AnUnavailableOrAlteredFrozenCatalogDoesNotFallBackToCurrentPrices()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);var f=await Create(db);var view=await f.Shop.GetShopAsync(f.Player,Ct);
        await Sql(db,"UPDATE season_shop_days SET config_sha256=repeat('0',64) WHERE reset_key=$1",view.ResetKey);
        var unavailable=await f.Shop.GetShopAsync(f.Player,Ct);Assert.Equal("Unavailable",unavailable.Policy!.State);Assert.Empty(unavailable.Products);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Shop.PurchaseAsync(f.Player,"no-fallback",Request(view,"equipment_fragments"),Ct));
        Assert.Equal(5000,(await f.Seasons.GetWalletAsync(f.Player,f.Season.ContextFor(0),Ct))!.Gold);
    }
}
