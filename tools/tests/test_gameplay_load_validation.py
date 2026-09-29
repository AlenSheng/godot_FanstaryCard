"""Offline regression tests; no Godot/server/network dependencies."""
import importlib.util
import math
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'gameplay_load_validation.py'
spec = importlib.util.spec_from_file_location('validation', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Process:
    pid = 7
    def __init__(self, code=None): self.code = code
    def poll(self): return self.code

class ValidationTests(unittest.TestCase):
    def entry(self, code=None, started=1000):
        return {'client_id': 'a', 'process': Process(code), 'started_at_ms': started}
    def status(self, **changes):
        return dict({'client_id':'a','pid':7,'now_unix_ms':10000,'online':True,'room':True}, **changes)
    def snapshot(self, code=None, status=None, now=10000):
        return module.workload_snapshot([self.entry(code)], [self.status() if status is None else status], now)
    def test_alive_fresh_counts(self):
        r=self.snapshot(); self.assertEqual((r['online'],r['in_room']),(1,1)); self.assertFalse(r['workload_failure'])
    def test_exited_success_never_online_or_stale(self):
        r=self.snapshot(0, now=100000); self.assertEqual(r['online'],0); self.assertFalse(r['workload_failure'])
    def test_exited_failure_is_workload_failure(self):
        r=self.snapshot(1); self.assertEqual(r['online'],0); self.assertEqual(r['failed_processes'],['a'])
    def test_stale_running_excluded(self):
        r=self.snapshot(now=40001); self.assertEqual(r['in_room'],0); self.assertEqual(r['stale_clients'],['a'])
    def test_pid_mismatch_excluded(self):
        self.assertEqual(self.snapshot(status=self.status(pid=8))['invalid_clients'],['a'])
    def test_future_timestamp_excluded(self):
        self.assertEqual(self.snapshot(status=self.status(now_unix_ms=10001))['invalid_clients'],['a'])
    def test_missing_uses_actual_launch_time(self):
        r=module.workload_snapshot([self.entry(started=9900)],[],10000)
        self.assertFalse(r['workload_failure'])
        self.assertEqual(module.workload_snapshot([self.entry()],[],31001)['missing_clients'],['a'])
    def test_dead_duplicate_and_unknown_do_not_inflate(self):
        r=module.workload_snapshot([self.entry()],[self.status(),self.status(),self.status(client_id='other')],10000)
        self.assertEqual(r['online'],1)
    def test_stalled_running_is_separate(self):
        self.assertEqual(self.snapshot(status=self.status(last_progress_age_ms=90001))['stalled_clients'],['a'])
    def test_performance_stop_is_not_pass(self):
        r=module.classify_stop('redline:http_p95_over_1500ms'); self.assertEqual(r['exit_code'],2); self.assertFalse(r['passed'])
    def test_generator_stop_is_invalid_not_capacity(self):
        self.assertEqual(module.classify_stop('redline:workload_or_generator_failure')['exit_code'],3)
    def test_workload_invalid_takes_precedence(self):
        self.assertEqual(module.classify_stop('redline:http_p95_over_1500ms', workload_failed=True)['exit_code'],3)
    def test_monitoring_stop_invalid(self):
        self.assertEqual(module.classify_stop('redline:monitoring_unavailable')['exit_code'],3)
    def test_operator_stop_not_pass(self):
        self.assertEqual(module.classify_stop('operator_stop_file')['exit_code'],130)
    def test_smoke_requires_evidence(self):
        self.assertFalse(module.classify_stop('smoke_passed')['passed'])
        self.assertTrue(module.classify_stop('smoke_passed',smoke_verified=True)['passed'])
    def test_empty_window_not_fake_latency(self):
        self.assertEqual(module.aggregate_window([])['http'],{'count':0})
    def test_steady_error_denominator(self):
        rows=[{'path':'/api/v1/auth/login','status':500,'ok':False,'duration_ms':20},
              {'path':'/api/v1/players/me','status':200,'ok':True,'duration_ms':10}]
        r=module.aggregate_window([{'operations':rows}])
        self.assertEqual(r['error_rate'],.5); self.assertEqual(r['steady_error_rate'],0)
        self.assertEqual(r['steady_sample_count'],1)
    def test_compatibility_404_not_silently_dropped(self):
        r=module.aggregate_window([{'operations':[{'path':'/api/v1/market/context','status':404,'ok':False,'duration_ms':1}]}])
        self.assertEqual(r['error_count'],1)
    def test_http_telemetry_is_not_double_counted(self):
        row={'type':'http','path':'/api/v1/players/me','status':200,'ok':True,'duration_ms':1}
        self.assertEqual(module.aggregate_window([{'operations':[row],'telemetry':[row]}])['sample_count'],1)
    def test_invalid_numbers_flagged(self):
        r=module.aggregate_window([{'operations':[{'duration_ms':x} for x in [None, True, -1, math.nan, math.inf]]}])
        self.assertEqual(r['invalid_metric_count'],5)
    def test_percentile_nearest_rank(self):
        self.assertEqual(module.summarize(list(range(1,101)))['p95_ms'],95)
    def test_coordinator_error_never_passes(self):
        self.assertEqual(module.classify_stop('coordinator_error:bad')['exit_code'],3)

if __name__ == '__main__': unittest.main()
