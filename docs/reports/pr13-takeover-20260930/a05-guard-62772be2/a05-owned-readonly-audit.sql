BEGIN READ ONLY;
SET LOCAL statement_timeout='5s';
WITH chain AS (
    SELECT *,lag(balance_after) OVER(PARTITION BY player_id,currency ORDER BY created_at,ledger_id) previous
    FROM economy_ledger WHERE currency <> 'ClassSoul'
)
SELECT jsonb_build_object(
    'checked_at',CURRENT_TIMESTAMP,
    'wallets',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM player_wallets t),'[]'::jsonb),
    'consumables',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM player_consumables t),'[]'::jsonb),
    'equipment',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM equipments t),'[]'::jsonb),
    'movements',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM inventory_movements t),'[]'::jsonb),
    'ledger',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM economy_ledger t),'[]'::jsonb),
    'settlements',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM match_settlements t),'[]'::jsonb),
    'holds',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM settlement_asset_holds t),'[]'::jsonb),
    'preparations',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM preparations t),'[]'::jsonb),
    'matches',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM matches t),'[]'::jsonb),
    'match_players',COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM match_players t),'[]'::jsonb),
    'ledger_chain_mismatches',(SELECT count(*) FROM chain WHERE previous IS NOT NULL AND previous+delta<>balance_after),
    'wallet_gold_mismatches',(SELECT count(*) FROM player_wallets w WHERE EXISTS(SELECT 1 FROM economy_ledger e WHERE e.player_id=w.player_id AND e.currency='Gold') AND
        w.gold<>(SELECT e.balance_after FROM economy_ledger e WHERE e.player_id=w.player_id AND e.currency='Gold' ORDER BY e.created_at DESC,e.ledger_id DESC LIMIT 1)),
    'pending_holds',(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'),
    'active_preparations',(SELECT count(*) FROM preparations WHERE status IN ('Active','Queued','Matched')),
    'queued_tickets',(SELECT count(*) FROM match_tickets WHERE status='Queued'),
    'unacknowledged_settlements',(SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NULL),
    'unfinished_matches',(SELECT count(*) FROM matches WHERE status IN ('Starting','Launching','Running')),
    'locked_equipment',(SELECT count(*) FROM equipments WHERE location IN ('PreparationLocked','InMatchEquipped','InMatchBackpack'))
)::text;
ROLLBACK;
