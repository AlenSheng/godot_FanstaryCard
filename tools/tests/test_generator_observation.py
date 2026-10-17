"""Resource provenance and FPS identity regressions; no network or game claims."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.gameplay_load_validation import workload_profile_identity, native_frame_observations
from tools import gameplay_load_test as runner


class GeneratorObservationTests(unittest.TestCase):
    def test_fps_change_has_new_complete_identity_with_same_family(self):
        a={'profile':'active-hold','client_max_fps':None,'cycle_limit_seconds':240}
        b=dict(a,client_max_fps=60);source={'native':'a'*64}
        x=workload_profile_identity(a,source);y=workload_profile_identity(b,source)
        self.assertEqual(x['profile_family'],y['profile_family'])
        self.assertNotEqual(x['workload_profile_id'],y['workload_profile_id'])
        self.assertTrue(x['qualified'] and y['qualified'])

    def test_profile_definition_is_stable_after_report_metadata_added(self):
        contract={'profile':'active-hold','client_max_fps':60}
        source={'native':'a'*64};result=workload_profile_identity(contract,source)
        contract['workload_profile_id']=result['workload_profile_id'];source['native']='b'*64
        self.assertNotIn('workload_profile_id',result['definition']['contract'])
        self.assertEqual(result['definition']['source_hashes']['native'],'a'*64)
        same=workload_profile_identity({'client_max_fps':60,'profile':'active-hold'},{'native':'a'*64})
        self.assertEqual(same['workload_profile_id'],result['workload_profile_id'])

    def test_missing_source_hashes_do_not_claim_qualified_profile(self):
        self.assertFalse(workload_profile_identity({'profile':'active-hold'}, {})['qualified'])

    def test_frames_are_measured_not_assumed_from_requested_cap(self):
        row=dict(client_id='a',pid=20,generator_frame_clock=dict(process_frames=300,observed_ms=10000,engine_max_fps=60))
        value=native_frame_observations([row])[0]
        self.assertEqual(value['process_fps'],30)
        self.assertEqual(value['engine_max_fps'],60)
        self.assertIsNone(value['missing_reason'])

    def test_old_or_zero_interval_frame_data_stays_unavailable(self):
        result=native_frame_observations([dict(client_id='a',pid=20),dict(client_id='b',pid=21,generator_frame_clock=dict(process_frames=0,observed_ms=0))])
        self.assertTrue(all(x['process_fps'] is None and x['missing_reason'] for x in result))

    def collect(self, *, deny_native=False, previous=None):
        class QueryError(Exception):pass
        class MeasuredProcess:
            def __init__(self,pid):self.pid=pid
            def cpu_times(self):
                if self.pid==20 and deny_native:raise QueryError()
                return SimpleNamespace(user={10:2,20:3}[self.pid],system=0)
            def memory_info(self):return SimpleNamespace(rss={10:10000,20:20000}[self.pid])
            def num_threads(self):return {10:2,20:3}[self.pid]
            def num_handles(self):return {10:5,20:7}[self.pid]
            def io_counters(self):return SimpleNamespace(write_bytes=self.pid*10)
        package=SimpleNamespace(Process=MeasuredProcess,NoSuchProcess=QueryError,AccessDenied=QueryError,
            virtual_memory=lambda:SimpleNamespace(available=9*1024**3),cpu_count=lambda logical:16)
        alive=SimpleNamespace(pid=20,poll=lambda:None);dead=SimpleNamespace(pid=30,poll=lambda:0)
        entries=[dict(client_id='live',process=alive,run_id='r',process_epoch='e'),dict(client_id='exited',process=dead)]
        with patch.object(runner,'psutil',package),patch.object(runner,'time',SimpleNamespace(monotonic=lambda:2.0)),patch.object(runner.os,'getpid',return_value=10):
            return runner.generator_resources(entries,previous)

    def test_per_pid_resources_and_exited_load_are_explicit(self):
        result,_=self.collect(previous=(1.0,{10:1,20:1}))
        self.assertEqual({x['pid'] for x in result['processes']},{10,20})
        self.assertEqual(result['rss_bytes'],30000)
        self.assertEqual(result['cpu_percent_of_one_core'],300)
        self.assertEqual(result['native_alive_processes'],1)
        self.assertEqual(result['excluded_exited_native_processes'][0]['pid'],30)
        self.assertIsNone(result['packet_send_rate'])
        self.assertTrue(result['packet_send_rate_missing_reason'])

    def test_unmeasured_native_resources_are_not_silent_zero(self):
        result,_=self.collect(deny_native=True,previous=(1.0,{10:1,20:1}))
        self.assertIsNone(result['rss_bytes'])
        self.assertIsNone(result['cpu_percent_of_one_core'])
        self.assertFalse(next(x for x in result['processes'] if x['pid']==20)['available'])

    def test_new_process_without_prior_cpu_counter_does_not_fake_total(self):
        result,_=self.collect(previous=(1.0,{10:1}))
        self.assertIsNone(result['cpu_percent_of_one_core'])
        self.assertEqual(next(x for x in result['processes'] if x['pid']==20)['cpu_missing_reason'],'first_or_new_process_counter')


if __name__=='__main__':unittest.main()
