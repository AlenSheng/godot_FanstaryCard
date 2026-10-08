"""Actual subprocess callers: legacy exit/outcome and additive six-dimension scope."""
import json
from pathlib import Path
import subprocess
import sys
import time

B=Path(__file__).resolve().parents[1];out=B/'evidence/caller-integration';out.mkdir(exist_ok=True)
rows=[]
for mode in ['preparation','invalid','operator','smoke_complete','cleanup_unknown']:
 d=out/mode;d.mkdir(exist_ok=True)
 cmd=[sys.executable,str(B/'source/tools/gameplay_load_test.py'),'--godot',sys.executable] if mode=='preparation' else [sys.executable,str(B/'harness/coordinator_case.py'),mode,str(d)]
 started=time.monotonic();r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
 (d/'stdout.log').write_text(r.stdout);(d/'stderr.log').write_text(r.stderr)
 if mode=='preparation':
  old={'exit_code':r.returncode,'scope':'preparation_only','load_accepted':False};new={'scope':'preparation_only','all_applicable_passed':False,'full_acceptance_passed':False};ok=r.returncode==0 and 'Prepared:' in r.stdout
 else:
  p=json.loads(next((d/'runs').glob('*/report.json')).read_text());old={'exit_code':r.returncode,'outcome':p['outcome'],'full_acceptance_claim':False};new={'exit_code':r.returncode,'result_dimensions':p['result_dimensions'],'full_acceptance_passed':p['full_acceptance_passed']};ok=r.returncode==p['outcome']['exit_code'] and set(p['result_dimensions']['dimensions'])=={'execution','evidence','load','gameplay','performance','cleanup'} and not p['full_acceptance_passed']
  if mode in ['invalid','operator','cleanup_unknown']:ok=ok and not p['acceptance_passed']
 rows.append({'mode':mode,'command':cmd,'actual_caller_exit':r.returncode,'legacy_schema_interpretation':old,'new_schema_interpretation':new,'compatible':ok,'elapsed_real_seconds':time.monotonic()-started})
assert all(r['compatible'] for r in rows)
(out/'receipt.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
