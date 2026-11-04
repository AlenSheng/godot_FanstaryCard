using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Rooms;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed record MarketQuery(string Currency="Gold",string? Quality=null,string? Slot=null,string? Element=null,
    string? Effect=null,bool MaterialsOnly=false,bool PriceAscending=false);
public sealed record MarketPurchaseExpectation(string Currency,long Price,string? SeasonId);

public sealed partial class EconomyRepository
{
    private readonly PublishedConfigCatalogs _marketConfigurations=configurations??new(GameConfigCatalog.Current);
    private sealed record MarketRealm(SeasonScheduleSnapshot Schedule,GameConfigCatalog? Configuration,SeasonMarketConfig? Policy,string State,DateTimeOffset Now)
    {
        public SeasonDefinition? Season=>Schedule.Current;
        public bool Enabled=>State is "Legacy" or "Active";
        public int SharedSlots=>Policy?.SharedSlots??Configuration!.Economy.MarketActiveListings;
        public int ListingHours=>Policy?.ListingHours??Configuration!.Economy.MarketDurationHours;
        public int TaxBasisPoints=>Policy?.TaxBasisPoints??checked((int)((decimal)Configuration!.Economy.MarketFeeRate*10000));
        public long MinimumFee=>Policy?.MinimumFee??1;
    }
    private sealed record StoredMarketListing(MarketListingResponse Response,string Currency,long Price,string? SeasonId,
        string? ConfigVersion,string? StatsVersion,DateTimeOffset? SeasonEndsAt,string? RuleVersion,int TaxBasisPoints,long MinimumFee);
    private const string MarketSelect="""
        SELECT l.listing_id,l.seller_id,l.equipment_id,l.price_gold,l.status,l.version,l.created_at,l.expires_at,
            l.currency,l.price,l.season_id,l.config_version,l.stats_version,l.season_ends_at,l.market_rule_version,l.tax_basis_points,l.minimum_fee,
            e.slot,e.quality,e.level,e.is_bound,e.location,e.version,e.element,e.effect_affix,e.secondary_trait,
            e.origin_season_id,e.season_id,e.asset_scope,e.stats_version,e.source_kind,e.recipe_extracted,e.unique_affix,e.unique_element
        FROM market_listings l JOIN equipments e ON e.instance_id=l.equipment_id
        """;
    private static string? Text(NpgsqlDataReader reader,int ordinal)=>reader.IsDBNull(ordinal)?null:reader.GetString(ordinal);
    private static long MarketFee(long price,int basisPoints,long minimum)=>Math.Max(minimum,decimal.ToInt64(decimal.Floor((decimal)price*basisPoints/10000)));

    private static StoredMarketListing ReadMarketListing(NpgsqlDataReader reader)
    {
        var price=reader.IsDBNull(9)?reader.GetInt64(3):reader.GetInt64(9);var rule=Text(reader,14);
        var tax=reader.IsDBNull(15)?1000:reader.GetInt32(15);var minimum=reader.IsDBNull(16)?1:reader.GetInt64(16);
        var equipment=new EquipmentResponse(reader.GetGuid(2),reader.GetString(17),reader.GetString(18),reader.GetInt32(19),
            reader.GetBoolean(20),reader.GetString(21),reader.GetInt64(22),Text(reader,23),Text(reader,24),Text(reader,25),
            Text(reader,26),Text(reader,27),Text(reader,28),Text(reader,29),Text(reader,30),reader.IsDBNull(27)?null:reader.GetBoolean(31),Text(reader,32),Text(reader,33));
        var response=new MarketListingResponse(reader.GetGuid(0),reader.GetGuid(1),reader.GetGuid(2),reader.GetInt64(3),
            reader.GetString(4),reader.GetInt64(5),reader.GetFieldValue<DateTimeOffset>(6),reader.GetFieldValue<DateTimeOffset>(7),equipment,
            rule is null?null:reader.GetString(8),rule is null?null:price,Text(reader,10),Text(reader,11),
            reader.IsDBNull(13)?null:reader.GetFieldValue<DateTimeOffset>(13),rule is null?null:MarketFee(price,tax,minimum),rule is null?null:price-MarketFee(price,tax,minimum));
        return new(response,reader.GetString(8),price,Text(reader,10),Text(reader,11),Text(reader,12),response.SeasonEndsAt,rule,tax,minimum);
    }

