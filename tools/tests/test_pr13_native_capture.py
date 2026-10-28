import unittest
from types import SimpleNamespace
from tools.pr13_native_capture import observe_processes, OWNERSHIP_ENV


class NativeCaptureTests(unittest.TestCase):
    def receipt(self):return dict(pid=123,client_id='client',run_id='run',process_epoch='epoch')
    def process(self, env=None):
        data=dict(FANTASYCARD_LOAD_CLIENT_ID='client',FANTASYCARD_LOAD_RUN_ID='run',
                  FANTASYCARD_LOAD_PROCESS_EPOCH='epoch',UNRELATED_PASSWORD='must-not-be-retained')
        if env:data.update(env)
        return SimpleNamespace(environ=lambda:data,exe=lambda:'/official/godot',
            cmdline=lambda:['/official/godot','--headless'],create_time=lambda:1000,
            nice=lambda:16384,cpu_affinity=lambda:[12,13,14,15],memory_info=lambda:SimpleNamespace(rss=1000000))

    def test_captures_actual_process_properties_and_only_selected_env(self):
        r=observe_processes(dict(launches=[self.receipt()]),1,lambda pid:self.process())
        self.assertEqual(123,r['processes'][0]['pid'])
        self.assertEqual('/official/godot',r['processes'][0]['exe'])
        self.assertEqual(set(OWNERSHIP_ENV),set(r['processes'][0]['load_environment']))
        self.assertNotIn('UNRELATED_PASSWORD',r['processes'][0]['load_environment'])

    def test_does_not_observe_other_processes_when_population_incomplete(self):
        seen=[]
        with self.assertRaises(ValueError):
            observe_processes(dict(launches=[self.receipt()]),2,lambda pid:seen.append(pid))
        self.assertEqual([],seen)

    def test_recycled_PID_with_foreign_owner_rejected(self):
        with self.assertRaises(ValueError):
            observe_processes(dict(launches=[self.receipt()]),1,
                lambda pid:self.process(dict(FANTASYCARD_LOAD_PROCESS_EPOCH='another-launch')))

    def test_duplicate_PID_not_counted_as_two_natives(self):
        with self.assertRaises(ValueError):
            observe_processes(dict(launches=[self.receipt(),self.receipt()]),2,lambda pid:self.process())

    def test_boolean_PID_not_a_native_process(self):
        r=self.receipt();r['pid']=True
        with self.assertRaises(ValueError):observe_processes(dict(launches=[r]),1,lambda pid:self.process())


if __name__=='__main__':unittest.main()
