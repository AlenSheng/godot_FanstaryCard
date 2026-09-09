using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed record EconomyReconciliationReport(
    long NegativeAccountCount,
    long ActiveListingAssetMismatchCount,
    long OrphanMarketListedEquipmentCount,
    long SoldListingMismatchCount,
    long MarketTransactionAmountMismatchCount,
    long LedgerChainMismatchCount)
{
    public long TotalViolationCount => NegativeAccountCount + ActiveListingAssetMismatchCount
        + OrphanMarketListedEquipmentCount + SoldListingMismatchCount
        + MarketTransactionAmountMismatchCount + LedgerChainMismatchCount;

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
                        PARTITION BY player_id, currency
                        ORDER BY created_at, ledger_id) AS previous_balance
                FROM economy_ledger
                WHERE currency <> 'ClassSoul'
            )
            SELECT
                (SELECT count(*) FROM player_wallets WHERE gold < 0 OR diamond < 0)
                + (SELECT count(*) FROM player_materials
                   WHERE warrior_soul < 0 OR priest_soul < 0 OR mage_soul < 0
                      OR guardian_soul < 0 OR equipment_fragments < 0)
                + (SELECT count(*) FROM player_consumables
                   WHERE health_potion_count < 0 OR advanced_bag_count < 0 OR top_bag_count < 0),
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
                 LEFT JOIN equipments AS equipment ON equipment.instance_id = listing.equipment_id
                 WHERE listing.status = 'Sold'
                   AND (txn.transaction_id IS NULL OR equipment.instance_id IS NULL
                        OR equipment.owner_id <> txn.buyer_id OR equipment.location <> 'Inventory')),
                (SELECT count(*) FROM market_transactions
                 WHERE seller_net_gold + fee_gold <> price_gold OR buyer_id = seller_id),
                (SELECT count(*) FROM ledger_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance + delta <> balance_after)
            """;

        await using var command = dataSource.CreateCommand(sql);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Economy reconciliation query returned no result.");

        return new EconomyReconciliationReport(
            reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2),
            reader.GetInt64(3), reader.GetInt64(4), reader.GetInt64(5));
    }
}
