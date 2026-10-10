import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools.cloud.pr13 import render_runtime as runtime


class CloudRenderRuntimeTests(unittest.TestCase):
    def test_unrelated_or_changed_container_identity_refuses_teardown(self):
        container = 'a' * 64
        for identity, labels in [(container, None), (container, {'codex.task': 'unrelated'}),
                                 ('b' * 64, {'codex.task': runtime.LABEL})]:
            with self.subTest(identity=identity, labels=labels):
                response = SimpleNamespace(stdout=json.dumps([{'Id': identity, 'Config': {'Labels': labels}}]))
                with patch.object(runtime, 'docker', return_value=response) as docker:
                    with self.assertRaises(ValueError): runtime.inspect_owned(container)
                    self.assertEqual([('inspect', container)], [call.args for call in docker.call_args_list])

    def test_name_or_nonimmutable_image_cannot_enter_runtime(self):
        with patch.object(runtime, 'docker') as docker:
            with self.assertRaises(ValueError): runtime.inspect_owned('production-server')
            with self.assertRaises(ValueError): runtime.render('latest', Path('.'), Path('absent'), Path('unused'), 'res://tests/a.tscn')
            docker.assert_not_called()

    def test_foreign_or_changed_source_blocks_before_output_and_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; source.mkdir()
            outside = root/'outside'; outside.write_bytes(b'external')
            target = source/'input'; target.write_bytes(b'changed')
            manifest = root/'inputs.json'
            for value in [{'../outside': runtime.sha(outside)}, {'input': hashlib.sha256(b'original').hexdigest()}]:
                with self.subTest(value=value):
                    manifest.write_text(json.dumps(value)); output = root/'output'
                    with patch.object(runtime, 'docker') as docker:
                        with self.assertRaises(ValueError): runtime.render(runtime.BASE_IMAGE, source, manifest, output, 'res://tests/a.tscn')
                        docker.assert_not_called()
                    self.assertFalse(output.exists())
                    self.assertEqual(b'external', outside.read_bytes())
                    self.assertEqual(b'changed', target.read_bytes())

    def test_memory_and_disk_redlines_stop_before_health_or_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for available, free in [(499999999, 300000000), (1000000000, 149999999)]:
                with self.subTest(available=available, free=free), \
                     patch.object(runtime.Path, 'read_text', return_value='MemAvailable: '+str(available//1024)+' kB\n'), \
                     patch.object(runtime.shutil, 'disk_usage', return_value=SimpleNamespace(total=1000000000, free=free)), \
                     patch.object(runtime.urllib.request, 'urlopen') as health:
                    with self.assertRaises(RuntimeError): runtime.guard(root)
                    health.assert_not_called()
            self.assertEqual(2, len((root/'resource-samples.jsonl').read_text().splitlines()))


if __name__ == '__main__':
    unittest.main()
