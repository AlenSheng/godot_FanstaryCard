"""Complete owned read-only financial evidence for disposable runtime closeout."""
import hashlib
import json

try:
    from .pr13_ledger_attribution import ledger_state
except ImportError:
    from pr13_ledger_attribution import ledger_state


TABLES = (
    ('economy_ledger', 'ledger', 'player_id,currency,created_at,ledger_id'),
    ('player_wallets', 'player_wallets', 'player_id'),
    ('player_materials', 'player_materials', 'player_id'),
    ('inventory_movements', 'inventory_movements', 'movement_id'),
    ('match_settlements', 'match_settlements', 'settlement_id'),
    ('settlement_asset_holds', 'settlement_asset_holds', 'hold_id'),
    ('match_players', 'match_players', 'match_id,player_id'),
    ('equipments', 'equipments', 'instance_id'),
)


def query():
    parts = ["'checked_at',now()", """'ledger_chain_mismatches',(
        SELECT count(*) FROM (
            SELECT delta,balance_after,
                lag(balance_after) OVER(PARTITION BY player_id,currency ORDER BY created_at,ledger_id) AS previous
            FROM economy_ledger WHERE currency<>'ClassSoul'
        ) chain WHERE previous IS NOT NULL AND previous+delta<>balance_after)"""]
    for table, key, order in TABLES:
        parts.append("'" + key + "',COALESCE((SELECT json_agg(row_to_json(item)) FROM "
                     "(SELECT * FROM " + table + " ORDER BY " + order + ") item),'[]'::json)")
    return ("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL statement_timeout='15s'; "
            "SELECT json_build_object(" + ','.join(parts) + "); ROLLBACK;")


def from_psql(stdout, *, scope, phase):
    if not isinstance(scope, str) or not scope or phase not in ('before', 'after', 'verification'):
        raise ValueError('Owned scope and explicit snapshot phase required')
    lines = [line for line in stdout.splitlines() if line.startswith('{')]
    if len(lines) != 1:
        raise ValueError('Exactly one complete database result required')
    result = json.loads(lines[0])
    for _, key, _ in TABLES:
        rows = result.get(key)
        if not isinstance(rows, list) or len(rows) > 100000 or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Complete bounded raw table required: ' + key)
    snapshot = {
        'scope': scope, 'transaction': 'READ ONLY; rollback; no mutation',
        'querySha256': hashlib.sha256(query().encode()).hexdigest(),
        'phase': phase, 'private_raw_table_whitelist': [table for table, _, _ in TABLES],
        'auth_tables_exported': False, 'result': result,
    }
    state = ledger_state(snapshot)
    snapshot['validation'] = {
        'complete_raw_tables': True, 'ledger_rows': len(result['ledger']),
        'verified_chain_mismatches': state['count'],
        'legacy_class_soul_rows': sum(row['currency'] == 'ClassSoul' for row in result['ledger']),
        'financial_acceptance': False,
        'scope': 'Complete observed ledger chains only; wallet reconciliation, legacy ClassSoul and full asset acceptance remain separate',
    }
    return snapshot
