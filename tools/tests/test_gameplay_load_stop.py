"""Real child-process cleanup contract; no network or game server required."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from tools.cloud_load_test import stop_all
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gameplay_load_test import read_owned_statuses
from gameplay_load_test import metrics, QUERIES, completed_smoke
from gameplay_load_validation import workload_snapshot
from tools.cloud_load_test import health_probe


class StopTests(unittest.TestCase):
    def test_health_timeout_is_one_failed_observation_without_fallback(self):
        from unittest.mock import patch
        with patch('tools.cloud_load_test.subprocess.run',side_effect=subprocess.TimeoutExpired('curl',5.5)) as call, patch('tools.cloud_load_test.urllib.request.urlopen') as fallback:
            result=health_probe('https://example.invalid',5)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'],'TimeoutExpired')
        self.assertEqual(call.call_args.kwargs['timeout'],5.5)
        fallback.assert_not_called()

    def test_multi_account_smoke_waits_for_every_account(self):
        import json
        class Child:
            def __init__(self, code): self.returncode=code
            def poll(self): return self.returncode
        with tempfile.TemporaryDirectory() as directory:
            entries=[]
            for index in range(10):
                report=Path(directory)/str(index)
                report.write_text(json.dumps({'ok':True,'cycles_completed':3}),encoding='utf8')
                entries.append({'process':Child(0),'report':report})
            self.assertIsNone(completed_smoke(entries[:1],10,3))
            entries[-1]['process'].returncode=None
            self.assertIsNone(completed_smoke(entries,10,3))
            entries[-1]['process'].returncode=0
            self.assertTrue(completed_smoke(entries,10,3))
            entries[-1]['report'].write_text(json.dumps({'ok':True,'cycles_completed':2}),encoding='utf8')
            self.assertFalse(completed_smoke(entries,10,3))

    def test_monitoring_uses_one_snapshot_and_preserves_unknowns(self):
        import io, json
        from unittest.mock import patch
        rows=[{'metric':{'pr13_metric':key},'value':[1,'3']} for key in QUERIES if key!='actor_wait']
        rows.append({'metric':{'pr13_metric':'cpu'},'value':[1,'4']})
        with patch('gameplay_load_test.urllib.request.urlopen',return_value=io.StringIO(json.dumps({'data':{'result':rows}}))) as request:
            values=metrics('http://127.0.0.1:1')
        self.assertEqual(request.call_count,1)
        self.assertEqual(request.call_args.kwargs['timeout'],3)
        self.assertIsNone(values['actor_wait'])
        self.assertIsNone(values['cpu'])
        self.assertEqual(values['server_humans_in_room'],3)

    def test_monitoring_failure_cannot_report_zero_resources(self):
        from unittest.mock import patch
        with patch('gameplay_load_test.urllib.request.urlopen',side_effect=TimeoutError()):
            self.assertEqual(metrics('http://127.0.0.1:1'),dict.fromkeys(QUERIES))

    def test_atomic_status_gap_uses_prior_owned_sample(self):
        class Running:
            pid = 42
            def poll(self): return None
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'client.json'
            status_path = Path(str(report) + '.status.json')
            status = {'client_id':'client','pid':42,'run_id':'run','process_epoch':'epoch',
                      'now_unix_ms':10000,'online':True,'room':True,'last_progress_age_ms':0}
            import json
            status_path.write_text(json.dumps(status),encoding='utf-8')
            entry = {'client_id':'client','process':Running(),'report':report,
                     'run_id':'run','process_epoch':'epoch','started_at_ms':1000}
            cache = {}
            self.assertEqual(read_owned_statuses([entry],cache),([status],0))
            status_path.unlink()
            self.assertEqual(read_owned_statuses([entry],cache),([status],0))
            self.assertEqual(workload_snapshot([entry],[status],41001)['stale_clients'],['client'])

    def test_forced_child_is_reported_and_reaped(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            with tempfile.TemporaryDirectory() as directory:
                stop = Path(directory) / 'STOP'
                forced = stop_all([{'process': child}], stop, grace_seconds=0)
                self.assertTrue(stop.exists())
                self.assertEqual(forced, [child.pid])
                self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
