using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class EconomyRepository
{
    private readonly Func<int,int> _shopRandom=shopRandom??RandomNumberGenerator.GetInt32;
    private sealed record ShopRealm(SeasonScheduleSnapshot Schedule,GameConfigCatalog? Config,string State)
    { public SeasonDefinition? Season=>Schedule.Current; }
    private sealed record ShopDay(string Key,string Version,string Hash,int Refreshes,IReadOnlyList<SeasonShopOffer> Offers)
    { public string Rotation=>$"{Key}~{Refreshes}"; }

    private async Task<ShopRealm> ShopRealmAsync(NpgsqlConnection c,NpgsqlTransaction? t,DateTimeOffset now,bool required,CancellationToken ct,SeasonScheduleSnapshot? snapshot=null)
    {
        var schedule=snapshot??await ReadMarketScheduleAsync(c,t,now,ct);
        if(schedule.LegacyAllowed)return new(schedule,GameConfigCatalog.Current,"Legacy");
        if(schedule.Current is not {} season)
        {
            if(required)throw new DomainValidationException("No active season is accepting shop purchases.");
            return new(schedule,null,schedule.Stage.ToString());
        }
        try
        {
            var config=_marketConfigurations.Resolve(season.ConfigVersion);
            await using var q=new NpgsqlCommand("SELECT config_sha256 FROM season_definitions WHERE season_id=$1",c,t);q.Parameters.AddWithValue(season.SeasonId);
            if(await q.ExecuteScalarAsync(ct) as string!=config.ContentHash||config.SeasonShop is null)
                throw new DomainValidationException("The original season shop policy is unavailable or differs from its publication.");
            return new(schedule,config,"Active");
        }
        catch(Exception e) when(e is IOException or DomainValidationException)
        {
            if(required)throw new DomainValidationException("The original season shop configuration is unavailable.");
            return new(schedule,null,"Unavailable");
        }
    }

    public Task<ShopResponse> GetShopAsync(Guid playerId,CancellationToken ct)=>GetShopForScheduleAsync(playerId,null,ct);

    internal async Task<ShopResponse> GetShopForScheduleAsync(Guid playerId,SeasonScheduleSnapshot? snapshot,CancellationToken ct)
    {
        var schedule=snapshot??await new SeasonRepository(dataSource,timeProvider).GetScheduleAsync(ct);
        if(schedule.LegacyAllowed)return await GetLegacyShopAsync(playerId,ct);
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);
        await LockPlayerAsync(c,t,playerId,ct);var now=timeProvider.GetUtcNow();var realm=await ShopRealmAsync(c,t,now,false,ct,snapshot);
        ShopDay? day=null;
        if(realm.State=="Active")
        {
            try { day=await ShopDayAsync(c,t,realm,now,ct); }
            catch(Exception e) when(e is IOException or DomainValidationException) { realm=realm with {State="Unavailable",Config=null}; }
        }
        var result=await ShopResponseAsync(c,t,playerId,realm,day,now,ct);await t.CommitAsync(ct);return result;
    }

    private async Task<ShopDay> ShopDayAsync(NpgsqlConnection c,NpgsqlTransaction t,ShopRealm realm,DateTimeOffset now,CancellationToken ct,bool refreshing=false)
    {
        var key=EconomySchedule.GetDailyResetKey(now);
        async Task<ShopDay?> Read()
        {
            await using var q=new NpgsqlCommand("SELECT s.config_version,s.config_sha256,s.refreshes_used,s.products_json::text,d.config_version,d.config_sha256 FROM season_shop_days s JOIN season_definitions d ON d.season_id=s.source_season_id WHERE s.reset_key=$1 "+(refreshing?"FOR UPDATE OF s":"FOR SHARE OF s"),c,t);
            q.Parameters.AddWithValue(key);await using var r=await q.ExecuteReaderAsync(ct);
            if(await r.ReadAsync(ct))
            {
                if(r.GetString(0)!=r.GetString(4)||r.GetString(1)!=r.GetString(5))throw new DomainValidationException("The frozen catalog differs from its original publication.");
                return new(key,r.GetString(0),r.GetString(1),r.GetInt32(2),
                    JsonSerializer.Deserialize<SeasonShopOffer[]>(r.GetString(3))??throw new DomainValidationException("The frozen shop offers are invalid."));
            }
            return null;
        }
        var day=await Read();
        if(day is null)
        {
            // Serialize only first publication, not all players' purchases.
            await using(var gate=new NpgsqlCommand("SELECT pg_advisory_xact_lock($1)",c,t))
            {gate.Parameters.AddWithValue(6_202_611_130_000_001L);await gate.ExecuteNonQueryAsync(ct);}
            day=await Read();
        }
        if(day is null)
        {
            var config=realm.Config!;
            string? legacyRotation=null;
            await using(var q=new NpgsqlCommand("SELECT rotation_key FROM shop_refresh_states WHERE shop_reset_key=$1 ORDER BY updated_at DESC FOR UPDATE",c,t))
            {q.Parameters.AddWithValue(key);await using var r=await q.ExecuteReaderAsync(ct);while(await r.ReadAsync(ct))legacyRotation??=r.GetString(0);}
            var start=DateTimeOffset.ParseExact(key+"T04:00:00+08:00","yyyy-MM-dd'T'HH:mm:sszzz",CultureInfo.InvariantCulture).ToUniversalTime();
            int used;
            await using(var q=new NpgsqlCommand("SELECT count(*)::integer FROM idempotency_records WHERE scope='shop.refresh' AND created_at>=$1 AND created_at<$2",c,t))
            {q.Parameters.AddWithValue(start);q.Parameters.AddWithValue(start.AddDays(1));used=(int)(await q.ExecuteScalarAsync(ct))!;}
            day=new(key,config.Version,config.ContentHash,used,config.SeasonShop!.Offers(config,$"{key}:refresh:{used}"));
            if(legacyRotation is not null)
            {
                var singles=new List<SeasonShopOffer>();
                await using var old=new NpgsqlCommand("SELECT product_id,payload_json::text,price_gold,limit_count FROM shop_rotations WHERE reset_key=$1 AND product_id LIKE 'daily_card_%' ORDER BY product_id",c,t);
                old.Parameters.AddWithValue(legacyRotation);await using(var r=await old.ExecuteReaderAsync(ct))
                    while(await r.ReadAsync(ct))
                    {
                        using var payload=JsonDocument.Parse(r.GetString(1));
                        singles.Add(new(r.GetString(0),"Cards",1,r.GetInt64(2),r.GetInt32(3),r.GetString(0),CardId:payload.RootElement.GetProperty("cardId").GetString()));
                    }
                if(singles.Count>0)
                {
                    day=day with {Offers=day.Offers.Where(o=>o.CardId is null).Concat(singles).ToArray()};
                    config.SeasonShop.ValidateOffers(config,day.Offers);
                }
            }
            await using var put=new NpgsqlCommand("INSERT INTO season_shop_days(reset_key,source_season_id,config_version,config_sha256,refreshes_used,products_json,created_at,updated_at) VALUES($1,$2,$3,$4,$5,$6,$7,$7)",c,t);
            put.Parameters.AddWithValue(key);put.Parameters.AddWithValue(realm.Season!.SeasonId);put.Parameters.AddWithValue(day.Version);
            put.Parameters.AddWithValue(day.Hash);put.Parameters.AddWithValue(used);put.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(day.Offers));put.Parameters.AddWithValue(now);await put.ExecuteNonQueryAsync(ct);
        }
        var frozen=_marketConfigurations.Resolve(day.Version);
        if(frozen.ContentHash!=day.Hash||frozen.SeasonShop is null)throw new DomainValidationException("The frozen daily shop catalog is unavailable.");
        frozen.SeasonShop.ValidateOffers(frozen,day.Offers);return day;
    }

    private static DateTimeOffset ShopResetAt(DateTimeOffset now)
    {
        var key=EconomySchedule.GetDailyResetKey(now);
        return DateTimeOffset.ParseExact(key+"T04:00:00+08:00","yyyy-MM-dd'T'HH:mm:sszzz",CultureInfo.InvariantCulture).AddDays(1);
    }

    private static async Task<ShopResponse> ShopResponseAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,ShopRealm realm,ShopDay? day,DateTimeOffset now,CancellationToken ct)
    {
        var wallet=await ReadMarketWalletAsync(c,t,player,realm.Schedule,ct);var products=new List<ShopProductResponse>();
        if(day is not null)
        {
            var owned=await OwnedCardIdsAsync(c,t,player,ct);
            foreach(var offer in day.Offers)
            {
                var purchased=await ShopPurchasedAsync(c,t,player,day,offer,ct);
                var payload=offer.CardId is not null?JsonSerializer.Serialize(new {cardId=offer.CardId,count=1}):
                    offer.Kind=="Cards"?JsonSerializer.Serialize(new {rarity="WhiteToPurple",count=offer.Amount}):
                    JsonSerializer.Serialize(new {amount=offer.Amount,heroClass=offer.HeroClass});
                products.Add(new(offer.ProductId,offer.Kind,offer.PriceGold,offer.DailyLimit,purchased,payload,offer.CardId is not null&&owned.Contains(offer.CardId)));
            }
        }
        return new(day?.Key??EconomySchedule.GetDailyResetKey(now),products,day?.Refreshes??0,realm.Config?.Economy.DailyShopRefreshLimit??0,
            new(realm.State,realm.Season?.SeasonId,realm.Season?.ConfigVersion,day?.Version,realm.Season?.EndsAtUtc,
                ShopResetAt(now),realm.State=="Active"&&day is not null,wallet,true),day?.Rotation);
    }

    private static async Task<int> ShopPurchasedAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,ShopDay day,SeasonShopOffer offer,CancellationToken ct)
    {
        var ids=day.Offers.Where(o=>o.QuotaGroup==offer.QuotaGroup).Select(o=>o.ProductId).ToArray();
        await using var q=new NpgsqlCommand("SELECT COALESCE(sum(quantity),0)::integer FROM shop_purchases WHERE player_id=$1 AND reset_key=$2 AND product_id=ANY($3)",c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(day.Key);q.Parameters.AddWithValue(NpgsqlDbType.Array|NpgsqlDbType.Varchar,ids);
        return (int)(await q.ExecuteScalarAsync(ct))!;
    }

    public async Task<ShopRefreshResult> RefreshShopAsync(Guid playerId,string requestId,CancellationToken ct)
    {
        RequireMarketRequestId(requestId);
        var schedule=await new SeasonRepository(dataSource,timeProvider).GetScheduleAsync(ct);
        if(schedule.LegacyAllowed)return await RefreshLegacyShopAsync(playerId,requestId,ct);
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);await LockPlayerAsync(c,t,playerId,ct);
        var hash=PersistentIdempotency.Hash(new {Action="shop.refresh",Version=1});
        ShopResponse? replay=null;
        await using(var q=new NpgsqlCommand("SELECT request_hash,response_json::text FROM season_shop_refresh_receipts WHERE player_id=$1 AND request_id=$2",c,t))
        {
            q.Parameters.AddWithValue(playerId);q.Parameters.AddWithValue(requestId);await using var r=await q.ExecuteReaderAsync(ct);
            if(await r.ReadAsync(ct)){if(r.GetString(0)!=hash)throw new IdempotencyConflictException();replay=JsonSerializer.Deserialize<ShopResponse>(r.GetString(1));}
        }
        replay??=await PersistentIdempotency.ReadAsync<ShopResponse>(c,t,playerId,"shop.refresh",requestId,hash,ct);
        if(replay is not null){await t.CommitAsync(ct);return new(replay,true);}
        var now=timeProvider.GetUtcNow();var realm=await ShopRealmAsync(c,t,now,true,ct);var day=await ShopDayAsync(c,t,realm,now,ct,true);
        var config=_marketConfigurations.Resolve(day.Version);
        if(day.Refreshes>=config.Economy.DailyShopRefreshLimit)throw new DomainValidationException("Daily shop refresh limit reached.");
        day=day with {Refreshes=day.Refreshes+1,Offers=config.SeasonShop!.Offers(config,$"{day.Key}:refresh:{day.Refreshes+1}")};
        await using(var q=new NpgsqlCommand("UPDATE season_shop_days SET refreshes_used=$1,products_json=$2,updated_at=$3 WHERE reset_key=$4",c,t))
        {q.Parameters.AddWithValue(day.Refreshes);q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(day.Offers));q.Parameters.AddWithValue(now);q.Parameters.AddWithValue(day.Key);await q.ExecuteNonQueryAsync(ct);}
        var result=await ShopResponseAsync(c,t,playerId,realm,day,now,ct);
        await using(var q=new NpgsqlCommand("INSERT INTO season_shop_refresh_receipts(player_id,request_id,request_hash,response_json,reset_key,created_at) VALUES($1,$2,$3,$4,$5,$6)",c,t))
        {q.Parameters.AddWithValue(playerId);q.Parameters.AddWithValue(requestId);q.Parameters.AddWithValue(hash);q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(result));q.Parameters.AddWithValue(day.Key);q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);}
        await t.CommitAsync(ct);return new(result,false);
    }

    public async Task<ShopPurchaseResponse> PurchaseAsync(Guid playerId,string requestId,PurchaseShopRequest request,CancellationToken ct)
    {
        RequireMarketRequestId(requestId);
        if(request.Quantity is <1 or >10||string.IsNullOrWhiteSpace(request.ProductId)||request.ProductId.Length>80)
            throw new DomainValidationException("Shop quantity or product is invalid.");
        var schedule=await new SeasonRepository(dataSource,timeProvider).GetScheduleAsync(ct);
        if(schedule.LegacyAllowed)
        {
            if(request.SeasonId is not null||request.CatalogVersion is not null)throw new DomainValidationException("The shop domain changed. Reload before purchasing.");
            return await PurchaseLegacyShopAsync(playerId,requestId,request,ct);
        }
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);await LockPlayerAsync(c,t,playerId,ct);
        var hash=Hash(request);
        await using(var q=new NpgsqlCommand("SELECT request_hash,product_id,quantity,granted_json::text,response_json::text FROM shop_purchases WHERE player_id=$1 AND request_id=$2",c,t))
        {
            q.Parameters.AddWithValue(playerId);q.Parameters.AddWithValue(requestId);await using var r=await q.ExecuteReaderAsync(ct);
            if(await r.ReadAsync(ct))
            {
                if(r.GetString(0)!=hash)throw new IdempotencyConflictException();
                ShopPurchaseResponse? result;
                if(!r.IsDBNull(4))result=JsonSerializer.Deserialize<ShopPurchaseResponse>(r.GetString(4))??throw new InvalidOperationException("The durable shop receipt is invalid.");
                else
                {
                    var id=r.GetString(1);var qty=r.GetInt32(2);var grant=JsonSerializer.Deserialize<string>(r.GetString(3))??r.GetString(3);await r.DisposeAsync();
                    result=new(id,qty,await CurrentGoldAsync(c,t,playerId,ct),grant);
                }
                await r.DisposeAsync();await t.CommitAsync(ct);return result;
            }
        }
        var now=timeProvider.GetUtcNow();var realm=await ShopRealmAsync(c,t,now,true,ct);var day=await ShopDayAsync(c,t,realm,now,ct);
        var config=_marketConfigurations.Resolve(day.Version);var policy=config.SeasonShop!;
        var offer=day.Offers.SingleOrDefault(o=>o.ProductId==request.ProductId)??throw new DomainValidationException("Shop product is unavailable.");
        if(request.SeasonId!=realm.Season!.SeasonId||request.ResetKey!=day.Key||request.RotationKey!=day.Rotation||
            request.ExpectedPriceGold!=offer.PriceGold||request.CatalogVersion!=day.Version)
            throw new DomainValidationException("Shop terms changed. Reload and confirm the current offer.");
        var count=await ShopPurchasedAsync(c,t,playerId,day,offer,ct);
        if(offer.DailyLimit>0&&checked(count+request.Quantity)>offer.DailyLimit)throw new DomainValidationException("Daily purchase limit reached.");
        var amount=checked(offer.Amount*request.Quantity);var total=checked(offer.PriceGold*request.Quantity);
        var payload=JsonSerializer.Serialize(new {amount=offer.Amount,heroClass=offer.HeroClass});
        await EnsurePaidBagCapacityAsync(c,t,playerId,offer.Kind,payload,request.Quantity,ct);
        var context=realm.Season.ContextFor(0);await SeasonRepository.EnsurePlayerWithinTransactionAsync(c,t,playerId,context,now,ct);
        await PermanentCardCopies.EnableWithinTransactionAsync(c,t,playerId,realm.Config!.Version,now,ct);
        var wallet=await SeasonRepository.ApplyWithinTransactionAsync(c,t,playerId,context,-total,
            offer.Kind=="EquipmentFragments"?amount:0,0,"shop.purchase",requestId,SeasonWalletPurpose.General,now,
            PersistentIdempotency.Hash(new {request,Total=total,Source="season-shop"}),ct);
        var grants=new List<ShopGrantResponse>();string granted;
        if(offer.Kind=="Cards")
        {
            var selected=Enumerable.Range(0,amount).Select(_=>offer.CardId is not null?
                config.Cards.Single(card=>card.CardId==offer.CardId):policy.Draw(config.Cards,_shopRandom)).ToArray();
            foreach(var group in selected.GroupBy(card=>card.CardId,StringComparer.Ordinal))
            {
                var grant=await PermanentCardCopies.GrantWithinTransactionAsync(c,t,playerId,group.First(),group.Count(),"shop.purchase",requestId,now,ct);
                grants.Add(new("Cards",grant.Quantity,grant.CardId,grant.NewlyUnlocked,grant.CopiesAfter,grant.Version));
            }
            granted=$"{amount} cards";
        }
        else if(offer.Kind=="EquipmentFragments") { grants.Add(new(offer.Kind,amount));granted=$"{amount} {offer.Kind}"; }
        else { granted=await GrantAsync(c,t,playerId,offer.Kind,payload,request.Quantity,requestId,ct);grants.Add(new(offer.Kind=="ClassSoul"?offer.HeroClass+"Soul":offer.Kind,amount)); }
        var balances=await ReadMarketWalletAsync(c,t,playerId,realm.Schedule,ct);
        var response=new ShopPurchaseResponse(offer.ProductId,request.Quantity,wallet.Gold,granted,grants,balances,
            realm.Season.SeasonId,realm.Season.ConfigVersion,day.Version,day.Key);
        await using(var q=new NpgsqlCommand("""
            INSERT INTO shop_purchases(purchase_id,player_id,reset_key,product_id,request_id,request_hash,quantity,price_gold,granted_json,created_at,
                season_id,config_version,catalog_version,quota_group,response_json)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            """,c,t))
        {
            q.Parameters.AddWithValue(Guid.CreateVersion7());q.Parameters.AddWithValue(playerId);q.Parameters.AddWithValue(day.Key);q.Parameters.AddWithValue(offer.ProductId);
            q.Parameters.AddWithValue(requestId);q.Parameters.AddWithValue(hash);q.Parameters.AddWithValue(request.Quantity);q.Parameters.AddWithValue(total);
            q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(granted));q.Parameters.AddWithValue(now);q.Parameters.AddWithValue(realm.Season.SeasonId);
            q.Parameters.AddWithValue(realm.Season.ConfigVersion);q.Parameters.AddWithValue(day.Version);q.Parameters.AddWithValue(offer.QuotaGroup);
            q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(response));await q.ExecuteNonQueryAsync(ct);
        }
        await t.CommitAsync(ct);return response;
    }
}
