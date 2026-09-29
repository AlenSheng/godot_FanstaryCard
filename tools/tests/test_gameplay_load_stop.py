"""Real child-process cleanup contract; no network or game server required."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from tools.cloud_load_test import stop_all
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gameplay_load_test import read_owned_statuses
from gameplay_load_validation import workload_snapshot


class StopTests(unittest.TestCase):
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
