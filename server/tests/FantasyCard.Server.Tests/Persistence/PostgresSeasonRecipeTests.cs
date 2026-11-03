using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonRecipeTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task LegalUnaffixedPurpleSampleIsLearnedOnceAndItsMarkerSurvivesOwnershipTransfer()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var sample=await CraftingTestInputs.ItemAsync(db,p,effect:null,level:3);
        var request=new LearnSeasonRecipeRequest(p.Season.SeasonId,sample,1);
        var learned=await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn",request,Ct);
        Assert.Null(learned.Recipe.EffectAffix);Assert.Equal(3,learned.Equipment.Level);Assert.True(learned.Equipment.RecipeExtracted);
        Assert.Equal(learned,await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn",request,Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.LearnSeasonRecipeAsync(p.Player,"twice",request with {ExpectedVersion=2},Ct));
        var buyer=await CraftingTestInputs.PlayerAsync(db,p.Clock);Assert.NotEqual(p.Player,buyer);
        await p.Seasons.EnsurePlayerAsync(buyer,p.Season.ContextFor(0),Ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET owner_id=$2,version=version+1 WHERE instance_id=$1",sample,buyer);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.LearnSeasonRecipeAsync(buyer,"buyer",new(p.Season.SeasonId,sample,3),Ct));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM learned_season_recipes"));
        Assert.True(await db.ScalarAsync<bool>("SELECT recipe_extracted FROM equipments WHERE instance_id=$1",sample));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ExistingTemplateDoesNotSpendAnotherSamplesLearningQualification()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var a=await CraftingTestInputs.ItemAsync(db,p);var b=await CraftingTestInputs.ItemAsync(db,p);
        var first=await p.Progression.LearnSeasonRecipeAsync(p.Player,"first",new(p.Season.SeasonId,a,1),Ct);
        var second=await p.Progression.LearnSeasonRecipeAsync(p.Player,"second",new(p.Season.SeasonId,b,1),Ct);
        Assert.True(second.AlreadyLearned);Assert.Equal(first.Recipe.RecipeId,second.Recipe.RecipeId);
        Assert.False(second.Equipment.RecipeExtracted);Assert.Equal(1,second.Equipment.Version);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task RebuildKeepsOneBodyAndBindingButResetsItsLevelAndCannotTeachAnotherRecipe()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var sample=await CraftingTestInputs.ItemAsync(db,p,"Orange","Head","Water","Vitality",3);
        var recipe=(await p.Progression.LearnSeasonRecipeAsync(p.Player,"sample",new(p.Season.SeasonId,sample,1),Ct)).Recipe;
        var body=await CraftingTestInputs.ItemAsync(db,p,"Orange","Feet","Fire","Bulwark",5,true,"MarkCraft","ForcedEscape");
        var quote=await p.Progression.GetReforgeQuoteAsync(p.Player,p.Season.SeasonId,recipe.RecipeId,body,Ct);
        Assert.Equal(2,quote.FragmentCost);Assert.Equal(0,quote.After.Level);Assert.Equal("Head",quote.After.Slot);Assert.True(quote.After.IsBound);
        var request=new ReforgeEquipmentRequest(p.Season.SeasonId,recipe.RecipeId,body,quote.Before.Version,quote.ExpectedWalletVersion);
        var result=await p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"rebuild",request,Ct);
        Assert.Equal(body,result.Equipment.InstanceId);Assert.True(result.Equipment.IsBound);Assert.Equal("TemplateReforge",result.Equipment.SourceKind);
        Assert.Equal("Water",result.Equipment.Element);Assert.Equal("Vitality",result.Equipment.EffectAffix);Assert.Equal(0,result.Equipment.Level);
        Assert.False(result.Equipment.RecipeExtracted);Assert.Equal(p.Season.SeasonId,result.Equipment.OriginSeasonId);
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE season_id=$1",p.Season.SeasonId));
        Assert.Equal(4998,result.Wallet.EquipmentFragments);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.LearnSeasonRecipeAsync(p.Player,"cannot-relearn",new(p.Season.SeasonId,body,result.Equipment.Version),Ct));
        p.Clock.Now=p.Season.EndsAtUtc;
        Assert.Equal(result,await new ProgressionRepository(db.DataSource,p.Clock).ReforgeSeasonEquipmentAsync(p.Player,"rebuild",request,Ct));
        await Assert.ThrowsAsync<IdempotencyConflictException>(()=>p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"rebuild",request with {ExpectedBodyVersion=2},Ct));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM season_equipment_actions WHERE action_kind='equipment.reforge'"));
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData(3,66,0)]
    [InlineData(5,786,10)]
    [Trait("Category","PostgresIntegration")]
    public async Task FiveRealBodiesReforgeForSixThenActuallyEnhanceForTheCombinedRebuildBudget(int targetLevel,int totalCost,int materialCount)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        foreach(var slot in new[]{"Head","Chest","Hands","Legs","Feet"})
        {
            var quality=slot=="Head"?"Orange":"Purple";
            var sample=await CraftingTestInputs.ItemAsync(db,p,quality,slot);
            var recipe=(await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn-"+slot,new(p.Season.SeasonId,sample,1),Ct)).Recipe;
            var body=await CraftingTestInputs.ItemAsync(db,p,quality,"Chest","Water","Bulwark",5);
            var quote=await p.Progression.GetReforgeQuoteAsync(p.Player,p.Season.SeasonId,recipe.RecipeId,body,Ct);
            var current=(await p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"reforge-"+slot,new(p.Season.SeasonId,recipe.RecipeId,body,1,quote.ExpectedWalletVersion),Ct)).Equipment;
            for(var level=0;level<targetLevel;level++)
            {
                Guid? material=level>=3?await CraftingTestInputs.ItemAsync(db,p,quality):null;
                current=(await p.Progression.EnhanceEquipmentAsync(p.Player,body,"enhance-"+slot+level,
                    new(current.Version,material,MaterialExpectedVersion:material is null?null:1),Ct)).Equipment;
            }
            Assert.Equal(targetLevel,current.Level);Assert.Equal(body,current.InstanceId);
        }
        Assert.Equal(5000L-totalCost,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1",p.Player));
        Assert.Equal(materialCount,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE location='EnhanceMaterialConsumed'"));
        Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE source_kind='TemplateReforge' AND location='Inventory'"));
        Assert.Equal(6L,await db.ScalarAsync<long>("SELECT -sum(delta)::bigint FROM economy_ledger WHERE reason='equipment.reforge'"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task WrongQualityMissingOrBorrowedBodyCannotMintFromARecipe()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var sample=await CraftingTestInputs.ItemAsync(db,p);var recipe=(await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn",new(p.Season.SeasonId,sample,1),Ct)).Recipe;
        var wrong=await CraftingTestInputs.ItemAsync(db,p,"Orange");var bot=await CraftingTestInputs.ItemAsync(db,p,source:"BotReward");
        var version=(await p.Progression.GetSeasonCraftingAsync(p.Player,Ct)).Wallet!.Version;
        foreach(var id in new[]{Guid.NewGuid(),wrong,bot})
            await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.ReforgeSeasonEquipmentAsync(p.Player,id.ToString("N"),new(p.Season.SeasonId,recipe.RecipeId,id,1,version),Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM season_equipment_actions WHERE action_kind='equipment.reforge'"));
        Assert.Equal(5000L,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1",p.Player));
    }
}
