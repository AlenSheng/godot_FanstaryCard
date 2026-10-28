import json
from pathlib import Path
import subprocess
import sys
import time
B=Path(__file__).resolve().parents[1];E=B/'evidence/coordinator-sticky-verified';E.mkdir(exist_ok=True)
cmd=[sys.executable,str(B/'harness/coordinator_gap.py'),'gap_sticky',str(E)];started=time.monotonic();r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
(E/'stdout.log').write_text(r.stdout);(E/'stderr.log').write_text(r.stderr)
report=json.loads(next((E/'runs').glob('*/report.json')).read_text())
actual={'command':cmd,'caller_exit':r.returncode,'expected_exit':3,'elapsed_real_seconds':time.monotonic()-started,'first_window_lost':report['samples'][0]['window']['lost_event_count'],'final_snapshot_sequences':[e['event_seq'] for e in report['final_clients'][0]['telemetry']],'tail_lost':report['tail_lost_event_count'],'evidence_dimension':report['result_dimensions']['dimensions']['evidence'],'audit_errors':report['audit_read_errors'],'model_inputs':['clock','metrics','telemetry'],'real_paths':['coordinator.main/report/exit','owned child','STOP grace35'],'capacity_claim':False}
assert r.returncode==3 and actual['first_window_lost']==1 and actual['final_snapshot_sequences']==[1,2,3,4] and actual['evidence_dimension']=='Failed'
(E/'receipt.json').write_text(json.dumps(actual,indent=2));print(json.dumps(actual))
