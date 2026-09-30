"""Offline regression tests; no Godot/server/network dependencies."""
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
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
        self.assertFalse(module.classify_stop('duration_limit')['passed'])
        self.assertEqual(module.classify_stop('duration_limit',load_verified=True)['classification'], 'load_window_completed')
        self.assertEqual(module.classify_stop('duration_limit',load_verified=True,workload_failed=True)['exit_code'],3)
        self.assertEqual(module.classify_stop('invalid_evidence:generator_memory_low')['exit_code'],3)
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
    def test_attempts_have_separate_denominator_from_logical_requests(self):
        final={'type':'http','path':'/api/v1/players/me','status':200,'ok':True,'duration_ms':14}
        attempts=[{'type':'http_attempt','status':503,'result':'http_error','duration_ms':5},
                  {'type':'http_attempt','status':200,'result':'success','duration_ms':4}]
        result=module.aggregate_window([{'operations':[final],'telemetry':[final,*attempts]}])
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(result['all_attempt_count'],2)
        self.assertEqual(result['attempt_result_counts'],{'http_error':1,'success':1})
    def test_client_cancellation_is_measured_without_service_redline(self):
        result=module.aggregate_window([{'operations':[
            {'type':'http','path':'/api/v1/client-info','status':0,'ok':False,'result':'cancelled','duration_ms':3000},
            {'type':'http','path':'/api/v1/bootstrap','status':200,'ok':True,'result':'success','duration_ms':100}]}])
        self.assertEqual(result['logical_request_count'],2)
        self.assertEqual(result['cancelled_count'],1)
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(result['error_rate'],0)
        self.assertEqual(result['http']['p95_ms'],100)
        self.assertEqual(result['cancelled_http']['p95_ms'],3000)
    def test_invalid_numbers_flagged(self):
        r=module.aggregate_window([{'operations':[{'duration_ms':x} for x in [None, True, -1, math.nan, math.inf]]}])
        self.assertEqual(r['invalid_metric_count'],5)
    def test_non_string_telemetry_types_are_invalid_evidence(self):
        valid = {'type':'http','path':'/api/v1/players/me','status':500,
                 'ok':False,'duration_ms':5}
        for kind in ([], {}, None, True, 1):
            with self.subTest(kind=kind):
                result = module.aggregate_window([{'operations':[valid],
                    'telemetry':[{'type':kind,'duration_ms':1}]}])
                self.assertEqual(result['invalid_schema_count'],1)
                self.assertEqual(result['sample_count'],1)
                self.assertEqual(result['error_count'],1)
                self.assertEqual(result['http']['min_ms'],5)
                self.assertEqual(module.classify_stop(
                    'invalid_evidence:invalid_telemetry')['exit_code'],3)
    def test_json_integer_outside_float_range_is_invalid_not_zero_latency(self):
        huge = json.loads('1' + '0' * 400)
        result = module.aggregate_window([{'operations':[{
            'duration_ms':huge,'status':500,'ok':False}]}])
        self.assertEqual(result['invalid_duration_count'],1)
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(result['error_count'],1)
        self.assertEqual(result['http'],{'count':0})
        for status in (self.status(now_unix_ms=huge),
                       self.status(last_progress_age_ms=huge)):
            with self.subTest(status=status):
                result = self.snapshot(status=status)
                self.assertTrue(result['workload_failure'])
                self.assertGreater(result['invalid_schema_count'],0)
        self.assertTrue(module.workload_snapshot(
            [self.entry()],[],huge)['workload_failure'])
    def test_owned_json_file_schema_failure_reaches_explicit_invalid_decision(self):
        tools = str(PATH.parent)
        sys.path.insert(0,tools)
        try:
            from gameplay_load_test import read_owned_statuses
        finally:
            sys.path.remove(tools)
        with tempfile.TemporaryDirectory() as directory:
            entry=self.entry()
            entry.update(report=Path(directory)/'client.json',run_id='r',process_epoch='e')
            for kind,duration in (([],1),({},1),('http',10**400)):
                with self.subTest(kind=kind):
                    event=dict(type=kind,duration_ms=duration,status=500,ok=False,
                               run_id='r',client_id='a',process_epoch='e',event_seq=1)
                    status=self.status(run_id='r',process_epoch='e',status_seq=1,
                        event_seq_max=1,telemetry=[event],
                        operations=[event] if kind=='http' else [])
                    Path(str(entry['report'])+'.status.json').write_text(json.dumps(status))
                    rows,invalid=read_owned_statuses([entry],{},require_files=True)
                    windows,lost=module.new_events(rows,{})
                    result=module.aggregate_window(windows)
                    self.assertEqual((invalid,lost),(0,0))
                    self.assertEqual(result['invalid_metric_count'],1)
                    decision=module.classify_stop('invalid_evidence:invalid_telemetry')
                    self.assertEqual(decision['classification'],'invalid_workload_or_evidence')
                    self.assertEqual(decision['exit_code'],3)
                    self.assertFalse(decision['passed'])
    def test_percentile_nearest_rank(self):
        self.assertEqual(module.summarize(list(range(1,101)))['p95_ms'],95)
    def test_coordinator_error_never_passes(self):
        self.assertEqual(module.classify_stop('coordinator_error:bad')['exit_code'],3)
    def test_malformed_status_does_not_crash_sampler(self):
        for bad in (None, [], {'client_id':'a','pid':7,'now_unix_ms':10000,
                              'last_progress_age_ms':'stalled'}):
            result=module.workload_snapshot([self.entry()],[bad],10000)
            self.assertTrue(result['workload_failure'])
            self.assertGreater(result['invalid_schema_count'],0)
        self.assertTrue(module.workload_snapshot([None],[],10000)['workload_failure'])
        self.assertTrue(module.workload_snapshot([self.entry()],[],"bad-time")['workload_failure'])
        self.assertGreater(module.aggregate_window(None)['invalid_schema_count'],0)
    def test_offline_room_is_not_active(self):
        result=self.snapshot(status=self.status(online=False))
        self.assertEqual(result['room_state_clients'],1)
        self.assertEqual(result['active_in_room'],0)
        self.assertEqual(result['in_room'],0)
    def test_bad_http_status_and_duration_keep_attempt(self):
        result=module.aggregate_window([{'operations':[
            {'path':'/api/v1/players/me','status':'oops','ok':True,'duration_ms':1},
            {'path':'/api/v1/players/me','status':500,'ok':False,'duration_ms':math.nan}]}])
        self.assertEqual(result['sample_count'],2)
        self.assertEqual(result['error_count'],2)
        self.assertEqual(result['http']['count'],1)
        self.assertGreaterEqual(result['invalid_metric_count'],2)
    def test_settlement_bootstrap_has_phase_and_legacy_comparison(self):
        result=module.aggregate_window([{'operations':[
            {'path':'/api/v1/bootstrap','label':'settlement_poll','phase':'settlement',
             'status':200,'ok':True,'duration_ms':5}]}])
        self.assertEqual(result['steady_sample_count'],0)
        self.assertEqual(result['phase_http']['settlement']['count'],1)
    def test_event_sequence_handles_same_millisecond_and_detects_loss(self):
        def event(seq):
            return {'type':'http','run_id':'r','client_id':'a','process_epoch':'e',
                    'event_seq':seq,'at_unix_ms':10000,'duration_ms':1,'status':200,'ok':True}
        status={'run_id':'r','client_id':'a','process_epoch':'e','event_seq_max':3,
                'telemetry':[event(1),event(3)],'operations':[event(1),event(3)]}
        seen={}
        rows,lost=module.new_events([status],seen)
        self.assertEqual((lost,len(rows[0]['operations'])),(1,2))
        self.assertEqual(seen[('a','e')],3)
        rows,lost=module.new_events([status],seen)
        self.assertEqual((lost,len(rows[0]['operations'])),(0,0))
    def test_owned_status_rejects_other_launch_and_preserves_exit_history(self):
        entry=self.entry(code=0)
        entry.update(run_id='r',process_epoch='e')
        good=self.status(run_id='r',process_epoch='e')
        result,invalid=module.owned_statuses([entry],[good,self.status(run_id='other',process_epoch='e')])
        self.assertEqual(result,[good])
        self.assertEqual(invalid,1)
        self.assertEqual(module.owned_statuses([entry],[{'client_id':[]}])[1],1)

    def test_operation_copy_cannot_replace_the_owned_telemetry_sample(self):
        event = dict(type='http', run_id='r', client_id='a', process_epoch='e',
                     event_seq=1, at_unix_ms=10000, duration_ms=1, status=500, ok=False)
        forged = dict(event, run_id='external', status=200, ok=True)
        status = dict(run_id='r', client_id='a', process_epoch='e', event_seq_max=1,
                      telemetry=[event], operations=[forged])
        windows, lost = module.new_events([status], {})
        self.assertGreater(lost, 0)
        self.assertEqual(windows[0]['operations'], [])
    def test_real_child_exit_is_not_counted_online(self):
        child=subprocess.Popen([sys.executable,'-c','raise SystemExit(7)'])
        try:
            self.assertEqual(child.wait(timeout=10),7)
            entry={'client_id':'a','process':child,'started_at_ms':1000}
            result=module.workload_snapshot([entry],[self.status(pid=child.pid)],10000)
            self.assertEqual(result['online'],0)
            self.assertEqual(result['failed_processes'],['a'])
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)

if __name__ == '__main__': unittest.main()
