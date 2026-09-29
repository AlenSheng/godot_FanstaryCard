"""Real child-process cleanup contract; no network or game server required."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from tools.cloud_load_test import stop_all


class StopTests(unittest.TestCase):
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
