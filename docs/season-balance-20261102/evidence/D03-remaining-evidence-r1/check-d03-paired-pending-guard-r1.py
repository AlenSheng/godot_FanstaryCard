from pathlib import Path
import hashlib,json,subprocess

b=Path(__file__).parent;repo=Path.cwd();path=repo/'docs/season-balance-20261102/D03-BUDGET.json';prior=path.read_bytes();assert json.loads(prior)['maximum']==308
out=b/'d03-paired-pending-guard-r1';assert not out.exists() and not (b/'d03-paired-routes-approved-r1').exists();out.mkdir()
command=['python',str(b/'run-d03-paired-routes-approved-r1.py')];r=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',timeout=10)
(out/'rejection.original.json').write_text(json.dumps(dict(command=command,exit=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
assert r.returncode!=0 and 'Additional D03 paired-route budget has not been explicitly approved.' in r.stderr
assert path.read_bytes()==prior and not (b/'d03-paired-routes-approved-r1').exists()
proof=dict(passed=True,no_run_directory_created=True,budget_bytes_unchanged=True,D03_used=308,actual_maximum=308,proposed_maximum=317,no_gameplay_or_dotnet_started=True,runner_sha256=hashlib.sha256((b/'run-d03-paired-routes-approved-r1.py').read_bytes()).hexdigest())
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
