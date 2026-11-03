using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Seasons;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    private sealed record CraftingRealm(SeasonDefinition Season, GameConfigCatalog Configuration, SeasonCraftingConfig Policy, int MaximumDifficulty)
    {
        public SeasonContext Context => Season.ContextFor(0);
    }

    private async Task<CraftingRealm> ReadCraftingRealmAsync(NpgsqlConnection connection, NpgsqlTransaction? transaction,
        Guid playerId, string? requestedSeasonId, CancellationToken ct)
    {
        var seasons = new SeasonRepository(dataSource,timeProvider ?? TimeProvider.System);
        var definition = (await seasons.GetScheduleAsync(ct)).Current
            ?? throw new DomainValidationException("No active season is accepting crafting actions.");
        if (requestedSeasonId is not null && requestedSeasonId != definition.SeasonId)
            throw new DomainValidationException("The crafting season changed. Reload and retry.");
        var configuration = await ResolveEquipmentSeasonCatalogAsync(connection,transaction,definition,ct);
        var policy = configuration.SeasonCrafting ?? throw new DomainValidationException("Crafting is unavailable in this original configuration.");
        var unlocked = await seasons.GetUnlockedDifficultyAsync(playerId,definition.SeasonId,ct);
        return new(definition,configuration,policy,Math.Min(unlocked,definition.HighestOpenDifficulty));
    }

    private static SeasonWalletResponse BlueprintWalletResponse(SeasonWalletSnapshot wallet) =>
        new(wallet.SeasonId,wallet.Gold,wallet.EquipmentFragments,wallet.ChallengeMarks,wallet.Version,wallet.ArchivedAt,true,
            wallet.BlueprintMarks,wallet.OrangeBlueprintMarks);

    private static async Task<SeasonWalletSnapshot> ReadCraftingWalletAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,
        Guid playerId,CraftingRealm realm,CancellationToken ct)
    {
        await using var command = new NpgsqlCommand("""
            SELECT gold,equipment_fragments,challenge_marks,version,archived_at,blueprint_marks,orange_blueprint_marks
            FROM player_season_wallets WHERE player_id=$1 AND season_id=$2
            """+(transaction is null?"":" FOR UPDATE"),connection,transaction);
        command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(realm.Season.SeasonId);
        await using var reader=await command.ExecuteReaderAsync(ct);
        if(!await reader.ReadAsync(ct) || !reader.IsDBNull(4))
            throw new DomainValidationException("The player has no active crafting wallet.");
        return new(playerId,realm.Season.SeasonId,reader.GetInt64(0),reader.GetInt64(1),reader.GetInt64(2),reader.GetInt64(3),null,
            reader.GetInt64(5),reader.GetInt64(6));
    }

    private static void RequireCraftingShape(string slot,string element,string? effect)
    {
        if(slot is not ("Head" or "Chest" or "Hands" or "Legs" or "Feet") ||
            element is not ("Fire" or "Wood" or "Earth" or "Metal" or "Water") ||
            effect is not null && !SeasonCraftingConfig.Effects.Contains(effect,StringComparer.Ordinal))
            throw new DomainValidationException("The selected equipment template is invalid.");
    }

    private static void RequireCraftingTier(CraftingRealm realm,string quality)
    {
        var offer=realm.Policy.Offer(quality);
        if(realm.MaximumDifficulty<offer.MinimumDifficulty ||
            SeasonLootConfig.Rank(quality)>realm.Configuration.SeasonDifficulty(realm.MaximumDifficulty).QualityCap)
            throw new DomainValidationException("The selected quality requires a higher open and unlocked difficulty.");
    }

    private static async Task<T?> ReadSeasonEquipmentActionAsync<T>(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,string kind,string requestId,string hash,CancellationToken ct) where T:class
    {
        if(string.IsNullOrWhiteSpace(requestId) || requestId.Length>80 || requestId.Any(char.IsControl))
            throw new DomainValidationException("The crafting request identity is invalid.");
        await using var query=new NpgsqlCommand("SELECT request_hash,response_json::text FROM season_equipment_actions WHERE player_id=$1 AND action_kind=$2 AND request_id=$3",connection,transaction);
        query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(kind);query.Parameters.AddWithValue(requestId);
        await using var reader=await query.ExecuteReaderAsync(ct);
        if(!await reader.ReadAsync(ct))return null;
        if(reader.GetString(0)!=hash)throw new IdempotencyConflictException();
        return JsonSerializer.Deserialize<T>(reader.GetString(1))??throw new InvalidOperationException("The crafting action response is invalid.");
    }

    private static async Task WriteSeasonEquipmentActionAsync<T>(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,string seasonId,string kind,string requestId,string hash,EquipmentResponse? before,EquipmentResponse? after,T response,DateTimeOffset now,CancellationToken ct)
    {
        await using var command=new NpgsqlCommand("""
            INSERT INTO season_equipment_actions(action_id,player_id,season_id,action_kind,request_id,request_hash,before_item,after_item,response_json,created_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,connection,transaction);
        command.Parameters.AddWithValue(Guid.NewGuid());command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(seasonId);
        command.Parameters.AddWithValue(kind);command.Parameters.AddWithValue(requestId);command.Parameters.AddWithValue(hash);
        command.Parameters.AddWithValue(NpgsqlDbType.Jsonb,before is null?DBNull.Value:JsonSerializer.Serialize(before));
        command.Parameters.AddWithValue(NpgsqlDbType.Jsonb,after is null?DBNull.Value:JsonSerializer.Serialize(after));
        command.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(response));command.Parameters.AddWithValue(now);
        await command.ExecuteNonQueryAsync(ct);
    }

    private static async Task<int> InventoryArmorCountAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,Guid playerId,string seasonId,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand("SELECT count(*)::integer FROM equipments WHERE owner_id=$1 AND season_id=$2 AND asset_scope='ActiveSeason' AND location='Inventory'",connection,transaction);
        query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(seasonId);return (int)(await query.ExecuteScalarAsync(ct))!;
    }

    public async Task<SeasonCraftingResponse> GetSeasonCraftingAsync(Guid playerId,CancellationToken ct)
    {
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        var realm=await ReadCraftingRealmAsync(connection,null,playerId,null,ct);
        var wallet=await ReadCraftingWalletAsync(connection,null,playerId,realm,ct);
        var wishes=new List<CraftingWishResponse>();
        await using(var query=new NpgsqlCommand("SELECT quality,slot,element,wished_effect,failures FROM player_crafting_wishes WHERE player_id=$1 AND season_id=$2 ORDER BY quality,slot,element,wished_effect",connection))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(realm.Season.SeasonId);
            await using var reader=await query.ExecuteReaderAsync(ct);
            while(await reader.ReadAsync(ct))wishes.Add(new(reader.GetString(0),reader.GetString(1),reader.GetString(2),reader.GetString(3),reader.GetInt32(4),realm.Policy.Offer(reader.GetString(0)).WishAttempts-reader.GetInt32(4)));
        }
        var recipes=await ReadSeasonRecipesAsync(connection,null,playerId,realm.Season.SeasonId,ct);
        return new(new(realm.Season.SeasonId,"D0",realm.Season.RulesetId,realm.Season.ConfigVersion,realm.Season.StatsVersion),BlueprintWalletResponse(wallet),realm.MaximumDifficulty,
            realm.Policy.Offers.Select(row=>new CraftingOfferResponse(row.Quality,row.MinimumDifficulty,row.MarkKind.ToString(),row.MarkCost,row.ReforgeFragmentCost,row.WishAttempts)).ToArray(),wishes,recipes);
    }

    public async Task<CraftEquipmentResponse> CraftSeasonEquipmentAsync(Guid playerId,string requestId,CraftEquipmentRequest request,CancellationToken ct)
    {
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,playerId,ct);
        var hash=HashIdempotentRequest("equipment.craft",request);
        var replay=await ReadSeasonEquipmentActionAsync<CraftEquipmentResponse>(connection,transaction,playerId,"equipment.craft",requestId,hash,ct);
        if(replay is not null){await transaction.CommitAsync(ct);return replay;}
        var realm=await ReadCraftingRealmAsync(connection,transaction,playerId,request.SeasonId,ct);
        RequireCraftingShape(request.Slot,request.Element,request.WishedEffect);RequireCraftingTier(realm,request.Quality);
        if(!SeasonCraftingConfig.Effects.Contains(request.WishedEffect,StringComparer.Ordinal))throw new DomainValidationException("Select a valid effect wish before crafting.");
        var wallet=await ReadCraftingWalletAsync(connection,transaction,playerId,realm,ct);
        if(wallet.Version!=request.ExpectedWalletVersion)throw new DomainValidationException("The crafting wallet changed. Reload and retry.");
        if(await InventoryArmorCountAsync(connection,transaction,playerId,realm.Season.SeasonId,ct)>=50)throw new DomainValidationException("The equipment inventory is full.");
        var payment=realm.Policy.Payment(request.Quality,wallet.BlueprintMarks,wallet.OrangeBlueprintMarks);
        int failures;
        await using(var query=new NpgsqlCommand("SELECT failures FROM player_crafting_wishes WHERE player_id=$1 AND season_id=$2 AND quality=$3 AND slot=$4 AND element=$5 AND wished_effect=$6 FOR UPDATE",connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(realm.Season.SeasonId);query.Parameters.AddWithValue(request.Quality);
            query.Parameters.AddWithValue(request.Slot);query.Parameters.AddWithValue(request.Element);query.Parameters.AddWithValue(request.WishedEffect);
            failures=await query.ExecuteScalarAsync(ct) is int value?value:0;
        }
        var now=(timeProvider??TimeProvider.System).GetUtcNow();
        var paid=await SeasonRepository.ApplyWithinTransactionAsync(connection,transaction,playerId,realm.Context,0,0,0,
            "equipment.craft",requestId,SeasonWalletPurpose.General,now,hash,ct,-payment.Blueprints,-payment.OrangeBlueprints);
        var offer=realm.Policy.Offer(request.Quality);
        var roll=realm.Policy.Wish(request.Quality,request.WishedEffect,failures,failures==offer.WishAttempts-1?0:_craftingRandom(3));
        var secondary=request.Slot=="Feet" && _craftingRandom(2)==1?"ForcedEscape":"DrawInterval";
        var item=new EquipmentResponse(Guid.NewGuid(),request.Slot,request.Quality,0,false,"Inventory",1,request.Element,roll.EffectAffix,secondary,
            realm.Season.SeasonId,realm.Season.SeasonId,"ActiveSeason",realm.Season.StatsVersion,"MarkCraft",false);
        await using(var insert=new NpgsqlCommand("""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES($1,$2,$3,$4,0,false,'Inventory',1,$5,$6,$7,$8,$9,$9,'ActiveSeason',$10,'MarkCraft',$11)
            """,connection,transaction))
        {
            insert.Parameters.AddWithValue(item.InstanceId);insert.Parameters.AddWithValue(playerId);insert.Parameters.AddWithValue(item.Slot);insert.Parameters.AddWithValue(item.Quality);
            insert.Parameters.AddWithValue(now);insert.Parameters.AddWithValue(item.Element!);insert.Parameters.AddWithValue(item.EffectAffix!);insert.Parameters.AddWithValue(item.SecondaryTrait!);
            insert.Parameters.AddWithValue(realm.Season.SeasonId);insert.Parameters.AddWithValue(realm.Season.StatsVersion);insert.Parameters.AddWithValue((short)realm.MaximumDifficulty);
            await insert.ExecuteNonQueryAsync(ct);
        }
        await using(var update=new NpgsqlCommand("""
            INSERT INTO player_crafting_wishes(player_id,season_id,quality,slot,element,wished_effect,failures,updated_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT(player_id,season_id,quality,slot,element,wished_effect)
            DO UPDATE SET failures=EXCLUDED.failures,version=player_crafting_wishes.version+1,updated_at=EXCLUDED.updated_at
            """,connection,transaction))
        {
            update.Parameters.AddWithValue(playerId);update.Parameters.AddWithValue(realm.Season.SeasonId);update.Parameters.AddWithValue(request.Quality);
            update.Parameters.AddWithValue(request.Slot);update.Parameters.AddWithValue(request.Element);update.Parameters.AddWithValue(request.WishedEffect);
            update.Parameters.AddWithValue(roll.FailuresAfter);update.Parameters.AddWithValue(now);await update.ExecuteNonQueryAsync(ct);
        }
        await WriteInventoryMovementAsync(connection,transaction,playerId,item.InstanceId,"NotMinted","Inventory","equipment.craft",ct,requestId,realm.Season.SeasonId);
        var response=new CraftEquipmentResponse(item,BlueprintWalletResponse(paid),new(request.Quality,request.Slot,request.Element,request.WishedEffect,roll.FailuresAfter,offer.WishAttempts-roll.FailuresAfter),payment.Blueprints,payment.OrangeBlueprints);
        await WriteSeasonEquipmentActionAsync(connection,transaction,playerId,realm.Season.SeasonId,"equipment.craft",requestId,hash,null,item,response,now,ct);
        await transaction.CommitAsync(ct);return response;
    }
}
