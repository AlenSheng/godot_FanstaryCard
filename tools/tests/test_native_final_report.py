"""Primary terminal JSON failures must reach the actual main verdict."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from tools.tests import test_gameplay_load_finalization as finalization
from tools import gameplay_load_test as runner


class NativeFinalVerdictTests(unittest.TestCase):
    def assert_primary_rejected(self, change):
        fixture = finalization.FinalizationTests()
        code, report = fixture.run_fixture(lambda entry, child: change(entry['report']))
        self.assertEqual(code, 3)
        self.assertEqual(report['result_dimensions']['dimensions']['evidence'], 'Failed')
        self.assertFalse(report['acceptance_passed'])
        self.assertFalse(report['outcome']['passed'])
        self.assertIn('native_final_report_invalid', report['all_triggers'])
        self.assertTrue(report['native_final_report_errors'])
        return report

    def test_only_primary_bad_json_cannot_be_hidden_by_valid_status(self):
        r = self.assert_primary_rejected(lambda p: p.write_bytes(b'{broken'))
        self.assertEqual(r['final_read_errors'], 0)
        self.assertEqual(r['native_final_report_errors'][0]['error_type'], 'JSONDecodeError')

    def test_only_primary_missing_cannot_be_repaired_from_status(self):
        self.assert_primary_rejected(lambda p: p.unlink())

    def test_primary_nonobject_and_invalid_encoding_are_rejected(self):
        for payload in (b'[]', b'null', b'\xff'):
            with self.subTest(payload=payload):
                self.assert_primary_rejected(lambda p: p.write_bytes(payload))

    def test_foreign_primary_identity_is_rejected_after_stop(self):
        def foreign(path):
            r = json.loads(path.read_text()); r['process_epoch'] = 'another-launch'
            path.write_text(json.dumps(r))
        r = self.assert_primary_rejected(foreign)
        self.assertEqual(r['native_final_report_errors'][0]['error'], 'native_final_foreign_context')

    def test_primary_valid_json_but_different_watermark_is_rejected(self):
        def different(path):
            r = json.loads(path.read_text()); r['event_seq_max'] += 1
            path.write_text(json.dumps(r))
        r = self.assert_primary_rejected(different)
        self.assertEqual(r['native_final_report_errors'][0]['fields'], ['event_seq_max'])

    def test_primary_hidden_business_error_is_preserved_and_disagreement_invalid(self):
        def hidden(path):
            r = json.loads(path.read_text()); r.update(ok=False, outcome='failed', errors=[{'message':'primary-only-business-failure'}])
            path.write_text(json.dumps(r))
        r = self.assert_primary_rejected(hidden)
        self.assertIn('final_business_failure', r['all_triggers'])

    def test_primary_counter_schema_is_not_coerced(self):
        for value in (True, -1, '0'):
            with self.subTest(value=value):
                def invalid(path):
                    r = json.loads(path.read_text()); r['audit_lost_count'] = value
                    path.write_text(json.dumps(r))
                self.assert_primary_rejected(invalid)

    def test_bounded_reader_checks_size_before_decoding(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'owned.json'; path.write_bytes(b'{' + b' ' * 100)
            entry = dict(client_id='c', run_id='r', process_epoch='p', report=path, process=SimpleNamespace(pid=4))
            valid, errors = runner.read_native_final_reports([entry], [], max_bytes=16)
            self.assertEqual(valid, [])
            self.assertEqual(errors[0]['error'], 'native_final_report_too_large')
            self.assertEqual(errors[0]['limit_bytes'], 16)


if __name__ == '__main__':
    unittest.main()
