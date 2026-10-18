"""OFFLINE guard/control fixtures; no live load or capacity claim."""
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from tools.pr13_resource_policy import disk_causes
from tools.gameplay_load_validation import workload_profile_identity
from tools.tests import test_gameplay_load_sampling_contract as sampling_fixtures
coordinator = sampling_fixtures.coordinator


class CapacityGuardContractTests(unittest.TestCase):
    def test_same_actual_monitor_value_stops_legacy_but_explicit_revision_runs(self):
        fixture = sampling_fixtures.CoordinatorSamplingContractTests()
        _, legacy = fixture.run_fixture(resource_changes={'disk_available': 14})
        _, revised = fixture.run_fixture(resource_changes={'disk_available': 14}, disk_floor=5)
        self.assertIn('disk_available_redline', legacy['all_triggers'])
        self.assertEqual(legacy['load_contract']['minimum_cloud_disk_percent'], 15)
        self.assertEqual(revised['stop_reason'], 'duration_limit')
        self.assertNotIn('disk_available_redline', revised['all_triggers'])
        self.assertEqual(revised['load_contract']['minimum_cloud_disk_percent'], 5)
        self.assertTrue(all(row['resources']['disk_available'] == 14 for row in revised['samples']))
        self.assertEqual(revised['load_contract']['target_online'], legacy['load_contract']['target_online'])
        self.assertEqual(revised['load_contract']['minimum_window'], 600)
        self.assertEqual(revised['load_contract']['minimum_coverage'], .95)

    def test_explicit_revision_still_stops_below_five_percent(self):
        _, report = sampling_fixtures.CoordinatorSamplingContractTests().run_fixture(resource_changes={'disk_available': 4.99}, disk_floor=5)
        self.assertIn('disk_available_redline', report['all_triggers'])
        self.assertFalse(report['load_window_verified'])
        self.assertEqual(disk_causes({'disk_available': 5}, 5), [])

    def test_invalid_monitoring_cannot_be_a_safe_disk_reading(self):
        for value in [None, True, -1, 101, float('nan'), float('inf')]:
            with self.subTest(value=value):
                self.assertEqual(disk_causes({'disk_available': value}, 5), ['monitoring_unavailable'])

    def test_invalid_explicit_floor_is_rejected_before_network_or_launch(self):
        for value in ['4.99', '0', '101', 'nan', 'inf']:
            argv = ['gameplay_load_test.py', '--godot', sys.executable,
                    '--minimum-cloud-disk-percent', value]
            with self.subTest(value=value), patch.object(sys, 'argv', argv), \
                    patch.object(coordinator, 'health_probe') as probe, \
                    patch.object(coordinator.subprocess, 'Popen') as launch, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    coordinator.main()
                self.assertEqual(error.exception.code, 2)
                probe.assert_not_called()
                launch.assert_not_called()

    def test_revised_guard_has_a_different_complete_profile_identity(self):
        source = {'tools/gameplay_load_test.py': 'a' * 64}
        legacy = workload_profile_identity({'target_online': 50, 'minimum_cloud_disk_percent': 15}, source)
        revised = workload_profile_identity({'target_online': 50, 'minimum_cloud_disk_percent': 5}, source)
        self.assertTrue(legacy['qualified'] and revised['qualified'])
        self.assertNotEqual(legacy['workload_profile_id'], revised['workload_profile_id'])

    def test_rejected_memory_admission_keeps_the_exact_prelaunch_measurement(self):
        _, report = sampling_fixtures.CoordinatorSamplingContractTests().run_fixture(memory_floor=3 * 1024 ** 3)
        self.assertEqual(report['stop_reason'], 'invalid_evidence:generator_memory_low_before_launch')
        self.assertEqual(report['clients'], 0)
        self.assertEqual(report['launch_receipts'], [])
        receipt = report['launch_admission_rejection']
        self.assertFalse(receipt['process_started'])
        self.assertEqual(receipt['available_bytes'], 3 * 1024 ** 3)
        self.assertEqual(receipt['required_bytes'], 3 * 1024 ** 3 + 256 * 1024 ** 2)
        self.assertEqual(receipt['next_client_number'], 1)
        self.assertEqual(receipt['scheduled_group'], 1)
        self.assertIn('at rejected admission', receipt['measurement_source'])
        self.assertFalse(report['result_dimensions']['all_applicable_passed'])