    private static async Task<SeasonScheduleSnapshot> ReadMarketScheduleAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,DateTimeOffset now,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand("SELECT season_id,ruleset_id,config_version,stats_version,starts_at,ends_at,highest_open_difficulty FROM season_definitions WHERE ruleset_id='season-v1' ORDER BY starts_at",connection,transaction);
        await using var reader=await query.ExecuteReaderAsync(ct);var definitions=new List<SeasonDefinition>();
        while(await reader.ReadAsync(ct))definitions.Add(new(reader.GetString(0),reader.GetString(1),reader.GetString(2),reader.GetString(3),
            reader.GetFieldValue<DateTimeOffset>(4),reader.GetFieldValue<DateTimeOffset>(5),reader.GetInt16(6)));
        return SeasonSchedule.Resolve(definitions,now);
    }

    private async Task<MarketRealm> ReadMarketRealmAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,DateTimeOffset now,bool requireOpen,CancellationToken ct,
        SeasonScheduleSnapshot? frozenSchedule=null)
    {
        var schedule=frozenSchedule??await ReadMarketScheduleAsync(connection,transaction,now,ct);
        if(schedule.LegacyAllowed)return new(schedule,GameConfigCatalog.Current,null,"Legacy",now);
        if(schedule.Current is not { } season)
        {
            if(requireOpen)throw new DomainValidationException("No active season is accepting market trades.");
            return new(schedule,null,null,schedule.Stage.ToString(),now);
        }
        try
        {
            var config=_marketConfigurations.Resolve(season.ConfigVersion);
            await using var hash=new NpgsqlCommand("SELECT config_sha256 FROM season_definitions WHERE season_id=$1",connection,transaction);
            hash.Parameters.AddWithValue(season.SeasonId);
            if(await hash.ExecuteScalarAsync(ct) as string!=config.ContentHash || config.SeasonMarket is not { } policy)
                throw new DomainValidationException("The original season market policy is unavailable or differs from its publication.");
            return new(schedule,config,policy,"Active",now);
        }
        catch(IOException)
        {
            if(requireOpen)throw new DomainValidationException("The original season market configuration is unavailable.");
            return new(schedule,null,null,"Unavailable",now);
        }
        catch(DomainValidationException) when(!requireOpen)
        {
            // Browsing the camp remains possible; no prices or purchase permission
            // are invented when the original published market bundle is missing.
            return new(schedule,null,null,"Unavailable",now);
        }
    }

    private static async Task<WalletResponse> ReadMarketWalletAsync(NpgsqlConnection connection,NpgsqlTransaction? transaction,Guid playerId,SeasonScheduleSnapshot schedule,CancellationToken ct)
    {
        long gold,diamond;
        await using(var query=new NpgsqlCommand("SELECT gold,diamond FROM player_wallets WHERE player_id=$1",connection,transaction))
        {
            query.Parameters.AddWithValue(playerId);await using var reader=await query.ExecuteReaderAsync(ct);
            if(!await reader.ReadAsync(ct))throw new InvalidOperationException("Player wallet was not found.");
            gold=reader.GetInt64(0);diamond=reader.GetInt64(1);
        }
        if(!schedule.LegacyAllowed)
        {
            gold=0;
            if(schedule.Current is { } season)
            {
                await using var query=new NpgsqlCommand("SELECT w.gold FROM player_season_wallets w JOIN player_season_state p USING(player_id,season_id) WHERE w.player_id=$1 AND w.season_id=$2 AND w.archived_at IS NULL AND p.archived_at IS NULL",connection,transaction);
                query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(season.SeasonId);
                if(await query.ExecuteScalarAsync(ct) is long current)gold=current;
            }
        }
        return new(gold,diamond);
    }

    public async Task<WalletResponse> GetWalletAsync(Guid playerId,CancellationToken cancellationToken)
    {
        await using var connection=await dataSource.OpenConnectionAsync(cancellationToken);
        var schedule=await ReadMarketScheduleAsync(connection,null,timeProvider.GetUtcNow(),cancellationToken);
        return await ReadMarketWalletAsync(connection,null,playerId,schedule,cancellationToken);
    }

    private static void ValidateMarketQuery(MarketQuery query,int limit,int offset)
    {
        if(limit is <1 or >200 || offset is <0 or >1000000 || query.Currency is not ("Gold" or "Diamond") ||
            query.Quality is not (null or "White" or "Green" or "Blue" or "Purple" or "Orange" or "Red") ||
            query.Slot is not (null or "Head" or "Chest" or "Hands" or "Legs" or "Feet") ||
            query.Element is not (null or "Wood" or "Fire" or "Earth" or "Metal" or "Water") ||
            query.Effect is not (null or "Piercing" or "Bulwark" or "Vitality"))throw new DomainValidationException("The market filter is invalid.");
    }

    public Task<IReadOnlyList<MarketListingResponse>> GetMarketAsync(CancellationToken cancellationToken,int limit=200,int offset=0,MarketQuery? query=null)=>
        GetMarketForScheduleAsync(null,cancellationToken,limit,offset,query);

    internal async Task<IReadOnlyList<MarketListingResponse>> GetMarketForScheduleAsync(SeasonScheduleSnapshot? schedule,CancellationToken ct,int limit=200,int offset=0,MarketQuery? filter=null)
    {
        var query=filter??new();ValidateMarketQuery(query,limit,offset);
        await using var connection=await dataSource.OpenConnectionAsync(ct);var now=timeProvider.GetUtcNow();
        var realm=await ReadMarketRealmAsync(connection,null,now,false,ct,schedule);
        if(!realm.Enabled || realm.Season is null && query.Currency!="Gold")return [];
        var scope=realm.Season is null?"l.season_id IS NULL AND e.season_id IS NULL AND e.asset_scope IS NULL":"l.season_id=$2 AND e.season_id=$2 AND e.asset_scope='ActiveSeason' AND e.stats_version=$3";
        var order=query.MaterialsOnly?"e.level,COALESCE(l.price,l.price_gold),l.created_at,l.listing_id":query.PriceAscending?"COALESCE(l.price,l.price_gold),l.created_at,l.listing_id":"l.created_at DESC,l.listing_id DESC";
        await using var command=new NpgsqlCommand(MarketSelect+" WHERE l.status='Active' AND l.expires_at>$1 AND ("+scope+") AND l.currency=$4 "+
            "AND ($5::varchar IS NULL OR e.quality=$5) AND ($6::varchar IS NULL OR e.slot=$6) AND ($7::varchar IS NULL OR e.element=$7) "+
            "AND ($8::varchar IS NULL OR e.effect_affix=$8) AND (NOT $9 OR COALESCE(e.source_kind,'') NOT IN ('BotReward','Borrowed')) "+
            "ORDER BY "+order+" LIMIT $10 OFFSET $11",connection);
        command.Parameters.AddWithValue(now);command.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.SeasonId??DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.StatsVersion??DBNull.Value);command.Parameters.AddWithValue(query.Currency);
        foreach(var value in new[]{query.Quality,query.Slot,query.Element,query.Effect})command.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)value??DBNull.Value);
        command.Parameters.AddWithValue(query.MaterialsOnly);command.Parameters.AddWithValue(limit);command.Parameters.AddWithValue(offset);
        await using var reader=await command.ExecuteReaderAsync(ct);var rows=new List<MarketListingResponse>();
        while(await reader.ReadAsync(ct))rows.Add(ReadMarketListing(reader).Response);
        return rows;
    }

    public async Task<MarketListingResponse?> GetListingForEventAsync(Guid listingId,CancellationToken cancellationToken)
    {
        await using var command=dataSource.CreateCommand(MarketSelect+" WHERE l.listing_id=$1");command.Parameters.AddWithValue(listingId);
        await using var reader=await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)?ReadMarketListing(reader).Response:null;
    }

    public Task<MarketPolicyResponse> GetMarketPolicyAsync(Guid playerId,CancellationToken ct)=>GetMarketPolicyForScheduleAsync(playerId,null,null,ct);

    internal async Task<MarketPolicyResponse> GetMarketPolicyForScheduleAsync(Guid playerId,SeasonScheduleSnapshot? schedule,DateTimeOffset? at,CancellationToken ct)
    {
        await using var connection=await dataSource.OpenConnectionAsync(ct);var realm=await ReadMarketRealmAsync(connection,null,at??timeProvider.GetUtcNow(),false,ct,schedule);
        var wallet=await ReadMarketWalletAsync(connection,null,playerId,realm.Schedule,ct);
        var currencies=realm.Policy?.Currencies.Select(value=>new MarketCurrencyResponse(value.Currency,value.OrangePriceCap,value.RedPriceCap)).ToArray()
            ??(realm.Schedule.LegacyAllowed?[new MarketCurrencyResponse("Gold",99999,99999)]:[]);
        return new(realm.State,realm.Season?.SeasonId,realm.Season?.ConfigVersion,realm.Season?.EndsAtUtc,
            realm.Enabled?realm.SharedSlots:8,realm.Enabled?realm.ListingHours:48,realm.Enabled?realm.TaxBasisPoints:1000,realm.Enabled?realm.MinimumFee:1,
            realm.Enabled,wallet,currencies);
    }

    public async Task<IReadOnlyList<MarketListingResponse>> GetOwnMarketListingsAsync(Guid playerId,CancellationToken ct)
    {
        await using var command=dataSource.CreateCommand(MarketSelect+" WHERE l.seller_id=$1 AND l.status='Active' ORDER BY l.created_at,l.listing_id");
        command.Parameters.AddWithValue(playerId);await using var reader=await command.ExecuteReaderAsync(ct);var rows=new List<MarketListingResponse>();
        while(await reader.ReadAsync(ct))rows.Add(ReadMarketListing(reader).Response);
        return rows;
    }

    public async Task<MarketReturnsResponse> GetMarketReturnsAsync(Guid playerId,CancellationToken ct,int limit=32,int offset=0)
    {
        if(limit is <1 or >200 || offset is <0 or >1000000)throw new DomainValidationException("The return page is invalid.");
        var sql=MarketSelect.Replace("FROM market_listings l",",h.return_id,h.created_at,(SELECT count(*) FROM equipments own WHERE own.owner_id=h.player_id AND own.location='Inventory' AND own.season_id IS NOT DISTINCT FROM h.season_id)<50 FROM market_listings l",StringComparison.Ordinal)+
            " JOIN market_return_holds h ON h.listing_id=l.listing_id WHERE h.player_id=$1 AND h.state='Pending' AND e.owner_id=h.player_id AND e.location='MarketReturnPending' ORDER BY h.created_at,h.return_id LIMIT $2 OFFSET $3";
        await using var command=dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(limit+1);command.Parameters.AddWithValue(offset);
        var result=new List<MarketReturnResponse>();await using(var reader=await command.ExecuteReaderAsync(ct))
            while(await reader.ReadAsync(ct))
            {
                var listing=ReadMarketListing(reader).Response;
                result.Add(new(reader.GetGuid(34),listing.ListingId,listing.Equipment!,reader.GetFieldValue<DateTimeOffset>(35),reader.GetBoolean(36)));
            }
        var more=result.Count>limit;if(more)result.RemoveAt(result.Count-1);
        return new(result,more?offset+limit:null);
    }
}
