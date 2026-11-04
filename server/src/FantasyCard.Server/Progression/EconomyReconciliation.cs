using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed record EconomyReconciliationReport(
    long NegativeAccountCount,
    long ActiveListingAssetMismatchCount,
    long OrphanMarketListedEquipmentCount,
    long SoldListingMismatchCount,
    long MarketTransactionAmountMismatchCount,
    long LedgerChainMismatchCount,long PendingMarketReturnMismatchCount=0,long CardCopyLedgerMismatchCount=0,long ActivityBudgetMismatchCount=0)
{
    public long TotalViolationCount => NegativeAccountCount + ActiveListingAssetMismatchCount
        + OrphanMarketListedEquipmentCount + SoldListingMismatchCount
        + MarketTransactionAmountMismatchCount + LedgerChainMismatchCount + PendingMarketReturnMismatchCount + CardCopyLedgerMismatchCount + ActivityBudgetMismatchCount;

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
            ), card_copy_chain AS (
                SELECT player_id,card_id,delta,balance_after,
                    lag(balance_after) OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence) AS previous_balance,
                    row_number() OVER(PARTITION BY player_id,card_id ORDER BY ledger_sequence DESC) AS latest
                FROM card_copy_ledger
            ), activity_chain AS (
                SELECT player_id,season_id,event_id,delta,balance_after,
                    lag(balance_after) OVER(PARTITION BY player_id,season_id,event_id ORDER BY ledger_sequence) AS previous_balance,
                    row_number() OVER(PARTITION BY player_id,season_id,event_id ORDER BY ledger_sequence DESC) AS latest
                FROM season_activity_token_ledger
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
                   WHERE e.location='MarketReturnPending' AND h.return_id IS NULL),
                (SELECT count(*) FROM card_copy_chain
                 WHERE previous_balance IS NOT NULL AND previous_balance::bigint+delta<>balance_after)
                + (SELECT count(*) FROM card_copy_chain l
                   LEFT JOIN player_cards c USING(player_id,card_id)
                   LEFT JOIN player_card_reserves r USING(player_id,card_id)
                   WHERE l.latest=1 AND (c.player_id IS NULL OR l.balance_after<>c.copy_count+COALESCE(r.extra_count,0))),
                (SELECT count(*) FROM activity_chain WHERE previous_balance IS NOT NULL AND previous_balance+delta<>balance_after)
                + (SELECT count(*) FROM player_season_activity_accounts a WHERE
                    a.earned-a.spent<>COALESCE((SELECT balance_after FROM activity_chain l WHERE l.player_id=a.player_id AND l.season_id=a.season_id AND l.event_id=a.event_id AND l.latest=1),0)
                    OR a.spent<>(SELECT COALESCE(sum(r.token_cost),0) FROM season_activity_redemptions r WHERE r.player_id=a.player_id AND r.season_id=a.season_id AND r.event_id=a.event_id)
                    OR a.earned<>(SELECT COALESCE(sum(r.credited_tokens),0) FROM season_activity_completions r WHERE r.player_id=a.player_id AND r.season_id=a.season_id AND r.event_id=a.event_id))
                + (SELECT count(*) FROM season_activity_redemptions r LEFT JOIN season_activity_reward_ledger l USING(reward_id)
                   WHERE (r.state='Claimed')<>(l.reward_id IS NOT NULL) OR l.reward_id IS NOT NULL AND
                    (l.player_id<>r.player_id OR l.season_id<>r.season_id OR l.event_id<>r.event_id OR l.reward_kind<>r.reward_kind OR l.reward_amount<>r.reward_amount))
                + (SELECT count(*) FROM season_activity_completions c JOIN season_activity_events e USING(season_id,event_id)
                   WHERE c.occurred_at<e.starts_at OR c.occurred_at>=e.ends_at OR c.config_version<>e.config_version)
            """;

        await using var command = dataSource.CreateCommand(sql);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Economy reconciliation query returned no result.");

        return new EconomyReconciliationReport(
            reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2),
            reader.GetInt64(3), reader.GetInt64(4), reader.GetInt64(5),reader.GetInt64(6),reader.GetInt64(7),reader.GetInt64(8));
    }
}
