using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    private static SeasonRecipeResponse RecipeRow(NpgsqlDataReader reader) => new(reader.GetGuid(0),reader.GetString(1),
        reader.GetString(2),reader.GetString(3),reader.GetString(4),reader.IsDBNull(5)?null:reader.GetString(5),
        reader.GetString(6),reader.GetString(7),reader.GetGuid(8));

    private static async Task<IReadOnlyList<SeasonRecipeResponse>> ReadSeasonRecipesAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,
        Guid playerId,string seasonId,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand("SELECT recipe_id,season_id,quality,slot,element,effect_affix,secondary_trait,stats_version,source_item_id FROM learned_season_recipes WHERE player_id=$1 AND season_id=$2 ORDER BY learned_at,recipe_id",connection,transaction);
        query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(seasonId);
        var rows=new List<SeasonRecipeResponse>();await using var reader=await query.ExecuteReaderAsync(ct);
        while(await reader.ReadAsync(ct))rows.Add(RecipeRow(reader));return rows;
    }

    private static void RequireRecipeBody(EquipmentResponse body,bool learning)
    {
        if(body.Quality is not ("Purple" or "Orange") || body.Location is not ("Inventory" or "Equipped") ||
            body.SourceKind is not ("NaturalDrop" or "MarkCraft" or "TemplateReforge") ||
            learning && (body.SourceKind=="TemplateReforge" || body.RecipeExtracted==true))
            throw new DomainValidationException("This equipment is not an eligible recipe sample or rebuild body.");
        RequireCraftingShape(body.Slot,body.Element??"",body.EffectAffix);
        if(body.Quality=="Orange" && body.EffectAffix is null || body.SecondaryTrait is not ("DrawInterval" or "ForcedEscape") ||
            body.SecondaryTrait=="ForcedEscape" && body.Slot!="Feet")
            throw new DomainValidationException("The equipment template has incomplete attributes.");
        // A legitimate Purple sample may have no effect. No new affix is invented while learning.
    }

    private void RequireCraftingTime(CraftingRealm realm)
    {
        if(!realm.Season.Contains((timeProvider??TimeProvider.System).GetUtcNow()))
            throw new DomainValidationException("The crafting season closed. Reload and retry.");
    }

    private static void RequireCraftingEquipmentRealm(EquipmentResponse item,CraftingRealm realm)
    {
        if(item.SeasonId!=realm.Season.SeasonId || item.AssetScope!="ActiveSeason" || item.StatsVersion!=realm.Season.StatsVersion)
            throw new DomainValidationException("The equipment belongs to another season or archive.");
    }

    public async Task<LearnSeasonRecipeResponse> LearnSeasonRecipeAsync(Guid playerId,string requestId,LearnSeasonRecipeRequest request,CancellationToken ct)
    {
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,playerId,ct);
        var hash=HashIdempotentRequest("recipe.learn",request);
        var replay=await ReadSeasonEquipmentActionAsync<LearnSeasonRecipeResponse>(connection,transaction,playerId,"recipe.learn",requestId,hash,ct);
        if(replay is not null){await transaction.CommitAsync(ct);return replay;}
        var realm=await ReadCraftingRealmAsync(connection,transaction,playerId,request.SeasonId,ct);
        var item=await ReadEnhancementEquipmentAsync(connection,transaction,playerId,request.EquipmentId,true,ct)
            ??throw new DomainValidationException("Equipment was not found.");
        if(item.Version!=request.ExpectedVersion)throw new DomainValidationException("Equipment changed. Reload and retry.");
        RequireCraftingEquipmentRealm(item,realm);RequireRecipeBody(item,true);
        var known=(await ReadSeasonRecipesAsync(connection,transaction,playerId,realm.Season.SeasonId,ct)).SingleOrDefault(row=>
            row.Quality==item.Quality && row.Slot==item.Slot && row.Element==item.Element && row.EffectAffix==item.EffectAffix && row.SecondaryTrait==item.SecondaryTrait);
        var recipe=known??new SeasonRecipeResponse(Guid.NewGuid(),realm.Season.SeasonId,item.Quality,item.Slot,item.Element!,item.EffectAffix,item.SecondaryTrait!,realm.Season.StatsVersion,item.InstanceId);
        var after=item;
        var now=(timeProvider??TimeProvider.System).GetUtcNow();RequireCraftingTime(realm);
        if(known is null)
        {
            await using(var insert=new NpgsqlCommand("""
                INSERT INTO learned_season_recipes(recipe_id,player_id,season_id,quality,slot,element,effect_affix,secondary_trait,stats_version,source_item_id,learned_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,connection,transaction))
            {
                insert.Parameters.AddWithValue(recipe.RecipeId);insert.Parameters.AddWithValue(playerId);insert.Parameters.AddWithValue(recipe.SeasonId);
                insert.Parameters.AddWithValue(recipe.Quality);insert.Parameters.AddWithValue(recipe.Slot);insert.Parameters.AddWithValue(recipe.Element);
                insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)recipe.EffectAffix??DBNull.Value);insert.Parameters.AddWithValue(recipe.SecondaryTrait);
                insert.Parameters.AddWithValue(recipe.StatsVersion);insert.Parameters.AddWithValue(recipe.SourceItemId);insert.Parameters.AddWithValue(now);
                await insert.ExecuteNonQueryAsync(ct);
            }
            await using(var mark=new NpgsqlCommand("UPDATE equipments SET recipe_extracted=true,version=version+1 WHERE instance_id=$1",connection,transaction))
            {mark.Parameters.AddWithValue(item.InstanceId);await mark.ExecuteNonQueryAsync(ct);}
            after=item with {RecipeExtracted=true,Version=item.Version+1};
        }
        var response=new LearnSeasonRecipeResponse(recipe,after,known is not null);
        await WriteSeasonEquipmentActionAsync(connection,transaction,playerId,realm.Season.SeasonId,"recipe.learn",requestId,hash,item,after,response,now,ct);
        await transaction.CommitAsync(ct);return response;
    }

    private static EquipmentResponse ReforgedItem(EquipmentResponse body,SeasonRecipeResponse recipe) => body with
    {
        Slot=recipe.Slot,Element=recipe.Element,EffectAffix=recipe.EffectAffix,SecondaryTrait=recipe.SecondaryTrait,
        Level=0,Location="Inventory",Version=body.Version+1,SourceKind="TemplateReforge"
    };

    public async Task<ReforgeQuoteResponse> GetReforgeQuoteAsync(Guid playerId,string seasonId,Guid recipeId,Guid bodyId,CancellationToken ct)
    {
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        var realm=await ReadCraftingRealmAsync(connection,null,playerId,seasonId,ct);
        var recipe=(await ReadSeasonRecipesAsync(connection,null,playerId,seasonId,ct)).SingleOrDefault(row=>row.RecipeId==recipeId)
            ??throw new DomainValidationException("The selected recipe is not known in this season.");
        var body=await ReadEnhancementEquipmentAsync(connection,null,playerId,bodyId,false,ct)
            ??throw new DomainValidationException("Equipment was not found.");
        RequireCraftingEquipmentRealm(body,realm);RequireRecipeBody(body,false);RequireCraftingTier(realm,recipe.Quality);
        if(recipe.Quality!=body.Quality || recipe.StatsVersion!=realm.Season.StatsVersion)
            throw new DomainValidationException("The rebuild body must match the recipe quality and original stats version.");
        var wallet=await ReadCraftingWalletAsync(connection,null,playerId,realm,ct);
        var cost=realm.Policy.Offer(recipe.Quality).ReforgeFragmentCost;
        var full=body.Location!="Inventory" && await InventoryArmorCountAsync(connection,null,playerId,seasonId,ct)>=50;
        var blocked=wallet.EquipmentFragments<cost?"Not enough equipment fragments.":full?"The equipment inventory is full.":null;
        RequireCraftingTime(realm);
        return new(recipe,body,ReforgedItem(body,recipe),cost,wallet.EquipmentFragments,wallet.Version,blocked is null,blocked);
    }

    public async Task<ReforgeEquipmentResponse> ReforgeSeasonEquipmentAsync(Guid playerId,string requestId,ReforgeEquipmentRequest request,CancellationToken ct)
    {
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,playerId,ct);var hash=HashIdempotentRequest("equipment.reforge",request);
        var replay=await ReadSeasonEquipmentActionAsync<ReforgeEquipmentResponse>(connection,transaction,playerId,"equipment.reforge",requestId,hash,ct);
        if(replay is not null){await transaction.CommitAsync(ct);return replay;}
        var realm=await ReadCraftingRealmAsync(connection,transaction,playerId,request.SeasonId,ct);
        var recipe=(await ReadSeasonRecipesAsync(connection,transaction,playerId,request.SeasonId,ct)).SingleOrDefault(row=>row.RecipeId==request.RecipeId)
            ??throw new DomainValidationException("The selected recipe is not known in this season.");
        var body=await ReadEnhancementEquipmentAsync(connection,transaction,playerId,request.BodyEquipmentId,true,ct)
            ??throw new DomainValidationException("Equipment was not found.");
        if(body.Version!=request.ExpectedBodyVersion)throw new DomainValidationException("The rebuild body changed. Reload and retry.");
        RequireCraftingEquipmentRealm(body,realm);RequireRecipeBody(body,false);RequireCraftingTier(realm,recipe.Quality);
        if(recipe.Quality!=body.Quality || recipe.StatsVersion!=realm.Season.StatsVersion)
            throw new DomainValidationException("The rebuild body must match the recipe quality and original stats version.");
        if(body.Location!="Inventory" && await InventoryArmorCountAsync(connection,transaction,playerId,realm.Season.SeasonId,ct)>=50)
            throw new DomainValidationException("The equipment inventory is full.");
        var wallet=await ReadCraftingWalletAsync(connection,transaction,playerId,realm,ct);
        if(wallet.Version!=request.ExpectedWalletVersion)throw new DomainValidationException("The crafting wallet changed. Reload and retry.");
        RequireCraftingTime(realm);var now=(timeProvider??TimeProvider.System).GetUtcNow();
        var paid=await SeasonRepository.ApplyWithinTransactionAsync(connection,transaction,playerId,realm.Context,0,-realm.Policy.Offer(recipe.Quality).ReforgeFragmentCost,0,
            "equipment.reforge",requestId,SeasonWalletPurpose.General,now,hash,ct);
        var after=ReforgedItem(body,recipe);
        await using(var update=new NpgsqlCommand("UPDATE equipments SET slot=$2,element=$3,effect_affix=$4,secondary_trait=$5,level=0,location='Inventory',version=version+1,source_kind='TemplateReforge' WHERE instance_id=$1",connection,transaction))
        {
            update.Parameters.AddWithValue(body.InstanceId);update.Parameters.AddWithValue(after.Slot);update.Parameters.AddWithValue(after.Element!);
            update.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)after.EffectAffix??DBNull.Value);update.Parameters.AddWithValue(after.SecondaryTrait!);
            await update.ExecuteNonQueryAsync(ct);
        }
        await using(var loadouts=new NpgsqlCommand("""
            UPDATE player_loadouts SET head_id=CASE WHEN head_id=$2 THEN NULL ELSE head_id END,
                chest_id=CASE WHEN chest_id=$2 THEN NULL ELSE chest_id END,hands_id=CASE WHEN hands_id=$2 THEN NULL ELSE hands_id END,
                legs_id=CASE WHEN legs_id=$2 THEN NULL ELSE legs_id END,feet_id=CASE WHEN feet_id=$2 THEN NULL ELSE feet_id END,version=version+1
            WHERE player_id=$1 AND $2=ANY(ARRAY[head_id,chest_id,hands_id,legs_id,feet_id])
            """,connection,transaction))
        {loadouts.Parameters.AddWithValue(playerId);loadouts.Parameters.AddWithValue(body.InstanceId);await loadouts.ExecuteNonQueryAsync(ct);}
        await WriteInventoryMovementAsync(connection,transaction,playerId,body.InstanceId,body.Location,"Inventory","equipment.reforge",ct,requestId,realm.Season.SeasonId);
        var response=new ReforgeEquipmentResponse(after,BlueprintWalletResponse(paid));
        await WriteSeasonEquipmentActionAsync(connection,transaction,playerId,realm.Season.SeasonId,"equipment.reforge",requestId,hash,body,after,response,now,ct);
        await transaction.CommitAsync(ct);return response;
    }
}
