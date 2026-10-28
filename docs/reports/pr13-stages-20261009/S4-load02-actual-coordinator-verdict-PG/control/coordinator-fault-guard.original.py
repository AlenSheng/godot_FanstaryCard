import contextlib
import importlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

C = Path('/control/context')
sys.path.insert(0,str(C))
sys.path.insert(0,str(C/'tools'))
import gameplay_load_test as coordinator
sampling = importlib.import_module('tools.tests.test_gameplay_load_sampling_contract')
finalization = importlib.import_module('tools.tests.test_gameplay_load_finalization')
mode = sys.argv[1]
root = Path('/output/coordinator-fixtures')/mode
root.mkdir(parents=True,exist_ok=False)

class PreserveActualFixtureDirectory:
    def __init__(self,*args,**kwargs):
        self.path = root/('fixture-'+str(len(list(root.glob('fixture-*')))))
        self.path.mkdir()
    def __enter__(self):
        return str(self.path)
    def __exit__(self,*args):
        return False

with patch('tempfile.TemporaryDirectory',PreserveActualFixtureDirectory):
    if mode=='duration-short':
        code,report = sampling.CoordinatorSamplingContractTests().run_fixture(max_seconds=20)
        assert code==1 and report['stop_reason']=='duration_limit'
        assert report['result_dimensions']['dimensions']['execution']=='Passed'
        assert report['result_dimensions']['dimensions']['load']=='Failed'
    elif mode in ['redline-and-invalid','redline']:
        options = {'resource_changes':{'cpu':95,'memory_available':10}}
        if mode=='redline-and-invalid':
            options['final_status_change'] = lambda row:row.update(audit_lost_count=2)
        code,report = sampling.CoordinatorSamplingContractTests().run_fixture(**options)
        assert code==(3 if mode=='redline-and-invalid' else 2)
        assert {'cpu_redline','memory_available_redline'} <= set(report['all_triggers'])
        if mode=='redline-and-invalid':
            assert 'final_audit_loss' in report['all_triggers']
            assert report['result_dimensions']['dimensions']['evidence']=='Failed'
        assert report['result_dimensions']['dimensions']['performance']=='Failed'
    elif mode=='write-failure':
        code,report = finalization.FinalizationTests().run_fixture(report_write_fails=True)
        assert code==3 and 'injected final report disk failure' in report['emergency']
        assert len(list(root.rglob('report.emergency.txt')))==1 and not list(root.rglob('report.json'))
    elif mode=='invalid':
        code,report = sampling.CoordinatorSamplingContractTests().run_fixture(
            final_status_change=lambda row:row.update(audit_lost_count=2))
        assert code==3 and 'final_audit_loss' in report['all_triggers']
    elif mode=='operator':
        code,report = finalization.FinalizationTests().run_fixture(operator_stop=True)
        assert code==130 and report['stop_reason']=='operator_stop_file'
    elif mode=='prepare-only':
        target = root/'actual-preparation-output'
        args = [sys.executable,str(C/'tools/gameplay_load_test.py'),'--godot',sys.executable,'--output',str(target)]
        result = subprocess.run(args,capture_output=True,timeout=20)
        (root/'caller.stdout.original.log').write_bytes(result.stdout)
        (root/'caller.stderr.original.log').write_bytes(result.stderr)
        code = result.returncode
        assert code==0 and not result.stderr and result.stdout.startswith(b'Prepared:')
        assert not target.exists()
        report = {'prepared_only':True,'actual_stdout':result.stdout.decode(),
                  'load_run_started':False,'acceptance_passed':False,'actual_cli':args}
    elif mode=='hang':
        child = foreign = None
        report = {}
        try:
            child = subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])
            foreign = subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])
            before = {'owned_pid':child.pid,'foreign_pid':foreign.pid,'foreign_before':foreign.poll()}
            (root/'owned-and-foreign-child-start.original.json').write_bytes((json.dumps(before,indent=2)+'\n').encode())
            forced = coordinator.stop_all([{'process':child}],root/'STOP',grace_seconds=.2)
            assert forced==[child.pid] and child.poll() is not None and foreign.poll() is None
            code = 3
            report = {**before,'forced_termination_pids':forced,'owned_exit':child.poll(),
                      'foreign_after_stop_all':foreign.poll(),'foreign_untouched_by_stop_all':True,
                      'acceptance_passed':False,'scope':'Actual bounded stop_all and two real processes; code 3 is this fault harness classification'}
        finally:
            for process in [child,foreign]:
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=10)
            if foreign is not None:
                report['foreign_reaped_only_by_separate_fixture_finalizer'] = foreign.poll() is not None
    else:
        raise ValueError('Unknown frozen fault mode')
assert report.get('acceptance_passed') is not True
observation = {'mode':mode,'actual_child_exit_code':code,'actual_report':report,
    'return_code_source':'coordinator.main return propagated as child exit' if mode!='hang' else 'Fault harness classification after actual stop_all forced cleanup',
    'injection_scope':'Current coordinator and existing frozen fake observation/clock/child fixtures, with real owned child cleanup for hang and real CLI preparation. Integrated while real PostgreSQL room is held; no live load or capacity claim',
    'all_raw_fixture_files_preserved':True}
(root/'actual-observation.original.json').write_bytes((json.dumps(observation,indent=2)+'\n').encode())
print(json.dumps(observation))
raise SystemExit(code)
