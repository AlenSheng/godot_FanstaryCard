"""Actual child-process gate regressions using declared native-report fixtures."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOL=pathlib.Path(__file__).resolve().parents[1]/'pr13_suite_coverage.py'
SOURCE='1'*40

class NativeSuiteGateCliTests(unittest.TestCase):
    def run_gate(self,outcome,*,native_exit=0,emit=True,expected_source=SOURCE):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=pathlib.Path(temporary.name)
        child=root/'controlled_native.py'
        child.write_text('''import pathlib,sys
outcome=sys.argv[2]
if sys.argv[4]=='emit':
 executed=0 if outcome=='NotExecuted' else 1
 xml='<TestRun><TestDefinitions><UnitTest id="id"><TestMethod name="Critical"/></UnitTest></TestDefinitions><Results><UnitTestResult testId="id" testName="Critical" outcome="'+outcome+'"/></Results><ResultSummary><Counters total="1" executed="'+str(executed)+'" passed="'+str(int(outcome=='Passed'))+'" failed="'+str(int(outcome=='Failed'))+'" notExecuted="'+str(int(outcome=='NotExecuted'))+'"/></ResultSummary></TestRun>'
 pathlib.Path(sys.argv[1]).write_text(xml)
raise SystemExit(int(sys.argv[3]))
''')
        command=root/'command.json';command.write_text(json.dumps([sys.executable,str(child),'{trx}',outcome,str(native_exit),'emit' if emit else 'missing']))
        required=root/'required.json';required.write_text(json.dumps({'Critical':1}))
        output=root/'output'
        result=subprocess.run([sys.executable,str(TOOL),'--command-json',str(command),'--required-methods',str(required),
            '--source-sha',SOURCE,'--expected-source-sha',expected_source,'--output',str(output),'--timeout-seconds','10'],
            capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        return result,json.loads((output/'report.json').read_text())

    def test_actual_zero_exit_passed_rows_ready_for_review_only(self):
        process,report=self.run_gate('Passed')
        self.assertEqual(process.returncode,0)
        self.assertEqual(report['state'],'ReadyForMainReview')
        self.assertFalse(report['acceptance'])

    def test_actual_zero_exit_critical_skip_is_blocked_nonzero(self):
        process,report=self.run_gate('NotExecuted')
        self.assertEqual(report['native_exit'],0)
        self.assertEqual((process.returncode,report['state']),(3,'Blocked'))
        self.assertEqual(report['suite']['skipped_cases'],['Critical'])

    def test_actual_failure_cannot_be_ready(self):
        process,report=self.run_gate('Failed',native_exit=1)
        self.assertEqual((process.returncode,report['state']),(1,'Failed'))

    def test_actual_zero_exit_without_trx_is_blocked(self):
        process,report=self.run_gate('Passed',emit=False)
        self.assertEqual((process.returncode,report['state']),(3,'Blocked'))

    def test_passed_rows_with_stale_source_are_blocked(self):
        process,report=self.run_gate('Passed',expected_source='2'*40)
        self.assertEqual((process.returncode,report['state']),(3,'Blocked'))
        self.assertEqual(report['gate']['stale_source_suites'],['native'])

if __name__=='__main__':unittest.main()
