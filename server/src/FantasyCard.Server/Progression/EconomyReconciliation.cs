using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed record EconomyReconciliationReport(
    long NegativeAccountCount,
    long ActiveListingAssetMismatchCount,
    long OrphanMarketListedEquipmentCount,
    long SoldListingMismatchCount,
    long MarketTransactionAmountMismatchCount,
    long LedgerChainMismatchCount,long PendingMarketReturnMismatchCount=0)
{
    public long TotalViolationCount => NegativeAccountCount + ActiveListingAssetMismatchCount
        + OrphanMarketListedEquipmentCount + SoldListingMismatchCount
        + MarketTransactionAmountMismatchCount + LedgerChainMismatchCount + PendingMarketReturnMismatchCount;

    public bool IsHealthy => TotalViolationCount == 0;
}

public sealed class EconomyReconciliationRepository(NpgsqlDataSource dataSource)
{
    public async Task<EconomyReconciliationReport> InspectAsync(CancellationToken cancellationToken)
    {
        const string sql =
            """
            WITH ledger_chain AS (
                SELECT player_id, currency, delta, balance_after,
                    lag(balance_after) OVER (
                        PARTITION BY player_id,currency,
                            CASE WHEN currency IN ('Gold','EquipmentFragments','ChallengeMarks','BlueprintMarks','OrangeBlueprintMarks') THEN season_id END
                        ORDER BY created_at,ledger_sequence,ledger_id) AS previous_balance
                FROM economy_ledger
                WHERE currency <> 'ClassSoul'
            )
            SELECT
                (SELECT count(*) FROM player_wallets WHERE gold < 0 OR diamond < 0)
                + (SELECT count(*) FROM player_materials
                   WHERE warrior_soul < 0 OR priest_soul < 0 OR mage_soul < 0
                      OR guardian_soul < 0 OR equipment_fragments < 0)
                + (SELECT count(*) FROM player_consumables
                   WHERE health_potion_count < 0 OR advanced_bag_count < 0 OR top_bag_count < 0)
                + (SELECT count(*) FROM player_season_wallets WHERE gold<0 OR equipment_fragments<0 OR challenge_marks<0 OR blueprint_marks<0 OR orange_blueprint_marks<0),
                (SELECT count(*)
                 FROM market_listings AS listing
                 LEFT JOIN equipments AS equipment ON equipment.instance_id = listing.equipment_id
                 WHERE listing.status = 'Active'
                   AND (equipment.instance_id IS NULL OR equipment.owner_id <> listing.seller_id
                        OR equipment.location <> 'MarketListed')),
                (SELECT count(*)
                 FROM equipments AS equipment
                 LEFT JOIN market_listings AS listing
                   ON listing.equipment_id = equipment.instance_id AND listing.status = 'Active'
                 WHERE equipment.location = 'MarketListed' AND listing.listing_id IS NULL),
                (SELECT count(*)
                 FROM market_listings AS listing
                 LEFT JOIN market_transactions AS txn ON txn.listing_id = listing.listing_id
                 WHERE listing.status = 'Sold'
                   AND (txn.transaction_id IS NULL OR txn.seller_id <> listing.seller_id
                        OR txn.currency<>listing.currency OR COALESCE(txn.price,txn.price_gold)<>COALESCE(listing.price,listing.price_gold)
                        OR (txn.price IS NOT NULL AND txn.season_id IS DISTINCT FROM listing.season_id))),
                (SELECT count(*) FROM market_transactions
                 WHERE COALESCE(seller_net,seller_net_gold)+COALESCE(fee,fee_gold)<>COALESCE(price,price_gold) OR buyer_id=seller_id),
                (SELECT count(*) FROM ledger_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance + delta <> balance_after),
                (SELECT count(*) FROM market_return_holds h LEFT JOIN equipments e ON e.instance_id=h.equipment_id
                 WHERE h.state='Pending' AND (e.instance_id IS NULL OR e.owner_id<>h.player_id OR e.location<>'MarketReturnPending'
                    OR e.season_id IS DISTINCT FROM h.season_id))
                + (SELECT count(*) FROM equipments e LEFT JOIN market_return_holds h ON h.equipment_id=e.instance_id AND h.state='Pending'
                   WHERE e.location='MarketReturnPending' AND h.return_id IS NULL)
            """;

        await using var command = dataSource.CreateCommand(sql);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Economy reconciliation query returned no result.");

        return new EconomyReconciliationReport(
            reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2),
            reader.GetInt64(3), reader.GetInt64(4), reader.GetInt64(5),reader.GetInt64(6));
    }
}
