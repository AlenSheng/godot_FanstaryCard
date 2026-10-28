import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tools.pr13_pg_launch_cases import CONTRACTS, export


class PostgresLaunchEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        source = 'a' * 40
        receipts = root / 'receipts.jsonl'
        rows = []
        run = ET.Element('TestRun')
        ET.SubElement(run, 'Counters', total='3', executed='3', passed='3', notExecuted='0', failed='0')
        contracts = []
        for fault, (selector, ids) in CONTRACTS.items():
            actual = {'durableStatus': 'Running', 'roomCount': 1, 'potionCount': 0, 'startMovementCount': 1}
            if fault == 'mark-running-response-loss':
                actual.update(faultObserved=True, restoredSameRoom=True, restoredSameMatch=True)
            else:
                actual.update(failedStatus='Launching', failedRoomPresent=False, sameRoom=True, sameMatch=True)
            rows.append({'schemaVersion': 1, 'sourceSha': source, 'fault': fault, 'status': 'Passed',
                'scope': 'Disposable PostgreSQL fixture, not LIVE player test', 'actual': actual})
            ET.SubElement(run, 'UnitTestResult', testName='FantasyCard.Server.Tests.Persistence.PostgresLifecycleRecoveryTests.' + selector, outcome='Passed')
            contracts.extend({'id': cid, 'setup_and_injection': fault, 'expected': 'durable postconditions'} for cid in ids)
        receipts.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        trx = root / 'test.trx'
        ET.ElementTree(run).write(trx, encoding='utf-8')
        proof = {'source_sha': source, 'exit_code': 0, 'owned_databases_removed': True}
        plan = {'packages': [{'subtasks': [{'test_cases': contracts}]}]}
        return receipts, trx, proof, plan, rows, run

    def test_actual_fault_points_export_only_their_declared_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            receipts, trx, proof, plan, _, _ = self.fixture(Path(directory))
            rows = export(receipts, trx, proof, plan)
            self.assertEqual({row['case_id'] for row in rows}, {'PR13-A04.3-T01', 'PR13-A04.3-T02', 'PR13-A04.3-T03', 'LOAD-09.2-T01'})
            self.assertTrue(all(row['profiles_executed'] == ['OFFLINE', 'POSTGRES'] for row in rows))

    def test_exit_zero_does_not_hide_skipped_or_failed_assertions(self):
        with tempfile.TemporaryDirectory() as directory:
            receipts, trx, proof, plan, _, tree = self.fixture(Path(directory))
            tree.find('Counters').set('executed', '2')
            tree.find('Counters').set('notExecuted', '1')
            ET.ElementTree(tree).write(trx)
            with self.assertRaises(ValueError):
                export(receipts, trx, proof, plan)
            tree.find('Counters').set('executed', '3')
            tree.find('Counters').set('notExecuted', '0')
            tree.find('UnitTestResult').set('outcome', 'Failed')
            ET.ElementTree(tree).write(trx)
            with self.assertRaises(ValueError):
                export(receipts, trx, proof, plan)

    def test_receipts_need_complete_unique_faults_and_same_source(self):
        with tempfile.TemporaryDirectory() as directory:
            receipts, trx, proof, plan, original, _ = self.fixture(Path(directory))
            foreign = copy.deepcopy(original)
            foreign[0]['sourceSha'] = 'b' * 40
            for rows in [original[:-1], original + [original[0]], foreign]:
                receipts.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
                with self.assertRaises(ValueError):
                    export(receipts, trx, proof, plan)

    def test_duplicate_spend_or_room_contradicts_passed_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipts, trx, proof, plan, original, _ = self.fixture(Path(directory))
            for key in ['roomCount', 'startMovementCount']:
                rows = copy.deepcopy(original)
                rows[0]['actual'][key] = 2
                receipts.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
                with self.assertRaises(ValueError):
                    export(receipts, trx, proof, plan)
            proof['owned_databases_removed'] = False
            with self.assertRaises(ValueError):
                export(receipts, trx, proof, plan)


if __name__ == '__main__':
    unittest.main()
