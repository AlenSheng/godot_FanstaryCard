using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonActivityRepository
{
    private const string RewardSelect="""
        SELECT reward_id,season_id,event_id,rule_id,reward_kind,reward_amount,hero_class,token_cost,quantity,state,created_at,claimed_at,config_version
        FROM season_activity_redemptions
        """;
    private static ActivityRewardResponse Reward(NpgsqlDataReader r,bool canClaim)=>new(r.GetGuid(0),r.GetString(1),r.GetString(2),r.GetString(3),
        r.GetString(4),r.GetInt32(5),r.IsDBNull(6)?null:r.GetString(6),r.GetInt32(7),r.GetInt32(8),r.GetString(9),
        r.GetFieldValue<DateTimeOffset>(10),r.IsDBNull(11)?null:r.GetFieldValue<DateTimeOffset>(11),canClaim&&r.GetString(9)=="Pending",r.GetString(12));

    public async Task<ActivityExchangeResponse> ExchangeAsync(Guid player,string activity,string requestId,ActivityExchangeRequest request,CancellationToken ct)
    {
        RequireKey(requestId);var hash=PersistentIdempotency.Hash(new {activity,request});
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);await LockPlayer(c,t,player,ct);
        var replay=await Replay<ActivityExchangeResponse>(c,t,player,"exchange",requestId,hash,ct);
        if(replay is not null){await t.CommitAsync(ct);return replay;}
        var realm=await Realm(c,t,request.SeasonId,activity,true,ct);var now=clock.GetUtcNow();var policy=realm.Policy!;
        if(now<realm.Window.StartsAt||now>=realm.Window.EndsAt&&!policy.LateExchange)
            throw new DomainValidationException("This activity cannot accept exchanges at the current time.");
        var rule=policy.Exchange(request.RuleId);var quote=policy.Quote(request.RuleId,request.Quantity);
        if(rule.RewardKind=="bound_class_soul"?request.HeroClass is not ("Priest" or "Mage" or "Guardian"):request.HeroClass is not null)
            throw new DomainValidationException("The selected activity soul class is invalid.");
        var account=await Account(c,t,player,request.SeasonId,activity,true,ct);
        if(account.Version!=request.ExpectedAccountVersion)throw new DomainValidationException("Activity balance changed. Reload before exchanging.");
        if(account.Earned-account.Spent<quote.Cost)throw new DomainValidationException("Not enough bound tokens in this original activity.");
        await using(var used=new NpgsqlCommand("SELECT COALESCE(sum(quantity),0)::integer FROM season_activity_redemptions WHERE player_id=$1 AND season_id=$2 AND event_id=$3 AND rule_id=$4",c,t))
        {
            used.Parameters.AddWithValue(player);used.Parameters.AddWithValue(request.SeasonId);used.Parameters.AddWithValue(activity);used.Parameters.AddWithValue(rule.RuleId);
            if((int)(await used.ExecuteScalarAsync(ct))!+request.Quantity>rule.EventLimit)
                throw new DomainValidationException("The activity exchange limit has been reached.");
        }
        var reward=new ActivityRewardResponse(Guid.CreateVersion7(),request.SeasonId,activity,rule.RuleId,rule.RewardKind,quote.Reward,
            request.HeroClass,quote.Cost,request.Quantity,"Pending",now,null,true,realm.Season.ConfigVersion);
        await using(var q=new NpgsqlCommand("""
            INSERT INTO season_activity_redemptions(reward_id,player_id,season_id,event_id,config_version,rule_id,quantity,token_cost,reward_kind,reward_amount,hero_class,state,created_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'Pending',$12)
            """,c,t))
        {
            q.Parameters.AddWithValue(reward.RewardId);q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(request.SeasonId);q.Parameters.AddWithValue(activity);
            q.Parameters.AddWithValue(reward.ConfigVersion);q.Parameters.AddWithValue(rule.RuleId);q.Parameters.AddWithValue(request.Quantity);q.Parameters.AddWithValue(quote.Cost);
            q.Parameters.AddWithValue(rule.RewardKind);q.Parameters.AddWithValue(quote.Reward);q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)request.HeroClass??DBNull.Value);
            q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
        }
        await using(var q=new NpgsqlCommand("UPDATE player_season_activity_accounts SET spent=spent+$1,version=version+1 WHERE player_id=$2 AND season_id=$3 AND event_id=$4",c,t))
        {q.Parameters.AddWithValue(quote.Cost);q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(request.SeasonId);q.Parameters.AddWithValue(activity);await q.ExecuteNonQueryAsync(ct);}
        var remaining=account.Earned-account.Spent-quote.Cost;
        await TokenLedger(c,t,player,request.SeasonId,activity,-quote.Cost,remaining,"exchange",reward.RewardId,now,ct);
        var result=new ActivityExchangeResponse(reward,remaining,account.Version+1);await Receipt(c,t,player,"exchange",requestId,hash,result,now,ct);
        await t.CommitAsync(ct);return result;
    }

    public async Task<ActivityClaimResponse> ClaimAsync(Guid player,Guid rewardId,string requestId,CancellationToken ct)
    {
        RequireKey(requestId);var hash=PersistentIdempotency.Hash(new {rewardId});
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);await LockPlayer(c,t,player,ct);
        var replay=await Replay<ActivityClaimResponse>(c,t,player,"claim",requestId,hash,ct);
        if(replay is not null){await t.CommitAsync(ct);return replay;}
        ActivityRewardResponse reward;
        await using(var q=new NpgsqlCommand(RewardSelect+" WHERE reward_id=$1 AND player_id=$2 FOR UPDATE",c,t))
        {
            q.Parameters.AddWithValue(rewardId);q.Parameters.AddWithValue(player);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct))throw new DomainValidationException("The activity reward does not belong to this account.");reward=Reward(r,true);
        }
        var now=clock.GetUtcNow();
        if(reward.State=="Claimed")
        {
            await using var q=new NpgsqlCommand("SELECT claim_json::text FROM season_activity_redemptions WHERE reward_id=$1",c,t);q.Parameters.AddWithValue(rewardId);
            var prior=JsonSerializer.Deserialize<ActivityClaimResponse>((string)(await q.ExecuteScalarAsync(ct))!)??throw new InvalidOperationException("The original activity claim is invalid.");
            await Receipt(c,t,player,"claim",requestId,hash,prior,now,ct);await t.CommitAsync(ct);return prior;
        }
        var realm=await Realm(c,t,reward.SeasonId,reward.EventId,true,ct);var rule=realm.Policy!.Exchange(reward.RuleId);var quote=realm.Policy.Quote(reward.RuleId,reward.Quantity);
        if(reward.ConfigVersion!=realm.Season.ConfigVersion||rule.RewardKind!=reward.RewardKind||quote.Cost!=reward.TokenCost||quote.Reward!=reward.RewardAmount)
            throw new DomainValidationException("The held activity reward differs from its original source.");
        long balance;
        if(reward.RewardKind=="bound_fragments")
        {
            var wallet=await SeasonRepository.ApplyWithinTransactionAsync(c,t,player,realm.Season.ContextFor(0),0,reward.RewardAmount,0,
                "activity.claim",rewardId.ToString("D"),SeasonWalletPurpose.LateSettlement,now,hash,ct);balance=wallet.EquipmentFragments;
        }
        else if(reward.RewardKind=="potion")
        {
            await using var q=new NpgsqlCommand("UPDATE player_consumables SET health_potion_count=health_potion_count+$1,version=version+1 WHERE player_id=$2 RETURNING health_potion_count",c,t);
            q.Parameters.AddWithValue(reward.RewardAmount);q.Parameters.AddWithValue(player);
            balance=await q.ExecuteScalarAsync(ct) is int value?value:throw new DomainValidationException("The activity consumable aggregate is missing.");
        }
        else
        {
            var currency=reward.RewardKind=="bound_warrior_soul"?"WarriorSoul":reward.HeroClass+"Soul";
            var column=currency switch {"WarriorSoul"=>"warrior_soul","PriestSoul"=>"priest_soul","MageSoul"=>"mage_soul","GuardianSoul"=>"guardian_soul",_=>throw new DomainValidationException("The held activity soul class is invalid.")};
            await using(var q=new NpgsqlCommand($"UPDATE player_materials SET {column}={column}+$1,version=version+1 WHERE player_id=$2 RETURNING {column}",c,t))
            {q.Parameters.AddWithValue(reward.RewardAmount);q.Parameters.AddWithValue(player);balance=await q.ExecuteScalarAsync(ct) is long value?value:throw new DomainValidationException("The permanent activity soul aggregate is missing.");}
            // D0 is the account-level accounting context, not a combat completion.
            await using var ledger=new NpgsqlCommand("""
                INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at,
                    season_id,source_kind,difficulty_id,ruleset_id,config_version,stats_version)
                VALUES($1,$2,$3,$4,$5,$6,'activity.claim',$7,$8,'SeasonActivity','D0',$9,$10,$11)
                """,c,t);
            ledger.Parameters.AddWithValue(Guid.CreateVersion7());ledger.Parameters.AddWithValue(player);ledger.Parameters.AddWithValue(rewardId.ToString("D"));ledger.Parameters.AddWithValue(currency);
            ledger.Parameters.AddWithValue((long)reward.RewardAmount);ledger.Parameters.AddWithValue(balance);ledger.Parameters.AddWithValue(now);ledger.Parameters.AddWithValue(reward.SeasonId);
            ledger.Parameters.AddWithValue(realm.Season.RulesetId);ledger.Parameters.AddWithValue(realm.Season.ConfigVersion);
            ledger.Parameters.AddWithValue(realm.Season.StatsVersion);await ledger.ExecuteNonQueryAsync(ct);
        }
        var result=new ActivityClaimResponse(reward with {State="Claimed",ClaimedAt=now,CanClaim=false},balance);
        await using(var q=new NpgsqlCommand("UPDATE season_activity_redemptions SET state='Claimed',claimed_at=$1,claim_json=$2 WHERE reward_id=$3",c,t))
        {q.Parameters.AddWithValue(now);q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(result));q.Parameters.AddWithValue(rewardId);await q.ExecuteNonQueryAsync(ct);}
        await using(var q=new NpgsqlCommand("INSERT INTO season_activity_reward_ledger(reward_id,player_id,season_id,event_id,reward_kind,reward_amount,balance_after,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)",c,t))
        {
            q.Parameters.AddWithValue(rewardId);q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(reward.SeasonId);q.Parameters.AddWithValue(reward.EventId);
            q.Parameters.AddWithValue(reward.RewardKind);q.Parameters.AddWithValue(reward.RewardAmount);q.Parameters.AddWithValue(balance);q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
        }
        await Receipt(c,t,player,"claim",requestId,hash,result,now,ct);await t.CommitAsync(ct);return result;
    }
}
