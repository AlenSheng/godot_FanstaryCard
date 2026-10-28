import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from tools.cloud_load_test import stop_all


class StopAllMarkerTests(unittest.TestCase):
    def _child(self, marker, receipt):
        code = (
            "import json,os,pathlib,sys,time;"
            "marker=pathlib.Path(sys.argv[1]);receipt=pathlib.Path(sys.argv[2]);"
            "deadline=time.monotonic()+5\n"
            "while not marker.is_file() and time.monotonic()<deadline:time.sleep(.01)\n"
            "receipt.write_text(json.dumps({'pid':os.getpid(),'observed':marker.is_file()}))\n"
        )
        return subprocess.Popen(
            [sys.executable, "-c", code, str(marker), str(receipt)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0),
        )

    def _exercise(self, initial=None, readonly=False):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "STOP"
            receipt = Path(folder) / "observed.json"
            if initial is not None:
                marker.write_bytes(initial)
                if readonly:
                    marker.chmod(stat.S_IREAD)
            child = self._child(marker, receipt)
            try:
                self.assertEqual(stop_all([{"process": child}], marker, grace_seconds=2), [])
                self.assertEqual(child.returncode, 0)
                self.assertEqual(json.loads(receipt.read_bytes()), {"pid": child.pid, "observed": True})
                self.assertEqual(marker.read_bytes(), b"stop" if initial is None else initial)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=3)
                if marker.exists():
                    marker.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_missing_marker_is_created_and_real_child_exits(self):
        self._exercise()

    def test_external_existing_marker_content_is_preserved(self):
        self._exercise(b"external controller reason\n")

    def test_readonly_external_marker_needs_no_write_access(self):
        self._exercise(b"owned external readonly STOP\n", readonly=True)

    def test_directory_marker_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "STOP"
            marker.mkdir()
            with self.assertRaises((OSError, ValueError)):
                stop_all([], marker, grace_seconds=0)


if __name__ == "__main__":
    unittest.main()
