import json
import unittest
from tools.pr13_financial_snapshot import TABLES, from_psql, query


def raw():
    data = {key: [] for _, key, _ in TABLES}
    data.update(checked_at='2026-10-09T01:00:00+00:00', ledger_chain_mismatches=0)
    return data


class FinancialSnapshotTests(unittest.TestCase):
    def test_missing_tables_or_multiple_results_do_not_become_empty_evidence(self):
        for key in ('ledger', 'player_wallets', 'settlement_asset_holds'):
            data = raw(); data.pop(key)
            with self.assertRaises(ValueError):
                from_psql(json.dumps(data), scope='owned-test', phase='after')
        with self.assertRaises(ValueError):
            from_psql(json.dumps(raw()) + '\n' + json.dumps(raw()), scope='owned-test', phase='after')

    def test_reported_zero_cannot_hide_a_raw_chain_difference(self):
        data = raw()
        data['ledger'] = [
            dict(ledger_id='a', player_id='p', currency='Gold', created_at='2026-10-09T00:00:00Z', delta=10, balance_after=10),
            dict(ledger_id='b', player_id='p', currency='Gold', created_at='2026-10-09T00:00:01Z', delta=1, balance_after=9),
        ]
        with self.assertRaises(ValueError):
            from_psql(json.dumps(data), scope='owned-test', phase='after')
        data['ledger_chain_mismatches'] = 1
        parsed = from_psql(json.dumps(data), scope='owned-test', phase='after')
        self.assertEqual(parsed['validation']['verified_chain_mismatches'], 1)
        self.assertFalse(parsed['validation']['financial_acceptance'])

    def test_empty_native_capture_retains_full_table_shape_and_read_only_identity(self):
        parsed = from_psql(json.dumps(raw()), scope='owned-test', phase='before')
        self.assertEqual(parsed['validation']['ledger_rows'], 0)
        self.assertFalse(parsed['auth_tables_exported'])
        self.assertIn('REPEATABLE READ READ ONLY', query())
        self.assertNotIn('auth_sessions', query())
        self.assertNotIn('password', query())
