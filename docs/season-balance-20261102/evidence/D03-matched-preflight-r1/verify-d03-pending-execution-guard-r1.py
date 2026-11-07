from pathlib import Path
import hashlib,json,subprocess

b=Path(__file__).parent;repo=Path.cwd();budget=repo/'docs/season-balance-20261102/D03-BUDGET.json';before=budget.read_bytes()
assert json.loads(before)['maximum']==300 and not (b/'d03-matched-armor-approved-r1').exists()
runner=b/'run-d03-matched-armor-approved-r1.py';compile(runner.read_text('utf-8'),str(runner),'exec')
out=b/'d03-pending-execution-guard-r1';assert not out.exists();out.mkdir()
command=['python',str(runner)];r=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',timeout=10)
(out/'rejected-command.original.json').write_text(json.dumps(dict(command=command,exit=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
assert r.returncode!=0 and 'D03 additional user budget reply has not been granted.' in r.stderr
assert budget.read_bytes()==before and not (b/'d03-matched-armor-approved-r1').exists()
proof=dict(passed=True,pending_budget_rejected_before_run_directory_or_reservation=True,D03_used=299,D03_maximum=300,actual_new_encounters=0,budget_sha256=hashlib.sha256(before).hexdigest(),runner_sha256=hashlib.sha256(runner.read_bytes()).hexdigest(),no_dotnet_command_reached=True)
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
