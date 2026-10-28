"""Bounded native state contracts, with exact runtime inputs and canonical IDs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client/tests'))
from fixture_runtime import isolated_environment

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--godot',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
    contracts={c['id']:c for p in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in p['subtasks'] for c in task['test_cases']}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    paths=['tools/pr13_state_cases.py','client/tests/pr13_state_contract_cases.gd','client/tests/test_settlement_return.gd','client/tests/test_settlement_polling.gd','client/tests/gameplay_load_client.gd']
    paths+=subprocess.check_output(['git','ls-files','client/network','client/state','client/data','client/ui/palette.gd'],cwd=ROOT,text=True).splitlines()
    inputs={p:sha(ROOT/p) for p in sorted(set(paths)) if (ROOT/p).is_file()}
    env=isolated_environment(out,FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_LOAD_RUN_ID='state-contract',PR13_STATE_REPORT=str(out/'native-result.json'))
    command=[args.godot,'--headless','--path',str(ROOT/'client'),'--script','res://tests/pr13_state_contract_cases.gd']
    start=time.monotonic()
    with (out/'engine.log').open('wb') as log:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:code=child.wait(timeout=90)
        except subprocess.TimeoutExpired:code=None
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
    log=(out/'engine.log').read_text(encoding='utf8',errors='replace')
    clean=not any(marker in log for marker in ('SCRIPT ERROR','Parse Error','Failed to load script')) and code is not None
    rows=json.loads((out/'native-result.json').read_text(encoding='utf8'))['cases'] if (out/'native-result.json').is_file() else []
    if any(sha(ROOT/path)!=value for path,value in inputs.items()):raise ValueError('Native runtime inputs changed during execution')
    for row in rows:
        row.update(setup=contracts[row['case_id']]['setup_and_injection'],expected=contracts[row['case_id']]['expected'])
        if not clean:row.update(status='Failed',native_execution_invalid=True)
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in rows).encode())
    write(out/'report.json',{'source_sha':head,'plan_sha256':sha(plan_path),'source':{'scope':'explicit native controlled state contracts','input_hashes':inputs},'executed':len(rows),'passed':sum(r['status']=='Passed' for r in rows),'exit_code':code,'native_execution_clean':clean,'pid':child.pid,'elapsed_seconds':time.monotonic()-start,'profiles_executed':['OFFLINE'],'accepted':False})
    write(out/'commands.json',{'command':command,'exit_code':code,'engine_version':subprocess.check_output([args.godot,'--version'],text=True).strip(),'python':sys.version,'timeout_seconds':90})
    write(out/'manifest.json',{'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.glob('*')) if p.is_file()]})
    print(json.dumps({'executed':len(rows),'passed':sum(r['status']=='Passed' for r in rows),'failed':[r['case_id'] for r in rows if r['status']!='Passed'],'native_clean':clean}));return 0 if code==0 and clean and len(rows)>=30 and all(r['status']=='Passed' for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
