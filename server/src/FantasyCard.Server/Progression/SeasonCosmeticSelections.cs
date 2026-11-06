using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonJourneyRepository
{
    public async Task<CosmeticSelectionResponse> SelectCosmeticAsync(Guid player,string requestId,CosmeticSelectionRequest request,CancellationToken ct)
    {
        RequireRewardIdentity(requestId);
        if(request.CosmeticId is not null)RequireRewardIdentity(request.CosmeticId);
        var column=request.Slot switch {"AvatarFrame"=>"avatar_frame_id","CardBack"=>"card_back_id","Title"=>"title_id",_=>throw new DomainValidationException("This cosmetic slot cannot be selected.")};
        if(request.ExpectedVersion<0)throw new DomainValidationException("The cosmetic selection version is invalid.");
        var hash=PersistentIdempotency.Hash(request);var now=clock.GetUtcNow();
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);await LockRewardPlayerAsync(c,t,player,ct);
        var replay=await PersistentIdempotency.ReadAsync<CosmeticSelectionResponse>(c,t,player,"cosmetic.select",requestId,hash,ct);
        if(replay is not null){await t.CommitAsync(ct);return replay;}
        if(request.CosmeticId is not null)
        {
            await using var q=new NpgsqlCommand("SELECT kind FROM player_cosmetics WHERE player_id=$1 AND cosmetic_id=$2",c,t);
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(request.CosmeticId);
            if(await q.ExecuteScalarAsync(ct) as string!=request.Slot)
                throw new DomainValidationException("The selected cosmetic is not owned in this display slot.");
        }
        await using(var q=new NpgsqlCommand("INSERT INTO player_cosmetic_profiles(player_id) VALUES($1) ON CONFLICT DO NOTHING",c,t))
        {q.Parameters.AddWithValue(player);await q.ExecuteNonQueryAsync(ct);}
        var prior=await ReadCosmeticSelectionAsync(c,t,player,true,ct);
        if(prior.Version!=request.ExpectedVersion)throw new DomainValidationException("Cosmetic ownership or selection changed. Reload before choosing.");
        var selected=request.Slot switch {"AvatarFrame"=>prior.AvatarFrameId,"CardBack"=>prior.CardBackId,_=>prior.TitleId};
        if(selected!=request.CosmeticId)
        {
            await using var q=new NpgsqlCommand($"UPDATE player_cosmetic_profiles SET {column}=$1,version=version+1 WHERE player_id=$2",c,t);
            q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)request.CosmeticId??DBNull.Value);q.Parameters.AddWithValue(player);await q.ExecuteNonQueryAsync(ct);
        }
        var response=await ReadCosmeticSelectionAsync(c,t,player,false,ct);
        await PersistentIdempotency.WriteAsync(c,t,player,"cosmetic.select",requestId,hash,response,now,ct);await t.CommitAsync(ct);return response;
    }
}
