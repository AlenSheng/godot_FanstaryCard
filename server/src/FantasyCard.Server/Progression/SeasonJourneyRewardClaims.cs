using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonJourneyRepository
{
    private static readonly JsonSerializerOptions RewardGrantJson=new(JsonSerializerDefaults.Web){Converters={new JsonStringEnumConverter()}};

    private static void RequireRewardIdentity(string key)
    {
        if(string.IsNullOrWhiteSpace(key)||key.Length>80||key.Any(char.IsControl))
            throw new DomainValidationException("The journey reward identity is invalid.");
    }

    private static async Task LockRewardPlayerAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE",c,t);q.Parameters.AddWithValue(player);
        if(await q.ExecuteScalarAsync(ct) is null)throw new DomainValidationException("The journey reward account is unavailable.");
    }

    private static HeroClass? RewardClass(string? value)=>value switch
    {
        null=>null,"Priest"=>HeroClass.Priest,"Mage"=>HeroClass.Mage,"Guardian"=>HeroClass.Guardian,
        _=>throw new DomainValidationException("The selected journey soul class is invalid.")
    };

    public async Task<JourneyClaimResponse> ClaimRewardAsync(Guid player,Guid rewardId,string requestId,JourneyClaimRequest request,CancellationToken ct)
    {
        RequireRewardIdentity(requestId);RequireRewardIdentity(request.SeasonId);var choice=RewardClass(request.HeroClass);
        var hash=PersistentIdempotency.Hash(new {rewardId,request});var now=clock.GetUtcNow();
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);await LockRewardPlayerAsync(c,t,player,ct);
        var replay=await PersistentIdempotency.ReadAsync<JourneyClaimResponse>(c,t,player,"journey.reward.claim",requestId,hash,ct);
        if(replay is not null){await t.CommitAsync(ct);return replay;}
        HeldJourneyReward held;
        await using(var q=new NpgsqlCommand("SELECT "+HeldRewardColumns+" FROM season_journey_reward_entitlements WHERE reward_id=$1 AND player_id=$2 FOR UPDATE",c,t))
        {
            q.Parameters.AddWithValue(rewardId);q.Parameters.AddWithValue(player);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct))throw new DomainValidationException("The journey reward does not belong to this account.");held=ReadHeldReward(r);
        }
        if(held.SeasonId!=request.SeasonId||held.Definition.RequiresClassChoice!=(choice is not null))
            throw new DomainValidationException("The journey reward season or class choice differs from its original source.");
        if(held.State=="Claimed")
        {
            if(held.HeroClassChoice!=request.HeroClass)throw new DomainValidationException("The claimed journey class choice cannot be changed.");
            var prior=JsonSerializer.Deserialize<JourneyClaimResponse>(held.ResponseJson??throw new InvalidDataException("The original journey claim is missing."))
                ??throw new InvalidDataException("The original journey claim is invalid.");
            if(prior.Reward.RewardId!=rewardId||prior.Reward.SeasonId!=held.SeasonId||prior.Reward.ConfigVersion!=held.ConfigVersion||prior.Reward.State!="Claimed")
                throw new InvalidDataException("The durable journey response differs from its original reward.");
            await PersistentIdempotency.WriteAsync(c,t,player,"journey.reward.claim",requestId,hash,prior,now,ct);await t.CommitAsync(ct);return prior;
        }
        var realm=await RewardRealmAsync(c,t,held.SeasonId,true,ct)??throw new DomainValidationException("The original journey season is unavailable.");
        var config=realm.Config!;var policy=config.SeasonJourneyRewards??throw new DomainValidationException("This original season has no published rewards.");
        var progress=await RewardProgressAsync(c,t,player,held.SeasonId,true,ct);
        if(progress.ConfigVersion!=config.Version||now<realm.Season.StartsAtUtc)
            throw new DomainValidationException("The journey progress differs from its original reward season.");
        ValidateHeldReward(held,realm.Season,config,progress.Experience,progress.Version);
        var definition=held.Definition;var grant=new SeasonJourneyRewardGrant(definition.RewardId,definition.Level,definition.Kind,
            definition.Amount,definition.Ownership,choice,held.PackCardIds,definition.CosmeticId);
        policy.ValidateGrant(grant,config);var grants=new List<ShopGrantResponse>();long? balance=null;var cosmeticNew=false;
        if(definition.Kind=="EquipmentFragments")
        {
            var wallet=await SeasonRepository.ApplyWithinTransactionAsync(c,t,player,realm.Season.ContextFor(0),0,definition.Amount,0,
                "journey.claim",rewardId.ToString("D"),SeasonWalletPurpose.LateSettlement,now,
                PersistentIdempotency.Hash(new {rewardId,held.ConfigVersion,held.ConfigHash,definition}),ct);
            balance=wallet.EquipmentFragments;grants.Add(new("EquipmentFragments",definition.Amount));
        }
        else if(definition.Kind is "WarriorSoul" or "ClassSoul")
        {
            var currency=definition.Kind=="WarriorSoul"?"WarriorSoul":request.HeroClass+"Soul";
            balance=await GrantJourneySoulAsync(c,t,player,held,realm.Season,currency,now,ct);grants.Add(new(currency,definition.Amount));
        }
        else if(definition.Kind=="CardPack")
        {
            await PermanentCardCopies.EnableWithinTransactionAsync(c,t,player,config.Version,now,ct);
            foreach(var group in held.PackCardIds.GroupBy(id=>id,StringComparer.Ordinal))
            {
                var card=config.Cards.Single(value=>value.CardId==group.Key);
                var credited=await PermanentCardCopies.GrantWithinTransactionAsync(c,t,player,card,group.Count(),"journey.claim",rewardId.ToString("D"),now,ct);
                grants.Add(new("Cards",credited.Quantity,credited.CardId,credited.NewlyUnlocked,credited.CopiesAfter,credited.Version));
            }
        }
        else if(definition.Kind=="Cosmetic")cosmeticNew=await GrantJourneyCosmeticAsync(c,t,player,held,policy.Cosmetic(definition.CosmeticId!),now,ct);
        else throw new InvalidDataException("The original journey reward kind is unsupported.");
        var claimed=held with {State="Claimed",ClaimedAt=now,HeroClassChoice=request.HeroClass};
        var response=new JourneyClaimResponse(RewardView(claimed,false),grants,balance,cosmeticNew);
        await using(var q=new NpgsqlCommand("""
            UPDATE season_journey_reward_entitlements SET state='Claimed',claimed_at=$1,hero_class_choice=$2,grant_json=$3,response_json=$4 WHERE reward_id=$5
            """,c,t))
        {
            q.Parameters.AddWithValue(now);q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)request.HeroClass??DBNull.Value);
            q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(grant,RewardGrantJson));
            q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(response));q.Parameters.AddWithValue(rewardId);await q.ExecuteNonQueryAsync(ct);
        }
        await using(var q=new NpgsqlCommand("""
            INSERT INTO season_journey_grant_ledger(reward_id,player_id,season_id,reward_level,reward_kind,reward_amount,
                actual_card_copies,grants_json,balance_after,cosmetic_newly_owned,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,c,t))
        {
            q.Parameters.AddWithValue(rewardId);q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(held.SeasonId);q.Parameters.AddWithValue((short)definition.Level);
            q.Parameters.AddWithValue(definition.Kind);q.Parameters.AddWithValue(definition.Amount);q.Parameters.AddWithValue(definition.Kind=="CardPack"?3:0);
            q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(grants));q.Parameters.AddWithValue(NpgsqlDbType.Bigint,(object?)balance??DBNull.Value);
            q.Parameters.AddWithValue(cosmeticNew);q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
        }
        await PersistentIdempotency.WriteAsync(c,t,player,"journey.reward.claim",requestId,hash,response,now,ct);await t.CommitAsync(ct);return response;
    }
}
