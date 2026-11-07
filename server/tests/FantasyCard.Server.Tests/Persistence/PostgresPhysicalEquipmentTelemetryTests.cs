using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresPhysicalEquipmentTelemetryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web);

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task RealCraftReforgeMarketAndDiscardCountOneMintAndDestroyWhileOriginalCreatorSurvivesOwnerAndSourceChanges()
    {
        await using var db=await Open("physical-chain");var p=await CraftingTestInputs.CreateAsync(db,_=>0);await CraftingTestInputs.FundAsync(db,p,4,0);
        var start=DateTimeOffset.UtcNow;p.Clock.Now=start;var wallet=(await p.Progression.GetSeasonCraftingAsync(p.Player,Ct)).Wallet!;
        var crafted=await p.Progression.CraftSeasonEquipmentAsync(p.Player,"physical-craft",new(p.Season.SeasonId,"Purple","Hands","Fire","Piercing",wallet.Version),Ct);var id=crafted.Equipment.InstanceId;
        var learned=await p.Progression.LearnSeasonRecipeAsync(p.Player,"physical-learn",new(p.Season.SeasonId,id,crafted.Equipment.Version),Ct);
        var quote=await p.Progression.GetReforgeQuoteAsync(p.Player,p.Season.SeasonId,learned.Recipe.RecipeId,id,Ct);
        var reforged=await p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"physical-reforge",new(p.Season.SeasonId,learned.Recipe.RecipeId,id,learned.Equipment.Version,quote.ExpectedWalletVersion),Ct);
        Assert.Equal("TemplateReforge",reforged.Equipment.SourceKind);
        var buyer=await CraftingTestInputs.PlayerAsync(db,p.Clock);await p.Seasons.EnsurePlayerAsync(buyer,p.Season.ContextFor(0),Ct);
        await p.Seasons.ApplyAsync(buyer,p.Season.ContextFor(0),200,0,0,"test.physical.capital","physical-fund",SeasonWalletPurpose.General,Ct);
        using var market=new EconomyRepository(db.DataSource,p.Clock);
        var listed=await market.ListAsync(p.Player,"physical-list1",new(id,100,"Gold",100,p.Season.SeasonId,reforged.Equipment.Version),Ct);
        await market.CancelListingAsync(p.Player,listed.ListingId,"physical-cancel",Ct);
        var version=await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1",id);
        listed=await market.ListAsync(p.Player,"physical-list2",new(id,100,"Gold",100,p.Season.SeasonId,version),Ct);
        await market.PurchaseMarketAsync(buyer,"physical-buy",listed.ListingId,listed.Version,Ct,new("Gold",100,p.Season.SeasonId));
        version=await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1",id);
        var discard=new DiscardEquipmentRequest([new(id,version)],p.Season.SeasonId);var progression=new ProgressionRepository(db.DataSource,p.Clock);
        await progression.DiscardEquipmentAsync(buyer,"physical-discard",discard,Ct);await progression.DiscardEquipmentAsync(buyer,"physical-discard",discard,Ct);
        var fingerprint=await Fingerprint(db);var report=await new PhysicalEquipmentTelemetryRepository(db.DataSource,p.Clock).ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        var mint=Assert.Single(report.Events,e=>e.Kind=="Mint");Assert.Equal(p.Player,mint.ToOwnerId);Assert.Equal("equipment.craft",mint.Source);Assert.Equal(id,mint.ItemId);
        Assert.Equal(1,report.Events.Sum(e=>e.DestroyedUnits));Assert.Equal(1,report.Events.Sum(e=>e.TransferredUnits));Assert.Equal(2,report.Events.Sum(e=>e.EscrowEntries));Assert.Equal(2,report.Events.Sum(e=>e.EscrowReleases));
        var transfer=Assert.Single(report.Events,e=>e.TransferredUnits==1);Assert.Equal(p.Player,transfer.FromOwnerId);Assert.Equal(buyer,transfer.ToOwnerId);
        var balance=Assert.Single(report.Supply);Assert.Equal("1",balance.Created);Assert.Equal("1",balance.Destroyed);Assert.Equal("0",balance.Closing);Assert.Equal("0",balance.Difference);Assert.True(report.KnownSubsetBalanced);
        Assert.Equal(0,report.MissingCreationSources);Assert.Equal(0,report.UnclassifiedMovements);Assert.Equal(fingerprint,await Fingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-physical-equipment-chain",report,originalCreator=p.Player,currentOwner=buyer,originalItem=id,readOnlyFingerprintUnchanged=true,replayNoNewUnits=true,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task CommittedRecyclingUsesItsExactOriginalHoldAndReceiptWhileOtherItemCannotBorrowItsBuild()
    {
        await using var db=await Open("physical-hold-profile");var p=await CraftingTestInputs.CreateAsync(db);p.Clock.Now=DateTimeOffset.UtcNow;var start=p.Clock.Now;
        var item=await CraftingTestInputs.ItemAsync(db,p);await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='InMatchBackpack' WHERE instance_id=$1",item);
        var room=Guid.NewGuid();var match=Guid.NewGuid();await Match(db,p,match,room,2);
        var domain=new BattleRoom(Guid.NewGuid(),"profile-only",CombatCardCatalog.CreatePrototype(),73);var player=domain.AddPlayer(new(p.Player,HeroClass.Mage,Enumerable.Repeat("C01",20).ToArray(),null));
        var profile=RoomBuildProfiles.Capture(player,CombatCardCatalog.CreatePrototype())!;
        using var details=JsonDocument.Parse(JsonSerializer.Serialize(new{roomId=room,heroClass="Mage",telemetryProfile=profile,telemetryProfileBasis="TerminalEvent",difficultyProgress=new{eliteCleared=false,bossCleared=false}},Json));
        using var metrics=new ServerMetrics();var settlements=new SettlementRepository(db.DataSource,p.Clock,metrics);var asset=new SettlementAsset("Equipment",item.ToString("D"),false,Destination:"Recycled");
        var receipt=await settlements.SettleAsync(match,p.Player,"Extracted",details.RootElement,[asset],Ct,p.Season.ContextFor(2),p.Season.ConfigVersion);
        Assert.Equal(1,await settlements.CommitHoldsAsync(receipt.SettlementId,Ct));Assert.Equal(0,await settlements.CommitHoldsAsync(receipt.SettlementId,Ct));
        var hold=await db.ScalarAsync<Guid>("SELECT hold_id FROM settlement_asset_holds WHERE settlement_id=$1",receipt.SettlementId);
        var fingerprint=await Fingerprint(db);var repository=new LifecycleEventTelemetryRepository(db.DataSource);var report=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        var destroyed=Assert.Single(report.Events,e=>e.EventName=="item_destroyed");Assert.Equal(hold,destroyed.SourceHoldId);Assert.Equal(match,destroyed.MatchId);Assert.Equal("Mage",destroyed.Dimensions.HeroClass);Assert.Equal(profile.BuildType,destroyed.Dimensions.BuildType);Assert.Equal(profile.GrowthStage,destroyed.Dimensions.GrowthStage);Assert.Equal(fingerprint,await Fingerprint(db));
        var other=await CraftingTestInputs.ItemAsync(db,p);await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at,season_id,difficulty_id,ruleset_id,config_version,stats_version)
            VALUES(gen_random_uuid(),$1,$2,'InMatchBackpack','Recycled','reward.recycle',$3,$4,$5,'D2','season-v1',$6,$7)
            """,p.Player,other,hold.ToString("D"),start,p.Season.SeasonId,p.Season.ConfigVersion,p.Season.StatsVersion);
        var mixed=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);var unrelated=Assert.Single(mixed.Events,e=>e.ItemId==other);Assert.Null(unrelated.SourceHoldId);Assert.Null(unrelated.Dimensions.BuildType);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-committed-destruction-profile",report,mixed,readOnlyFingerprintUnchanged=true,originalHold=hold,unrelatedItemRejected=true,declaredAssetBoundaryFixture=true,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task UnknownTerminalTimeAndDuplicateDestructionClaimsRemainCoverageGapsRatherThanNewSupply()
    {
        await using var db=await Open("physical-lifetime-history");var p=await CraftingTestInputs.CreateAsync(db);p.Clock.Now=DateTimeOffset.UtcNow;var start=p.Clock.Now;
        var missing=await CraftingTestInputs.ItemAsync(db,p);var duplicate=await CraftingTestInputs.ItemAsync(db,p);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='Recycled' WHERE owner_id=$1",p.Player);
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,created_at)
            VALUES(gen_random_uuid(),$1,$2,'Inventory','Recycled','equipment.discard',$3),(gen_random_uuid(),$1,$2,'Inventory','Recycled','equipment.discard',$3)
            """,p.Player,duplicate,start);
        var fingerprint=await Fingerprint(db);var report=await new PhysicalEquipmentTelemetryRepository(db.DataSource,p.Clock).ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        var balance=Assert.Single(report.Supply);Assert.Equal("1",balance.UnknownTerminalTimes);Assert.Equal("1",balance.DuplicateDestructionClaims);Assert.Equal("1",balance.Destroyed);Assert.False(report.KnownSubsetBalanced);
        Assert.Equal(2,report.MissingCreationSources);Assert.All(report.Events.Where(e=>e.Kind=="Mint"),e=>Assert.Null(e.ToOwnerId));Assert.Equal(fingerprint,await Fingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-physical-history-gaps",report,unknownItem=missing,readOnlyFingerprintUnchanged=true,noCreationOwnerInference=true,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task ArchiveMarkersCoverWalletRecipeWishAndLoadoutsWithoutBackdatingLateCreditAmounts()
    {
        await using var db=await Open("physical-domain-archive");var p=await CraftingTestInputs.CreateAsync(db,_=>0);var funded=await CraftingTestInputs.FundAsync(db,p,4,0);
        var crafted=await p.Progression.CraftSeasonEquipmentAsync(p.Player,"archive-craft",new(p.Season.SeasonId,"Purple","Head","Fire","Vitality",funded.Version),Ct);
        await p.Progression.LearnSeasonRecipeAsync(p.Player,"archive-learn",new(p.Season.SeasonId,crafted.Equipment.InstanceId,crafted.Equipment.Version),Ct);
        var loadout=await db.ScalarAsync<long>("SELECT version FROM player_loadouts WHERE player_id=$1 AND hero_class=2",p.Player);
        await p.Progression.SaveLoadoutAsync(p.Player,HeroClass.Mage,[crafted.Equipment.InstanceId,null,null,null,null],"archive-loadout",loadout,p.Clock.Now,Ct);
        p.Clock.Now=p.Season.EndsAtUtc;await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,10,Ct);
        var repository=new LifecycleEventTelemetryRepository(db.DataSource);var before=await repository.ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct);
        Assert.Single(before.Events,e=>e.AssetKind=="SeasonWallet");Assert.Single(before.Events,e=>e.AssetKind=="Recipe");Assert.Single(before.Events,e=>e.AssetKind=="CraftingWish");Assert.Single(before.Events,e=>e.AssetKind=="SavedLoadout");
        Assert.All(before.Events,e=>Assert.Equal("season_asset_archived",e.EventName));
        await p.Seasons.ApplyAsync(p.Player,p.Season.ContextFor(0),7,0,0,"test.late","archive-late",SeasonWalletPurpose.LateSettlement,Ct);
        var fingerprint=await Fingerprint(db);var after=await repository.ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct);
        Assert.Equal(JsonSerializer.Serialize(before),JsonSerializer.Serialize(after));Assert.Equal(fingerprint,await Fingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-wallet-recipe-archive-markers",before,after,readOnlyFingerprintUnchanged=true,lateCreditDoesNotRewriteMarkers=true,noArchiveAmountSnapshotClaimed=true,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task RealPreparationCancelAndMatchAdmissionRetainSelfOwnershipLegsWithoutChangingGameRules()
    {
        await using var db=await Open("physical-admission-ownership");var p=await CraftingTestInputs.CreateAsync(db);p.Clock.Now=DateTimeOffset.UtcNow;
        var item=await CraftingTestInputs.ItemAsync(db,p,"Green","Head",effect:null);var loadout=await db.ScalarAsync<long>("SELECT version FROM player_loadouts WHERE player_id=$1 AND hero_class=2",p.Player);
        await p.Progression.SaveLoadoutAsync(p.Player,HeroClass.Mage,[item,null,null,null,null],"owner-equip",loadout,p.Clock.Now,Ct);
        var deck=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",p.Player);var preparations=new PreparationRepository(db.DataSource,p.Clock);
        var request=new CreatePreparationRequest(HeroClassDto.Mage,deck,[item,null,null,null,null],BackpackTierDto.Free,[],0,"D0",p.Season.SeasonId);
        var first=await preparations.CreateAsync(p.Player,"owner-prep1",request,Ct);Assert.Equal(CreatePreparationStatus.Created,first.Status);
        await preparations.CancelAsync(p.Player,first.Preparation!.PreparationId,"owner-cancel",Ct);
        var second=await preparations.CreateAsync(p.Player,"owner-prep2",request,Ct);Assert.Equal(CreatePreparationStatus.Created,second.Status);
        using var metrics=new ServerMetrics();var matches=new MatchmakingRepository(db.DataSource,p.Clock,metrics);await matches.EnqueueAsync(p.Player,"owner-queue",new(second.Preparation!.PreparationId),Ct);
        p.Clock.Now=p.Clock.Now.AddSeconds(31);Assert.NotNull(await matches.TryCreateMatchAsync(Ct));await matches.MarkReadyAsync(p.Player,p.Clock.Now,Ct);Assert.NotNull(await matches.ClaimReadyMatchAsync(p.Clock.Now,Ct));
        Assert.Equal("InMatchEquipped",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",item));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND (from_owner_id IS DISTINCT FROM player_id OR to_owner_id IS DISTINCT FROM player_id)",item));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason='match.start'",item));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-preparation-owner-observations",item,selfOwnershipStable=true,cancelReleaseAndMatchStartExecuted=true,nativeCapacityClaimed=false,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    private static async Task Match(PostgresTestSchema db,CraftingPlayer p,Guid match,Guid room,int difficulty)
    {
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version) VALUES($1,$2,'ChaosRealm',$3,73,$4,'Running',$5,$6,'season-v1',$7)",match,room,"D"+difficulty,p.Season.ConfigVersion,p.Clock.Now,p.Season.SeasonId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,p.Player);
    }
    private static async Task<PostgresTestSchema> Open(string label)
    {
        var db=await PostgresTestSchema.CreateAsync(false);try{PostgresSeasonMarketTests.RecordTelemetrySchema(db,label);await db.MigrateAsync();return db;}catch{await db.DisposeAsync();throw;}
    }
    private static async Task<string> Fingerprint(PostgresTestSchema db)=>await db.ScalarAsync<string>("""
        SELECT md5(concat_ws('|',$1,
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY instance_id)::text,'[]') FROM equipments x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY movement_id)::text,'[]') FROM inventory_movements x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY hold_id)::text,'[]') FROM settlement_asset_holds x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY settlement_id)::text,'[]') FROM match_settlements x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY recipe_id)::text,'[]') FROM learned_season_recipes x)))
        """,await PostgresSeasonMarketTests.TelemetryFinancialFingerprint(db));
}
