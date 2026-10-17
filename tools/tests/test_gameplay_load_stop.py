"""Real child-process cleanup contract; no network or game server required."""
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from tools.cloud_load_test import stop_all
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gameplay_load_test import read_owned_statuses
from gameplay_load_test import metrics, QUERIES, completed_smoke
from gameplay_load_validation import workload_snapshot
from tools.cloud_load_test import health_probe


class StopTests(unittest.TestCase):
    def _owned_report_path(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        report = Path(directory.name) / "client.json"
        # Size validation now precedes the injected read error. Create the
        # actual owned file so each test reaches its intended read branch.
        Path(str(report) + ".status.json").write_text("{}", encoding="utf8")
        return report

    def test_receipt_clock_preserves_cache_age_across_wall_clock_jump(self):
        import json
        class Running:
            pid=42
            def poll(self):return None
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'client.json';path=Path(str(report)+'.status.json')
            row=dict(client_id='client',pid=42,run_id='run',process_epoch='epoch',status_seq=1,
                     now_unix_ms=10000,online=True,room=True,last_progress_age_ms=0)
            entry=dict(client_id='client',process=Running(),report=report,run_id='run',process_epoch='epoch',
                       started_at_ms=9900,started_at_monotonic_ms=9000)
            cache={};path.write_text(json.dumps(row),encoding='utf8')
            first,_=read_owned_statuses([entry],cache,10000)
            again,_=read_owned_statuses([entry],cache,41001)
            self.assertEqual(again[0]['_received_at_monotonic_ms'],10000)
            result=workload_snapshot([entry],again,0,now_monotonic_ms=41001)
            self.assertEqual(result['stale_clients'],['client'])
            self.assertEqual(result['online'],0)
            path.unlink()
            cached,_=read_owned_statuses([entry],cache,42000)
            self.assertEqual(cached[0]['_received_at_monotonic_ms'],10000)

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
            # Windows replacement can remove the destination between an exists
            # check and opening it. Preserve the prior owned observation only.
            from unittest.mock import patch
            with patch('gameplay_load_test.Path.read_text',side_effect=FileNotFoundError()):
                self.assertEqual(read_owned_statuses([entry],cache),([status],0))
            status_path.unlink()
            self.assertEqual(read_owned_statuses([entry],cache),([status],0))
            self.assertEqual(workload_snapshot([entry],[status],41001)['stale_clients'],['client'])

    def test_status_read_recovers_io_with_new_heartbeat_and_diagnostic(self):
        import json
        from unittest.mock import patch
        entry = {'client_id':'client','report':self._owned_report_path(),'process':SimpleNamespace(pid=42)}
        previous = {'client_id':'client','pid':42,'status_seq':1,'_received_at_monotonic_ms':10000}
        current = {'client_id':'client','pid':42,'status_seq':2}
        failures = []
        with patch('gameplay_load_test.Path.read_text', side_effect=[PermissionError(13, 'sharing'), json.dumps(current)]), \
                patch('gameplay_load_test.time.sleep') as pause:
            owned, invalid = read_owned_statuses([entry], {'client':previous}, 20000, read_errors=failures)
        self.assertEqual(invalid, 0)
        self.assertEqual(owned, [dict(current, _received_at_monotonic_ms=20000)])
        self.assertEqual(failures[0]['error'], 'PermissionError')
        self.assertEqual(failures[0]['errno'], 13)
        self.assertEqual(failures[0]['disposition'], 'recovered_read')
        pause.assert_called_once_with(.01)

    def test_status_permanent_io_failure_does_not_reuse_cache(self):
        from unittest.mock import patch
        entry = {'client_id':'client','report':self._owned_report_path()}
        failures = []
        with patch('gameplay_load_test.Path.read_text', side_effect=PermissionError(13, 'denied')) as read, \
                patch('gameplay_load_test.time.sleep'):
            owned, invalid = read_owned_statuses([entry], {'client':{'client_id':'client'}}, read_errors=failures)
        self.assertEqual((owned, invalid), ([], 1))
        self.assertEqual(read.call_count, 3)
        self.assertEqual([row['attempt'] for row in failures], [1, 2, 3])
        self.assertTrue(all(row['disposition']=='invalid_file' for row in failures))

    def test_status_corruption_is_not_retried_or_hidden(self):
        from unittest.mock import patch
        entry = {'client_id':'client','report':self._owned_report_path()}
        for data, error_name in [('{"client_id":', 'JSONDecodeError'),
                (UnicodeDecodeError('utf8', b'\xff', 0, 1, 'invalid'), 'UnicodeDecodeError')]:
            with self.subTest(error=error_name):
                failures = []
                kwargs = {'side_effect':data} if isinstance(data, Exception) else {'return_value':data}
                with patch('gameplay_load_test.Path.read_text', **kwargs) as read, \
                        patch('gameplay_load_test.time.sleep') as pause:
                    owned, invalid = read_owned_statuses([entry], {'client':{'client_id':'client'}}, read_errors=failures)
                self.assertEqual((owned, invalid), ([], 1))
                self.assertEqual(failures[0]['error'], error_name)
                read.assert_called_once()
                pause.assert_not_called()

    def test_recovered_io_does_not_accept_foreign_status(self):
        import json
        from unittest.mock import patch
        entry = {'client_id':'client','report':self._owned_report_path(),'run_id':'owned','process':SimpleNamespace(pid=42)}
        failures = []
        with patch('gameplay_load_test.Path.read_text', side_effect=[OSError(32, 'sharing'),
                json.dumps({'client_id':'client','pid':42,'run_id':'foreign','status_seq':2})]), \
                patch('gameplay_load_test.time.sleep'):
            owned, invalid = read_owned_statuses([entry], read_errors=failures)
        self.assertEqual((owned, invalid), ([], 1))
        self.assertEqual(failures[0]['disposition'], 'recovered_read')

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
