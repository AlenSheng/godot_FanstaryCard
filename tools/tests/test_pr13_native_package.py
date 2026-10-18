"""Offline direct Native package, immutable source and capability controls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pr13_native_package import SCHEMA,verify_package,launch_command,package_environment,package_unchanged,runtime_capabilities

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class NativePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.project=self.root/'project';self.project.mkdir();(self.project/'tests').mkdir()
        self.source=self.project/'tests/gameplay_load_client.gd';self.source.write_bytes(b'complete fixture')
        self.entry=self.project/'tests/private_entry.gd';self.entry.write_bytes(b'private full entry')
        self.exe=self.root/'FullNative.exe';self.exe.write_bytes(b'MZ synthetic only');self.pck=self.exe.with_suffix('.pck');self.pck.write_bytes(b'synthetic encrypted payload')
        self.contract_path=self.root/'contract.json';self.contract={'schema':SCHEMA,'entry_scene':'res://tests/gameplay_load_client.tscn',
            'runtime_features':{'debug_features':True,'max_fps':0,'physics_ticks':60},
            'source_inputs':{'client/tests/gameplay_load_client.gd':sha(self.source)},'extra_inputs':{'tests/private_entry.gd':sha(self.entry)},
            'executable_sha256':sha(self.exe),'pck_sha256':sha(self.pck)}

    def verify(self,contract=None,exe=None):
        self.contract_path.write_bytes(json.dumps(self.contract if contract is None else contract).encode())
        return verify_package(self.exe if exe is None else exe,self.contract_path,self.project,self.contract['source_inputs'])

    def test_complete_source_and_package_are_bound(self):
        proof=self.verify();self.assertEqual((proof['source_input_count'],proof['extra_input_count']),(1,1));self.assertTrue(package_unchanged(proof))

    def test_incomplete_or_unsafe_declarations_are_rejected(self):
        patches=[{'schema':'other'},{'entry_scene':'res://reduced.tscn'},{'source_inputs':{}},{'extra_inputs':{}},
                 {'extra_inputs':{'../outside':sha(self.entry)}},{'extra_inputs':{'/outside':sha(self.entry)}},
                 {'extra_inputs':{'C:/outside':sha(self.entry)}},{'executable_sha256':'0'*64},{'pck_sha256':'0'*64}]
        for patch in patches:
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.verify(self.contract|patch)

    def test_release_capped_or_modified_physics_are_rejected(self):
        for patch in ({'debug_features':False},{'max_fps':30},{'max_fps':False},{'physics_ticks':30}):
            changed=copy.deepcopy(self.contract);changed['runtime_features'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):self.verify(changed)

    def test_changed_source_and_launcher_are_rejected(self):
        self.source.write_bytes(b'changed source')
        with self.assertRaises(ValueError):self.verify()
        for name in ('engine_console.exe','launcher.py'):
            path=self.root/name;path.write_bytes(b'fake')
            with self.subTest(name=name),self.assertRaises(ValueError):self.verify(exe=path)

    def test_postrun_tamper_and_missing_companion_are_detected(self):
        proof=self.verify();self.pck.write_bytes(b'changed');self.assertFalse(package_unchanged(proof));self.pck.unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_direct_package_and_existing_editor_commands(self):
        self.assertEqual(launch_command('editor',self.project),['editor','--headless','--audio-driver','Dummy','--path',str(self.project),'res://tests/gameplay_load_client.tscn'])
        self.assertEqual(launch_command('editor',self.project,max_fps=60)[-3:],['--max-fps','60','res://tests/gameplay_load_client.tscn'])
        self.assertEqual(launch_command('editor',self.project,package=self.exe),[str(self.exe),'--headless','--audio-driver','Dummy'])
        with self.assertRaises(ValueError):launch_command('editor',self.project,package=self.exe,max_fps=30)
        self.assertEqual(package_environment('unique.json'),{'FANTASYCARD_PRIVATE_QA_MODE':'gameplay','NATIVE_RUNTIME_FEATURE_REPORT':'unique.json'})

    def test_runtime_capability_observation_and_negative_boundaries(self):
        names={'debug_features_retained','game_process_not_editor_hint','development_login_unchanged','no_FPS_cap','normal_physics_tick_rate','no_export_key_environment'}
        good={'mode':'gameplay','debug_features':True,'max_fps':0,'physics_ticks':60,'is_editor_binary':False,'checks':{key:True for key in names}}
        path=self.root/'runtime.json';path.write_bytes(json.dumps(good).encode());self.assertEqual(runtime_capabilities(path)['features'],good)
        for patch in ({'mode':'regressions'},{'debug_features':False},{'max_fps':False},{'physics_ticks':30},{'is_editor_binary':True},{'checks':{}}):
            path.write_bytes(json.dumps(good|patch).encode())
            with self.subTest(patch=patch),self.assertRaises(ValueError):runtime_capabilities(path)
        path.write_bytes(b'[]')
        with self.assertRaises(ValueError):runtime_capabilities(path)

if __name__=='__main__':unittest.main()
