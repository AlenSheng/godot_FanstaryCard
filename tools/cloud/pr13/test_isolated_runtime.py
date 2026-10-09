"""Reject wrong ownership before any Docker removal or database operation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pr13_isolated_runtime', Path(__file__).with_name('isolated_runtime.py'))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class OwnershipTests(unittest.TestCase):
    def test_cpu_quota_removal_requires_owned_bypass_before_mutation(self):
        with patch.object(runtime, 'docker') as docker:
            with self.assertRaises(ValueError):
                runtime.start(unrestricted_cpu=True)
            docker.assert_not_called()

    def test_database_override_requires_owned_bypass_before_mutation(self):
        for bypass, maximum in [(False, 256), (True, 99), (True, 513), (True, True), (True, 256.5)]:
            with self.subTest(bypass=bypass, maximum=maximum), patch.object(runtime, 'docker') as docker:
                with self.assertRaises(ValueError):
                    runtime.start(owned_test_bypass=bypass, database_max_connections=maximum)
                docker.assert_not_called()

    def test_exact_identity_and_session_are_both_required(self):
        record = {'containers': {'server': 'owned-id'}}
        for info in [
            {'Id': 'other-id', 'Config': {'Labels': {'codex.session': runtime.LABEL}}},
            {'Id': 'owned-id', 'Config': {'Labels': {'codex.session': 'other-session'}}},
        ]:
            with self.subTest(info=info), patch.object(runtime, 'inspect', return_value=info):
                with self.assertRaises(ValueError):
                    runtime.owned(record, 'server')

    def test_mismatch_cannot_remove_any_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'evidence').mkdir()
            record = {'containers': {'server': 'owned-id'}}
            with patch.object(runtime, 'BASE', root), patch.object(runtime, 'owned', side_effect=ValueError('identity differs')), patch.object(runtime, 'docker') as docker:
                result = runtime.stop(record)
                self.assertEqual(result, {'server': 'ValueError'})
                docker.assert_not_called()

    def test_existing_immutable_runtime_does_not_launch_or_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'evidence').mkdir()
            (root / 'evidence/live-runtime.json').write_text('{}')
            with patch.object(runtime, 'BASE', root), patch.object(runtime, 'docker') as docker:
                with self.assertRaises(ValueError):
                    runtime.start()
                docker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
