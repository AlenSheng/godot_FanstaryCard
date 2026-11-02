using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Settlement;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed partial class PostgresSeasonSettlementTests
{
    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task OriginalCellAndPromotionProofPersistOnceWithTheFrozenSeason()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var definition=Define();var clock=new Clock(definition.StartsAtUtc);
        var fixture=await SetupAsync(db,clock,definition);using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,clock,metrics);
        var rule=GameConfigCatalog.Current.SeasonLoot(0,"outer");
        var origin=new SeasonEquipmentOrigin(fixture.Context,"NaturalChoice",rule.RuleId,"outer","White",true);
        var item=new EquipmentRewardData("Head","Green","Fire",null,"DrawInterval",SeasonOrigin:origin);var id=Guid.NewGuid();
        var receipt=await SettleAsync(repository,fixture,[new("Equipment",id.ToString("D"),false,Equipment:item),new("Gold","gold",false,17)]);
        Assert.Equal(2,await repository.CommitHoldsAsync(receipt.SettlementId,Ct));Assert.Equal(0,await repository.CommitHoldsAsync(receipt.SettlementId,Ct));
        Assert.Equal(rule.RuleId,await db.ScalarAsync<string>("SELECT loot_rule_id FROM equipments WHERE instance_id=$1",id));
        Assert.Equal("NaturalDrop",await db.ScalarAsync<string>("SELECT source_kind FROM equipments WHERE instance_id=$1",id));
        var original=await db.ScalarAsync<string>("SELECT source_loot_json::text FROM equipments WHERE instance_id=$1",id);
        Assert.Equal(origin,JsonSerializer.Deserialize<SeasonEquipmentOrigin>(original));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1",id));
        Assert.Equal(17L,await Balance(db,fixture.Player,definition.SeasonId,"gold"));
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("quality")] [InlineData("season")] [InlineData("rule")] [InlineData("layer")] [InlineData("missing")]
    [Trait("Category","PostgresIntegration")]
    public async Task InvalidMintQualityOrOriginLeavesEveryHoldAndWalletUncommitted(string mutation)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var definition=Define();var clock=new Clock(definition.StartsAtUtc);
        var fixture=await SetupAsync(db,clock,definition);using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,clock,metrics);
        var origin=new SeasonEquipmentOrigin(fixture.Context,"NaturalChoice",GameConfigCatalog.Current.SeasonLoot(0,"outer").RuleId,"outer","White",true);
        origin=mutation switch
        {
            "season"=>origin with {Season=new("wrong",0,"season-v1",fixture.Context.ConfigVersion,fixture.Context.StatsVersion)},
            "rule"=>origin with {LootRuleId="unpublished"},"layer"=>origin with {LayerId="boss"},_=>origin
        };
        var id=Guid.NewGuid();var item=new EquipmentRewardData("Head",mutation=="quality"?"Purple":"Green","Fire",null,"DrawInterval",SeasonOrigin:origin);
        if(mutation=="missing")item=item with {SeasonOrigin=null};
        // Submit the raw invalid hold; the normal fixture helper attaches a valid origin to its older controls.
        var receipt=await repository.SettleAsync(fixture.Match,fixture.Player,"Extracted",JsonSerializer.SerializeToElement(new {roomId=fixture.Room}),
            [new("Gold","gold",false,37),new("Equipment",id.ToString("D"),false,Equipment:item)],Ct,fixture.Context);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CommitHoldsAsync(receipt.SettlementId,Ct));
        Assert.Equal(0L,await Balance(db,fixture.Player,definition.SeasonId,"gold"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending'",receipt.SettlementId));
        Assert.Empty(await repository.GetReadyNotificationsAsync(fixture.Player,Ct));
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData(0)] [InlineData(1)] [InlineData(2)] [InlineData(3)] [InlineData(4)] [InlineData(5)]
    [Trait("Category","PostgresIntegration")]
    public async Task DatabaseMintCapCoversEverySourceWithoutRestrictingLaterInventoryOwnership(int difficulty)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var definition=Define();var clock=new Clock(definition.StartsAtUtc);
        var fixture=await SetupAsync(db,clock,definition);
        foreach(var source in SourceKinds)
        for(var rank=0;rank<6;rank++)
        {
            var id=Guid.NewGuid();var accepted=difficulty>=2 || rank<=(difficulty==0?2:3);
            async Task Insert()=>await Sql(db,"""
                INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
                VALUES($1,$2,'Head',$3,0,'Inventory',now(),'Fire',$4,$4,'ActiveSeason',$5,$6,$7)
                """,id,fixture.Player,SeasonLootConfig.Quality(rank),definition.SeasonId,definition.StatsVersion,source,(short)difficulty);
            if(accepted)await Insert();
            else
            {
                var error=await Assert.ThrowsAsync<PostgresException>(Insert);
                Assert.Equal(PostgresErrorCodes.CheckViolation,error.SqlState);Assert.Equal("ck_equipment_generated_difficulty_quality",error.ConstraintName);
            }
            Assert.Equal(accepted?1L:0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",id));
        }
    }

    private static readonly string[] SourceKinds=["NaturalDrop","MarkCrafted","Shop","Activity","FutureSource"];
}
