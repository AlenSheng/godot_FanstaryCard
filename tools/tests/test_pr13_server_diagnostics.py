import json
from pathlib import Path
import tempfile
import unittest
from tools.pr13_server_diagnostics import current_window, resource_trend


class ServerDiagnosticTests(unittest.TestCase):
    def row(self, second=1):
        return dict(pid=7, process_started_at='same-owned-process', server_assembly_sha256='a' * 64,
                    observed_at_unix_ms=second * 1000, sequence=second, window_seconds=1, elapsed_seconds=second,
                    rss_bytes=10000 + second * 100, server_cpu_percent=2, managed_allocated_bytes_total=second * 500,
                    managed_heap_bytes=second * 100, gc_collections=[0, 0, 0], dropped_observations=0,
                    durations={'fantasycard.room_actor.command.wait': dict(count=5, p95_ms=12)},
                    counters={'fantasycard.rooms.humans.active': 4})

    def test_owned_partial_write_uses_only_fresh_same_process_and_never_fills_unknown_with_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'owned.jsonl'; file.write_text(json.dumps(self.row()) + '\n{"pid":', encoding='utf8')
            result = current_window(file, 7, now_ms=1001)
            self.assertTrue(result['server_metrics_available']); self.assertEqual(result['actor_wait'], 12)
            for pid, now in [(8, 1001), (7, 6001), (7, 999)]:
                result = current_window(file, pid, now_ms=now)
                self.assertFalse(result['server_metrics_available']); self.assertIsNone(result['actor_wait'])

    def test_actual_histogram_overflow_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'owned.jsonl'; row = self.row(); row['dropped_observations'] = 1
            file.write_text(json.dumps(row), encoding='utf8')
            self.assertFalse(current_window(file, 7, now_ms=1001)['server_metrics_available'])

    def test_slope_preserves_native_allocation_and_gc_evidence_without_claiming_a_leak(self):
        result = resource_trend([self.row(i) for i in range(1, 4)])
        self.assertEqual(result['rss_slope_bytes_per_second'], 100)
        self.assertEqual(result['managed_allocated_bytes_delta'], 1000)
        self.assertFalse(result['leak_proven'])

    def test_os_restart_is_not_a_single_growth_curve(self):
        rows = [self.row(i) for i in range(1, 4)]; rows[2]['pid'] = 8
        with self.assertRaises(ValueError): resource_trend(rows)
