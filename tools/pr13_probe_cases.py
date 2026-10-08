"""Real 20-second Python worker faults through the production coordinator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.tests.test_gameplay_load_sampling_contract import CoordinatorSamplingContractTests

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']};records=[]
    for number,all_workers in ((1,False),(2,True)):
        start=time.monotonic();code,result=CoordinatorSamplingContractTests().run_fixture(max_groups=2,probe_delay_seconds=20,delay_all_probes=all_workers)
        actual={'coordinator_exit_code':code,'sample_collection_ms':[s['sample_collection_ms'] for s in result['samples']],'launched_groups':len(result['group_launches']),'stop_triggers':result['all_triggers'],'workers':result['actual_delayed_fixture_workers'],'elapsed_including_worker_join_seconds':time.monotonic()-start,'orphan_fixture_workers':False}
        cid=f'LOAD-07.1-T0{number}'
        passed=code==3 and 'probe_timeout' in result['all_triggers'] and len(result['group_launches'])==1 and 5900<=result['samples'][0]['sample_collection_ms']<=8000 and len(actual['workers'])==(2 if all_workers else 1) and all(w['elapsed_seconds']>=20 for w in actual['workers'])
        records.append({'case_id':cid,'executed':True,'status':'Passed' if passed else 'Failed','setup':contracts[cid]['setup_and_injection'],'expected':contracts[cid]['expected'],'actual':actual,'profiles_executed':['OFFLINE'],'scope':'Actual ThreadPoolExecutor workers and production six-second wait/verdict; child/state/network values are declared controlled fixture inputs. No live capacity claim.'})
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode())
    write(out/'report.json',{'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':sha(plan_path),'source':{'scope':'actual bounded probe worker faults, controlled coordinator children/clock','input_hashes':{p:sha(ROOT/p) for p in ('tools/pr13_probe_cases.py','tools/gameplay_load_test.py','tools/tests/test_gameplay_load_sampling_contract.py')}},'executed':2,'passed':sum(r['status']=='Passed' for r in records),'accepted':False})
    print(json.dumps({'executed':2,'passed':sum(r['status']=='Passed' for r in records)}));return 0 if all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
