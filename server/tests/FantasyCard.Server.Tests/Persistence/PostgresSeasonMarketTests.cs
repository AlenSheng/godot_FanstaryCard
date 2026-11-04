using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonMarketTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("Gold","Orange",99999,9999)] [InlineData("Diamond","Orange",2000,200)] [InlineData("Diamond","Red",8000,800)]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualSameCurrencyTransferBurnsOnlySellerTaxAndKeepsOriginalItemAndReplay(string currency,string quality,long price,long fee)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        var item=await Item(db,f,quality);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        var before=await db.ScalarAsync<string>("SELECT jsonb_build_object('origin',origin_season_id,'mint',mint_id,'week',mint_week,'scope',quota_scope,'stats',stats_version,'source',source_kind,'recipe',recipe_extracted)::text FROM equipments WHERE instance_id=$1",item);
        var listing=await market.ListAsync(f.Owner.Player,"list-source",Request(item,currency,price,f),Ct);
        Assert.Equal(currency,listing.Currency);Assert.Equal(price,listing.Price);Assert.Equal(currency=="Gold"?price:0,listing.PriceGold);
        Assert.Equal(TimeSpan.FromHours(48),listing.ExpiresAt-listing.CreatedAt);
        var expectation=new MarketPurchaseExpectation(currency,price,f.Owner.Season.SeasonId);
        var purchased=await market.PurchaseMarketAsync(f.Buyer,"buy-source",listing.ListingId,listing.Version,Ct,expectation);
        var seller=await market.GetWalletAsync(f.Owner.Player,Ct);var buyer=await market.GetWalletAsync(f.Buyer,Ct);
        Assert.Equal(currency=="Gold"?100000+price-fee:100000,seller.Gold);
        Assert.Equal(currency=="Gold"?150000-price:150000,buyer.Gold);
        Assert.Equal(currency=="Diamond"?100+price-fee:100,seller.Diamond);
        Assert.Equal(currency=="Diamond"?10000-price:10000,buyer.Diamond);
        Assert.Equal(777,await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",f.Owner.Player));
        Assert.Equal(888,await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1",f.Buyer));
        Assert.Equal(f.Buyer,await db.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1",item));
        Assert.Equal(before,await db.ScalarAsync<string>("SELECT jsonb_build_object('origin',origin_season_id,'mint',mint_id,'week',mint_week,'scope',quota_scope,'stats',stats_version,'source',source_kind,'recipe',recipe_extracted)::text FROM equipments WHERE instance_id=$1",item));
        Assert.Equal(fee,await db.ScalarAsync<long>("SELECT fee FROM market_transactions WHERE listing_id=$1",listing.ListingId));
        Assert.Equal(currency,await db.ScalarAsync<string>("SELECT currency FROM market_transactions WHERE listing_id=$1",listing.ListingId));
        var ledger=await db.ScalarAsync<long>("SELECT sum(delta)::bigint FROM economy_ledger WHERE reason IN ('market.purchase','market.sale') AND currency=$1",currency);Assert.Equal(-fee,ledger);
        await db.ExecuteAsync("DELETE FROM idempotency_records");
        f.Owner.Clock.Now=f.Owner.Season.EndsAtUtc;
        using var restarted=new EconomyRepository(db.DataSource,f.Owner.Clock);
        Assert.Equal(purchased,await restarted.PurchaseMarketAsync(f.Buyer,"buy-source",listing.ListingId,listing.Version,Ct,expectation));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM market_transactions"));
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>restarted.PurchaseMarketAsync(f.Buyer,"buy-source",listing.ListingId,listing.Version+1,Ct,expectation));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task BothCurrenciesShareEightSlotsAndAtomicRelistNeedsNoSpareInventorySlot()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        var items=new List<Guid>();for(var index=0;index<9;index++)items.Add(await Item(db,f));
        var tasks=items.Take(8).Select((id,index)=>market.ListAsync(f.Owner.Player,"slot-"+index,Request(id,index%2==0?"Gold":"Diamond",100,f),Ct));
        var listings=await Task.WhenAll(tasks);Assert.Equal(8,listings.Length);
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.ListAsync(f.Owner.Player,"ninth",Request(items[8],"Gold",100,f),Ct));
        await FillInventory(db,f,50);
        var original=listings[0];var request=new RelistMarketListingRequest("Diamond",2000,original.Version,f.Owner.Season.SeasonId);
        var changed=await market.RelistMarketAsync(f.Owner.Player,original.ListingId,"switch-currency",request,Ct);
        Assert.NotEqual(original.ListingId,changed.ListingId);Assert.Equal(original.EquipmentId,changed.EquipmentId);Assert.Equal("Diamond",changed.Currency);
        Assert.Equal(8L,await db.ScalarAsync<long>("SELECT count(*) FROM market_listings WHERE status='Active'"));
        Assert.Equal("Cancelled",await db.ScalarAsync<string>("SELECT status FROM market_listings WHERE listing_id=$1",original.ListingId));
        Assert.Equal("MarketListed",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",original.EquipmentId));
        Assert.Equal(changed,await market.RelistMarketAsync(f.Owner.Player,original.ListingId,"switch-currency",request,Ct));
        await market.CancelListingAsync(f.Owner.Player,original.ListingId,"cancel-original-after-switch",Ct);
        Assert.Equal("MarketListed",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",original.EquipmentId));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM market_transactions"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task WrongDiamondConfirmationAndPostPaymentFaultCannotSpendOrTransferAnything()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        var item=await Item(db,f);var listing=await market.ListAsync(f.Owner.Player,"fault-list",Request(item,"Diamond",2000,f),Ct);
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.PurchaseMarketAsync(f.Buyer,"no-currency",listing.ListingId,listing.Version,Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.PurchaseMarketAsync(f.Buyer,"wrong-currency",listing.ListingId,listing.Version,Ct,new("Gold",2000,f.Owner.Season.SeasonId)));
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.PurchaseMarketAsync(f.Buyer,"wrong-price",listing.ListingId,listing.Version,Ct,new("Diamond",1999,f.Owner.Season.SeasonId)));
        await db.ExecuteAsync("""
            CREATE FUNCTION fail_market_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated market commit fault'; END $$;
            CREATE TRIGGER fail_market_commit BEFORE INSERT ON market_transactions FOR EACH ROW EXECUTE FUNCTION fail_market_commit();
            """);
        var error=await Assert.ThrowsAsync<PostgresException>(()=>market.PurchaseMarketAsync(f.Buyer,"fault-purchase",listing.ListingId,listing.Version,Ct,new("Diamond",2000,f.Owner.Season.SeasonId)));
        Assert.Equal(PostgresErrorCodes.RaiseException,error.SqlState);
        Assert.Equal(10000,await db.ScalarAsync<long>("SELECT diamond FROM player_wallets WHERE player_id=$1",f.Buyer));
        Assert.Equal(100,await db.ScalarAsync<long>("SELECT diamond FROM player_wallets WHERE player_id=$1",f.Owner.Player));
        Assert.Equal(f.Owner.Player,await db.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1",item));
        Assert.Equal("Active",await db.ScalarAsync<string>("SELECT status FROM market_listings WHERE listing_id=$1",listing.ListingId));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM market_transactions"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason IN ('market.purchase','market.sale')"));
        await db.ExecuteAsync("DROP TRIGGER fail_market_commit ON market_transactions");
        await market.PurchaseMarketAsync(f.Buyer,"fault-purchase",listing.ListingId,listing.Version,Ct,new("Diamond",2000,f.Owner.Season.SeasonId));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM market_transactions"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task FullInventoryReturnStaysDurableAcrossSeasonClosureAndNeverEntersTheNewSeason()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        f.Owner.Clock.Now=f.Owner.Season.EndsAtUtc.AddHours(-1);var item=await Item(db,f);var listing=await market.ListAsync(f.Owner.Player,"late-list",Request(item,"Gold",100,f),Ct);
        await FillInventory(db,f,50);f.Owner.Clock.Now=f.Owner.Season.EndsAtUtc;
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.PurchaseMarketAsync(f.Buyer,"closed-buy",listing.ListingId,listing.Version,Ct));
        Assert.Contains(listing.ListingId,await market.ExpireListingsAsync(Ct));Assert.Empty(await market.ExpireListingsAsync(Ct));
        Assert.Equal("MarketReturnPending",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",item));
        Assert.Equal("ArchivedSeason",await db.ScalarAsync<string>("SELECT asset_scope FROM equipments WHERE instance_id=$1",item));
        var held=Assert.Single((await market.GetMarketReturnsAsync(f.Owner.Player,Ct)).Items);Assert.False(held.CanClaim);
        Assert.Empty((await market.GetMarketReturnsAsync(f.Buyer,Ct)).Items);
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.ClaimMarketReturnAsync(f.Buyer,held.ReturnId,"foreign-return",new(held.Equipment.Version,f.Owner.Season.SeasonId),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>market.ClaimMarketReturnAsync(f.Owner.Player,held.ReturnId,"full-return",new(held.Equipment.Version,f.Owner.Season.SeasonId),Ct));
        var next=new SeasonDefinition("market-next",f.Owner.Season.RulesetId,f.Owner.Season.ConfigVersion,f.Owner.Season.StatsVersion,
            f.Owner.Season.EndsAtUtc,f.Owner.Season.EndsAtUtc.AddDays(42),5);
        await f.Owner.Seasons.PublishAsync(next,GameConfigCatalog.Current.ContentHash,Ct);await f.Owner.Seasons.EnsurePlayerAsync(f.Owner.Player,next.ContextFor(0),Ct);
        var surplus=await db.ScalarAsync<Guid>("SELECT instance_id FROM equipments WHERE owner_id=$1 AND location='Inventory' AND season_id=$2 LIMIT 1",f.Owner.Player,f.Owner.Season.SeasonId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='Recycled' WHERE instance_id=$1",surplus);
        using var restarted=new EconomyRepository(db.DataSource,f.Owner.Clock);var request=new ClaimMarketReturnRequest(held.Equipment.Version,f.Owner.Season.SeasonId);
        var claimed=await restarted.ClaimMarketReturnAsync(f.Owner.Player,held.ReturnId,"claim-original",request,Ct);
        Assert.Equal("ArchivedSeason",claimed.AssetScope);Assert.Equal(f.Owner.Season.SeasonId,claimed.SeasonId);Assert.Equal(item,claimed.InstanceId);
        Assert.Equal(claimed,await restarted.ClaimMarketReturnAsync(f.Owner.Player,held.ReturnId,"claim-original",request,Ct));
        Assert.Empty((await new ProgressionRepository(db.DataSource,f.Owner.Clock).GetInventoryAsync(f.Owner.Player,Ct)).Equipments);
        Assert.Equal(0,(await restarted.GetWalletAsync(f.Owner.Player,Ct)).Gold);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM market_return_holds WHERE state='Claimed'"));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task CurrentFiltersMaterialOrderAndPaginationKeepCurrenciesAndSourceRestrictionsSeparate()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        foreach(var (level,price) in new[]{(3,10),(0,30),(0,20),(1,5)})
        {
            var item=await Item(db,f,"Purple",level);await market.ListAsync(f.Owner.Player,"filter-"+level+"-"+price,Request(item,"Gold",price,f),Ct);
        }
        var orange=await Item(db,f);await market.ListAsync(f.Owner.Player,"diamond-filter",Request(orange,"Diamond",2000,f),Ct);
        var page1=await market.GetMarketAsync(Ct,2,0,new("Gold","Purple",MaterialsOnly:true));
        var page2=await market.GetMarketAsync(Ct,2,2,new("Gold","Purple",MaterialsOnly:true));
        Assert.Collection(page1,value=>Assert.Equal(20L,value.Price),value=>Assert.Equal(30L,value.Price));
        Assert.Collection(page2,value=>Assert.Equal(1,value.Equipment!.Level),value=>Assert.Equal(3,value.Equipment!.Level));
        Assert.Equal(4,page1.Concat(page2).Select(value=>value.ListingId).Distinct().Count());
        Assert.Single(await market.GetMarketAsync(Ct,200,0,new("Diamond")));
        Assert.Empty(await market.GetMarketAsync(Ct,200,0,new("Gold",Element:"Water")));
        Assert.All(page1.Concat(page2),value=>Assert.Equal("Gold",value.Currency));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task PurchaseAndCancellationRaceHaveOneCustodianAndAtMostOneCurrencyTransfer()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        var item=await Item(db,f);var listing=await market.ListAsync(f.Owner.Player,"race-list",Request(item,"Diamond",2000,f),Ct);
        async Task<bool> Buy()
        {
            try{await market.PurchaseMarketAsync(f.Buyer,"race-buy",listing.ListingId,listing.Version,Ct,new("Diamond",2000,f.Owner.Season.SeasonId));return true;}
            catch(DomainValidationException){return false;}
        }
        async Task<bool> Cancel()
        {
            try{await market.CancelListingAsync(f.Owner.Player,listing.ListingId,"race-cancel",Ct);return true;}
            catch(DomainValidationException){return false;}
        }
        var buyer=Buy();var cancelled=Cancel();await Task.WhenAll(buyer,cancelled);
        Assert.NotEqual(await buyer,await cancelled);
        Assert.Equal(await buyer?f.Buyer:f.Owner.Player,await db.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1",item));
        Assert.Equal("Inventory",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",item));
        Assert.Equal(await buyer?1L:0L,await db.ScalarAsync<long>("SELECT count(*) FROM market_transactions"));
        Assert.Equal(await buyer?8000L:10000L,await db.ScalarAsync<long>("SELECT diamond FROM player_wallets WHERE player_id=$1",f.Buyer));
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task HeldReturnPaginationIsCompleteAndNeverIncludesAnotherPlayersItems()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);using var market=new EconomyRepository(db.DataSource,f.Owner.Clock);
        // Authored, valid held-return history isolates paging/ownership from the
        // separately tested cancellation transaction. There are no active lots.
        for(var index=0;index<33;index++)
        {
            var item=await Item(db,f);var listing=Guid.NewGuid();var held=Guid.NewGuid();
            await CraftingTestInputs.SqlAsync(db,"""
                INSERT INTO market_listings(listing_id,seller_id,equipment_id,price_gold,status,version,created_at,expires_at,
                    currency,price,season_id,config_version,stats_version,season_ends_at,market_rule_version,tax_basis_points,minimum_fee)
                VALUES($1,$2,$3,10,'Cancelled',2,$4,$5,'Gold',10,$6,$7,$8,$9,'season-market-v1',1000,1)
                """,listing,f.Owner.Player,item,f.Owner.Clock.Now,f.Owner.Clock.Now.AddHours(48),f.Owner.Season.SeasonId,
                    f.Owner.Season.ConfigVersion,f.Owner.Season.StatsVersion,f.Owner.Season.EndsAtUtc);
            await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='MarketReturnPending',version=version+1 WHERE instance_id=$1",item);
            await CraftingTestInputs.SqlAsync(db,"""
                INSERT INTO market_return_holds(return_id,listing_id,equipment_id,player_id,season_id,state,created_at)
                VALUES($1,$2,$3,$4,$5,'Pending',$6)
                """,held,listing,item,f.Owner.Player,f.Owner.Season.SeasonId,f.Owner.Clock.Now);
        }
        var first=await market.GetMarketReturnsAsync(f.Owner.Player,Ct,32,0);var second=await market.GetMarketReturnsAsync(f.Owner.Player,Ct,32,32);
        Assert.Equal(32,first.Items.Count);Assert.Equal(32,first.NextOffset);Assert.Single(second.Items);Assert.Null(second.NextOffset);
        Assert.Equal(33,first.Items.Concat(second.Items).Select(row=>row.ReturnId).Distinct().Count());
        Assert.Empty((await market.GetMarketReturnsAsync(f.Buyer,Ct)).Items);
        Assert.True((await new EconomyReconciliationRepository(db.DataSource).InspectAsync(Ct)).IsHealthy);
    }

    private static CreateMarketListingRequest Request(Guid item,string currency,long price,Fixture f)=>
        new(item,currency=="Gold"?price:0,currency,price,f.Owner.Season.SeasonId,1);
    private sealed record Fixture(CraftingPlayer Owner,Guid Buyer);
    private static async Task<Fixture> Create(PostgresTestSchema db)
    {
        var owner=await CraftingTestInputs.CreateAsync(db);var buyer=await CraftingTestInputs.PlayerAsync(db,owner.Clock);
        await owner.Seasons.EnsurePlayerAsync(buyer,owner.Season.ContextFor(0),Ct);
        await owner.Seasons.ApplyAsync(owner.Player,owner.Season.ContextFor(0),100000,0,0,"test.gold","seller-fund",SeasonWalletPurpose.General,Ct);
        await owner.Seasons.ApplyAsync(buyer,owner.Season.ContextFor(0),150000,0,0,"test.gold","buyer-fund",SeasonWalletPurpose.General,Ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_wallets SET gold=777,diamond=100 WHERE player_id=$1",owner.Player);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_wallets SET gold=888,diamond=10000 WHERE player_id=$1",buyer);
        return new(owner,buyer);
    }
    private static async Task<Guid> Item(PostgresTestSchema db,Fixture f,string quality="Orange",int level=0)
    {
        var item=await CraftingTestInputs.ItemAsync(db,f.Owner,quality,effect:quality is "Purple" or "Orange" or "Red"?"Piercing":null,level:level);
        if(quality=="Red")await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET source_kind='RedBoss',unique_affix='Inferno',unique_element='Fire',mint_id=$2,quota_scope='primary',mint_week='2026-10-26' WHERE instance_id=$1",item,Guid.NewGuid());
        return item;
    }
    private static async Task FillInventory(PostgresTestSchema db,Fixture f,int target)
    {
        while(await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location='Inventory'",f.Owner.Player)<target)
            await Item(db,f,"Blue");
    }
}
